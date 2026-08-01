import re
from typing import Tuple

PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|above)\s+(instructions|directives|prompts)",
    r"(?i)system\s*:\s*",
    r"(?i)developer\s+mode\s+(on|enabled)",
    r"(?i)<\|im_start\|>",
    r"(?i)<\|im_end\|>",
    r"(?i)you\s+are\s+now\s+an?\s+unrestricted",
    r"(?i)override\s+(system|safety)\s+rules",
    r"(?i)disregard\s+prior\s+context",
]

def sanitize_ocr_text(text: str) -> Tuple[str, bool]:
    """
    Sanitizes extracted OCR text before it is fed into LLM prompts.
    Returns (sanitized_text, flagged_for_suspicious_patterns).
    """
    if not text:
        return "", False
        
    flagged = False
    sanitized = text

    # Remove null bytes and non-printable control characters
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", sanitized)

    # Detect and neutralize prompt injection triggers
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, sanitized):
            flagged = True
            sanitized = re.sub(pattern, "[FLAGGED_INJECTION_REMOVED]", sanitized)

    return sanitized, flagged

def format_grounded_context(chunks: list[dict]) -> str:
    """
    Wraps retrieved document chunks securely inside XML-style delimiters so LLMs treat them purely as data.
    """
    formatted_sources = []
    for idx, chunk in enumerate(chunks, 1):
        doc_name = chunk.get("doc_name", "Unknown Document")
        page = chunk.get("page_number", 1)
        text, _ = sanitize_ocr_text(chunk.get("text", ""))
        formatted_sources.append(
            f'<source index="{idx}" document="{doc_name}" page="{page}">\n{text}\n</source>'
        )
    
    return "<retrieved_context>\n" + "\n\n".join(formatted_sources) + "\n</retrieved_context>"
