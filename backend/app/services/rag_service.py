import re
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple
from sqlalchemy.orm import Session
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
from app.config import settings
from app.core.logging import logger
from app.core.sanitizer import sanitize_ocr_text, format_grounded_context
from app.db.models import Document
from app.db.vector_store import SQLiteVectorRepository
from app.services.embedding_service import embedding_service, EmbeddingProviderError

_thread_pool = ThreadPoolExecutor(max_workers=4)

# Matches the "--- Page N ---" markers the OCR service writes, so chunks keep
# their page number even after the user edits the text.
_PAGE_MARKER_RE = re.compile(r"^---\s*Page\s+(\d+)\s*---\s*$", re.MULTILINE)


def split_pages(text: str) -> List[Tuple[int, str]]:
    """Split OCR text back into (page_number, page_text) using the page markers."""
    matches = list(_PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [(1, text)]

    pages = []
    # Anything before the first marker still belongs to page 1.
    preamble = text[:matches[0].start()].strip()
    if preamble:
        pages.append((1, preamble))

    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if body:
            pages.append((int(match.group(1)), body))
    return pages or [(1, text)]


class RAGService:
    def __init__(self):
        self.vector_repo = SQLiteVectorRepository()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        # ponytail: a low floor that only drops pure noise. Grounding is enforced by
        # the system prompt, not by guessing a cosine cutoff that differs per embedder.
        self.min_confidence_threshold = settings.RETRIEVAL_MIN_SIMILARITY

    def index_document(self, db: Session, document_id: str) -> int:
        """Chunk the document's OCR text, embed it, and replace its vector-store entries."""
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        text_to_index = doc.ocr_edited_text or doc.ocr_raw_text
        if not text_to_index or not text_to_index.strip():
            raise ValueError("Document has no text to index")

        sanitized_text, flagged = sanitize_ocr_text(text_to_index)
        if flagged:
            logger.warning(
                f"Document {document_id} contained potential prompt injection patterns (sanitized)."
            )

        # Re-confirming a document must replace its chunks, not duplicate them.
        removed = self.vector_repo.delete_by_document(db, document_id)
        if removed:
            logger.info(f"Removed {removed} stale chunks before re-indexing {document_id}")

        pending: List[Dict[str, Any]] = []
        for page_number, page_text in split_pages(sanitized_text):
            for chunk_text in self.text_splitter.split_text(page_text):
                if not chunk_text.strip():
                    continue
                pending.append({
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_index": len(pending),
                    "chunk_text": chunk_text,
                    "metadata": {
                        "doc_name": doc.filename,
                        "flagged": flagged,
                        "embed_model": embedding_service.active_model,
                    },
                })

        if not pending:
            raise ValueError("Document produced no indexable chunks")

        logger.info(f"Embedding {len(pending)} chunks for document {document_id}...")
        vectors = embedding_service.embed_documents([c["chunk_text"] for c in pending])
        for chunk, vector in zip(pending, vectors):
            chunk["embedding"] = vector

        chunk_ids = self.vector_repo.add_chunks(db, pending)
        doc.status = "indexed"
        db.commit()
        logger.info(f"Indexed {len(chunk_ids)} chunks for document {document_id} ({doc.filename})")
        return len(chunk_ids)

    def retrieve_relevant_chunks(
        self, db: Session, query: str, top_k: int = 4, doc_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        query_vector = embedding_service.embed_text(query)
        return self.vector_repo.hybrid_search(db, query, query_vector, top_k=top_k, doc_ids=doc_ids)

    async def generate_rag_response_stream(
        self, db: Session, query: str, doc_ids: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream RAG chat tokens and citations as SSE JSON objects."""
        loop = asyncio.get_running_loop()
        try:
            retrieved_chunks = await loop.run_in_executor(
                _thread_pool,
                lambda: self.retrieve_relevant_chunks(db, query, top_k=4, doc_ids=doc_ids),
            )
        except EmbeddingProviderError as e:
            # The question itself could not be embedded, so no search happened.
            # Say that plainly instead of leaking a provider quota dump.
            logger.warning(f"Query embedding failed: {e}")
            message = (
                "The embedding service is rate limited right now, so I couldn't search "
                "your documents. Wait about a minute and ask again."
                if e.rate_limited
                else "The embedding service is unavailable, so I couldn't search your "
                     "documents. Please try again shortly."
            )
            for group in self._chunk_text_tokens(message):
                yield self._sse({"type": "token", "content": group})
                await asyncio.sleep(0.02)
            yield self._sse({"type": "citations", "content": []})
            yield self._sse({"type": "done"})
            return

        max_similarity = max((c.get("similarity", 0) for c in retrieved_chunks), default=0.0)
        logger.info(
            f"Retrieved {len(retrieved_chunks)} chunks (max similarity {max_similarity:.3f}) "
            f"for query: {query[:80]!r}"
        )

        if not retrieved_chunks or max_similarity < self.min_confidence_threshold:
            # Distinguish "nothing matched" from "the document is invisible to search",
            # which otherwise looks identical to the user.
            stale = await loop.run_in_executor(
                _thread_pool, lambda: self.vector_repo.stale_document_names(db, doc_ids)
            )
            if stale:
                fallback_msg = (
                    f"{', '.join(stale)} was indexed with a different embedding model, "
                    "so it cannot be searched right now. Open it in Upload & Review and "
                    "choose 'Re-index with edits' to rebuild it, then ask again."
                )
                logger.warning(f"Query blocked by stale embeddings in: {', '.join(stale)}")
            else:
                fallback_msg = (
                    "I couldn't find anything relevant in your indexed documents to answer that. "
                    "Make sure the document you want to ask about has finished indexing, "
                    "then try rephrasing the question."
                )
            for group in self._chunk_text_tokens(fallback_msg):
                yield self._sse({"type": "token", "content": group})
                await asyncio.sleep(0.02)
            yield self._sse({"type": "citations", "content": []})
            yield self._sse({"type": "done"})
            return

        citations = []
        seen = set()
        for chunk in retrieved_chunks:
            key = (chunk.get("document_id"), chunk.get("page_number"))
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "document_id": chunk.get("document_id"),
                "document_name": chunk.get("doc_name"),
                "page_number": chunk.get("page_number", 1),
                "snippet": chunk.get("text", "")[:300],
            })

        if settings.GEMINI_API_KEY:
            streamed = False
            try:
                async for event in self._stream_gemini(query, retrieved_chunks, loop):
                    streamed = True
                    yield event
            except Exception as e:
                logger.warning(f"Gemini stream failed: {e}. Falling back to grounded extract.")

            if streamed:
                yield self._sse({"type": "citations", "content": citations})
                yield self._sse({"type": "done"})
                return

        # Grounded extract fallback: quotes retrieved text, never invents content.
        top = retrieved_chunks[0]
        response_text = (
            f"From **{top.get('doc_name', 'your document')}** (page {top.get('page_number', 1)}):\n\n"
            f"> {top.get('text', '').strip()[:600]}\n\n"
            f"This is the closest passage found in your indexed documents. "
            f"Set GEMINI_API_KEY to get a synthesized answer across all "
            f"{len(retrieved_chunks)} retrieved passages."
        )
        for group in self._chunk_text_tokens(response_text):
            yield self._sse({"type": "token", "content": group})
            await asyncio.sleep(0.015)

        yield self._sse({"type": "citations", "content": citations})
        yield self._sse({"type": "done"})

    async def _stream_gemini(self, query, chunks, loop) -> AsyncGenerator[str, None]:
        """Bridge Gemini's blocking stream iterator onto the event loop."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        system_prompt = (
            "You are a document intelligence assistant. Answer the user's question using ONLY "
            "the text inside <retrieved_context>. If the answer is not in that context, say so "
            "plainly. Never invent facts. Cite document names and page numbers where relevant."
        )
        user_prompt = f"User Question: {query}\n\n{format_grounded_context(chunks)}"

        queue: asyncio.Queue = asyncio.Queue()

        def _pump():
            # asyncio.Queue is not thread-safe, so hand items back via the loop.
            try:
                stream = client.models.generate_content_stream(
                    model=settings.GEMINI_MODEL,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(system_instruction=system_prompt),
                )
                for chunk in stream:
                    if chunk.text:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(_thread_pool, _pump)

        while True:
            item = await queue.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield self._sse({"type": "token", "content": item})

    @staticmethod
    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    def _chunk_text_tokens(self, text: str):
        words = text.split(" ")
        for i in range(0, len(words), 2):
            yield " ".join(words[i:i + 2]) + " "


rag_service = RAGService()
