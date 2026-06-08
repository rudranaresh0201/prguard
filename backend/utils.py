from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split on sentence boundaries with character-overlap."""
    import re
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    cleaned = cleaned.replace("-\n", "").replace("\n", " ")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return []

    # Split on sentence-ending punctuation or bullet points
    sentence_endings = re.compile(r'(?<=[.!?])\s+|(?=•)')
    sentences = [s.strip() for s in sentence_endings.split(cleaned) if s.strip()]
    if not sentences:
        return [cleaned]

    chunks = []
    current = ""

    for sentence in sentences:
        candidate = (current + " " + sentence).strip() if current else sentence
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current and len(current.split()) >= 5:
                chunks.append(current)
            # Start new chunk with overlap from end of previous
            overlap_text = current[-overlap:] if current else ""
            last_space = overlap_text.find(" ")
            overlap_text = overlap_text[last_space + 1:] if last_space != -1 else overlap_text
            current = (overlap_text + " " + sentence).strip() if overlap_text else sentence

    if current and len(current.split()) >= 5:
        chunks.append(current)

    return chunks if chunks else [cleaned]
