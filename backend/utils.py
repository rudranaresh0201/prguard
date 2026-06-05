from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    cleaned = str(text or "")
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(cleaned):
        end = start + chunk_size
        piece = cleaned[start:end]
        if piece:
            chunks.append(piece)
        start += step
    return chunks
