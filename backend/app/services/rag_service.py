import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, AsyncGenerator, Optional
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
from app.services.embedding_service import embedding_service

_thread_pool = ThreadPoolExecutor(max_workers=2)


class RAGService:
    def __init__(self):
        self.vector_repo = SQLiteVectorRepository()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        self.min_confidence_threshold = 0.55

    def index_document(self, db: Session, document_id: str) -> int:
        """
        Chunks the document's OCR text, generates embeddings, and saves to the vector store.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        text_to_index = doc.ocr_edited_text or doc.ocr_raw_text
        if not text_to_index:
            raise ValueError("Document has no text to index")

        # Sanitize text before chunking
        sanitized_text, flagged = sanitize_ocr_text(text_to_index)
        if flagged:
            logger.warning(f"Document {document_id} contained potential prompt injection patterns (sanitized).")

        raw_chunks = self.text_splitter.split_text(sanitized_text)
        chunk_objects = []
        
        for idx, chunk_text in enumerate(raw_chunks):
            embedding = embedding_service.embed_text(chunk_text)
            chunk_objects.append({
                "document_id": document_id,
                "page_number": 1,
                "chunk_index": idx,
                "chunk_text": chunk_text,
                "embedding": embedding,
                "metadata": {"doc_name": doc.filename, "flagged": flagged}
            })

        chunk_ids = self.vector_repo.add_chunks(db, chunk_objects)
        doc.status = "indexed"
        db.commit()
        logger.info(f"Successfully indexed {len(chunk_ids)} chunks for document {document_id}")
        return len(chunk_ids)

    def retrieve_relevant_chunks(self, db: Session, query: str, top_k: int = 4, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        query_vector = embedding_service.embed_text(query)
        chunks = self.vector_repo.hybrid_search(db, query, query_vector, top_k=top_k, doc_ids=doc_ids)
        return chunks

    async def generate_rag_response_stream(
        self, db: Session, query: str, doc_ids: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams RAG chat tokens and citations as SSE JSON objects.
        """
        # Run retrieval in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        retrieved_chunks = await loop.run_in_executor(
            _thread_pool, lambda: self.retrieve_relevant_chunks(db, query, top_k=4, doc_ids=doc_ids)
        )
        
        # Check retrieval confidence score threshold
        max_similarity = max((c.get("similarity", 0) for c in retrieved_chunks), default=0.0)
        
        if not retrieved_chunks or max_similarity < self.min_confidence_threshold:
            fallback_msg = "I'm sorry, but I couldn't find relevant information in your uploaded documents to answer this question. Please make sure you have uploaded and indexed at least one document first."
            for char_group in self._chunk_text_tokens(fallback_msg):
                yield f"data: {json.dumps({'type': 'token', 'content': char_group})}\n\n"
                await asyncio.sleep(0.02)
            yield f"data: {json.dumps({'type': 'citations', 'content': []})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Prepare Citations
        citations = []
        seen_citations = set()
        for chunk in retrieved_chunks:
            key = (chunk.get("doc_name"), chunk.get("page_number"))
            if key not in seen_citations:
                seen_citations.add(key)
                citations.append({
                    "document_id": chunk.get("document_id"),
                    "document_name": chunk.get("doc_name"),
                    "page_number": chunk.get("page_number", 1),
                    "snippet": chunk.get("text", "")[:150] + "..."
                })

        # Check if live Gemini API is configured
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                grounded_context = format_grounded_context(retrieved_chunks)
                
                system_prompt = (
                    "You are a document intelligence AI assistant. "
                    "Answer the user's question using ONLY the provided document context inside <retrieved_context>. "
                    "Do NOT invent facts outside the context. Cite the document names where appropriate."
                )
                user_prompt = f"User Question: {query}\n\n{grounded_context}"

                # Gemini's generate_content_stream is synchronous —
                # collect chunks in a thread, push them via an async queue.
                chunk_queue: asyncio.Queue = asyncio.Queue()

                def _run_gemini_stream():
                    try:
                        response = client.models.generate_content_stream(
                            model=settings.GEMINI_MODEL,
                            contents=[system_prompt, user_prompt]
                        )
                        for chunk in response:
                            if chunk.text:
                                chunk_queue.put_nowait(chunk.text)
                    except Exception as e:
                        logger.warning(f"Gemini stream error: {e}")
                    finally:
                        chunk_queue.put_nowait(None)  # Sentinel

                loop = asyncio.get_event_loop()
                loop.run_in_executor(_thread_pool, _run_gemini_stream)

                while True:
                    token = await chunk_queue.get()
                    if token is None:
                        break
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

                yield f"data: {json.dumps({'type': 'citations', 'content': citations})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            except Exception as e:
                logger.warning(f"Gemini LLM stream call failed: {e}. Utilizing grounded generation fallback.")

        # Grounded mock generator for local dev / fallback
        first_doc = retrieved_chunks[0].get("doc_name", "Document")
        snippet = retrieved_chunks[0].get("text", "")
        response_text = (
            f"Based on **{first_doc}** (page {retrieved_chunks[0].get('page_number', 1)}), "
            f"here is the relevant information regarding '{query}':\n\n"
            f"> \"{snippet[:280]}\"\n\n"
            f"This summary directly reflects the extracted OCR content from your indexed document."
        )

        for char_group in self._chunk_text_tokens(response_text):
            yield f"data: {json.dumps({'type': 'token', 'content': char_group})}\n\n"
            await asyncio.sleep(0.015)

        yield f"data: {json.dumps({'type': 'citations', 'content': citations})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    def _chunk_text_tokens(self, text: str):
        words = text.split(" ")
        for i in range(0, len(words), 2):
            yield " ".join(words[i:i+2]) + " "

rag_service = RAGService()
