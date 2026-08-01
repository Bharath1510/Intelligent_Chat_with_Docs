import os
from typing import Dict, Any, List, Optional
from app.config import settings
from app.core.logging import logger


class OCRUnavailableError(RuntimeError):
    """No OCR engine available to read a scanned page."""


class OCRExtractionError(RuntimeError):
    """The file was read but yielded no usable text."""


# ponytail: a PDF page with fewer than this many chars has no real text layer -> rasterize + OCR.
MIN_TEXT_LAYER_CHARS = 32
# ponytail: 200 DPI is the accuracy/speed knee for PP-OCR; raise it if small print is missed.
RASTER_DPI = 200

PAGE_MARKER = "--- Page {n} ---"


def _jsonable(value):
    """Bounding boxes come back as numpy arrays; JSON columns need plain lists."""
    if value is None:
        return None
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value


class OCRService:
    def __init__(self):
        self._paddle = None
        self._init_error: Optional[str] = None
        self._initialized = False

    def _engine(self):
        """Lazy-init PaddleOCR. Returns the engine, or None if it could not start."""
        if self._initialized:
            return self._paddle

        self._initialized = True
        try:
            from paddleocr import PaddleOCR
            # PaddleOCR 3.x arg names: use_angle_cls/show_log were removed.
            # mkldnn off: paddle 3.3.1 on this CPU raises ConvertPirAttribute2RuntimeAttribute
            # during text detection. Turn it back on once paddle fixes the oneDNN kernel.
            self._paddle = PaddleOCR(
                use_textline_orientation=True,
                lang=settings.OCR_LANG,
                enable_mkldnn=settings.OCR_ENABLE_MKLDNN,
            )
            logger.info(f"PaddleOCR engine initialized (lang={settings.OCR_LANG}).")
        except Exception as e:
            self._init_error = f"{type(e).__name__}: {e}"
            logger.error(
                f"PaddleOCR is unavailable, scanned pages cannot be read: {self._init_error}"
            )
        return self._paddle

    def engine_status(self) -> Dict[str, Any]:
        """Reported by /health so the UI never claims an engine that isn't loaded."""
        return {
            "engine": "PaddleOCR",
            "available": self._engine() is not None,
            "error": self._init_error,
        }

    def extract_text_from_file(self, file_path: str) -> Dict[str, Any]:
        """Extract text, per-block confidence and page numbers from a PDF or image."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self._process_pdf(file_path)
        return self._process_image(file_path)

    def _ocr_blocks(self, source, page: int, first_block_id: int) -> List[Dict[str, Any]]:
        """Run PaddleOCR over one image (path or numpy array) and normalize its output."""
        engine = self._engine()
        if engine is None:
            raise OCRUnavailableError(
                f"PaddleOCR engine is not available ({self._init_error}). "
                "Install paddlepaddle to read scanned pages."
            )

        # 3.x exposes predict(); older builds only have ocr().
        raw = engine.predict(source) if hasattr(engine, "predict") else engine.ocr(source)

        blocks: List[Dict[str, Any]] = []
        for result in raw or []:
            if isinstance(result, dict):
                texts = result.get("rec_texts") or []
                scores = result.get("rec_scores") or []
                polys = result.get("rec_polys") or result.get("dt_polys") or []
                rows = zip(texts, scores, list(polys) + [None] * (len(texts) - len(polys)))
            else:
                # PaddleOCR 2.x shape: [[bbox, (text, score)], ...]
                rows = ((line[1][0], line[1][1], line[0]) for line in result or [])

            for text, score, poly in rows:
                if not str(text).strip():
                    continue
                blocks.append({
                    "block_id": first_block_id + len(blocks),
                    "page": page,
                    "text": str(text),
                    "confidence": round(float(score), 3) if score is not None else None,
                    "bbox": _jsonable(poly),
                    "source": "paddleocr",
                })
        return blocks

    def _process_image(self, image_path: str) -> Dict[str, Any]:
        blocks = self._ocr_blocks(image_path, page=1, first_block_id=1)
        if not blocks:
            raise OCRExtractionError("PaddleOCR found no readable text in this image.")

        logger.info(f"OCR read {len(blocks)} blocks from image {os.path.basename(image_path)}")
        return {
            "text": "\n".join(b["text"] for b in blocks),
            "total_pages": 1,
            "blocks": blocks,
            "metadata": {"engine": "PaddleOCR", "ocr_pages": 1, "text_layer_pages": 0},
        }

    def _process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Use the embedded text layer where the PDF has one (fast and exact),
        and fall back to rasterize + PaddleOCR only for pages that are scans.
        """
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)

        blocks: List[Dict[str, Any]] = []
        page_texts: List[str] = []
        rendered = None
        ocr_pages = 0
        text_layer_pages = 0

        for page_no, page in enumerate(reader.pages, 1):
            try:
                layer = (page.extract_text() or "").strip()
            except Exception as e:
                logger.warning(f"Text-layer read failed on page {page_no}: {e}")
                layer = ""

            if len(layer) >= MIN_TEXT_LAYER_CHARS:
                text_layer_pages += 1
                blocks.append({
                    "block_id": len(blocks) + 1,
                    "page": page_no,
                    "text": layer,
                    "confidence": 1.0,
                    "bbox": None,
                    "source": "pdf_text_layer",
                })
                page_texts.append(f"{PAGE_MARKER.format(n=page_no)}\n{layer}")
                continue

            # No text layer: this page is a scan, so it needs real OCR.
            if rendered is None:
                import pypdfium2 as pdfium
                rendered = pdfium.PdfDocument(pdf_path)

            import numpy as np
            image = rendered[page_no - 1].render(scale=RASTER_DPI / 72).to_pil().convert("RGB")
            page_blocks = self._ocr_blocks(np.asarray(image), page_no, len(blocks) + 1)
            if page_blocks:
                ocr_pages += 1
                blocks.extend(page_blocks)
                joined = "\n".join(b["text"] for b in page_blocks)
                page_texts.append(f"{PAGE_MARKER.format(n=page_no)}\n{joined}")

        if rendered is not None:
            rendered.close()

        if not page_texts:
            raise OCRExtractionError(
                f"No text could be extracted from any of the {total_pages} page(s)."
            )

        logger.info(
            f"PDF extraction complete: {total_pages} pages "
            f"({text_layer_pages} via text layer, {ocr_pages} via PaddleOCR), {len(blocks)} blocks"
        )
        return {
            "text": "\n\n".join(page_texts),
            "total_pages": total_pages,
            "blocks": blocks,
            "metadata": {
                "engine": "PaddleOCR" if ocr_pages else "PdfTextLayer",
                "ocr_pages": ocr_pages,
                "text_layer_pages": text_layer_pages,
            },
        }


ocr_service = OCRService()
