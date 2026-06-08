from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path

import requests
from dotenv import load_dotenv

from .core.logging import get_logger

load_dotenv()

logger = get_logger(__name__)

HF_CACHE_DIR = os.getenv("HF_CACHE_DIR", "").strip()
if HF_CACHE_DIR:
    os.environ["HF_HOME"] = HF_CACHE_DIR


def generate_answer_openrouter(query: str, context: str) -> str:
    # Try OpenRouter first
    try:
        model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-small-24b-instruct-2501")
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8003",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a precise, comprehensive assistant. Answer using the provided context. Always list ALL relevant items — never truncate. Report everything present and note any gaps."},
                {"role": "user", "content": f"Context:\n{context[:8000]}\n\nQuestion: {query}"},
            ],
            "temperature": 0.2,
            "max_tokens": 1000,
        }
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=30,
        )
        logger.warning("[OPENROUTER] status=%s body=%s", r.status_code, r.text[:300])
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.warning("[OPENROUTER] Failed: %s — trying Groq", e)

    # Groq fallback
    try:
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_key:
            raise ValueError("GROQ_API_KEY not set")

        groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": groq_model,
            "messages": [
                {"role": "system", "content": "You are a precise, comprehensive assistant. Answer using the provided context. Always list ALL relevant items — never truncate. Report everything present and note any gaps."},
                {"role": "user", "content": f"Context:\n{context[:8000]}\n\nQuestion: {query}"},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=30,
        )
        logger.warning("[GROQ] status=%s body=%s", r.status_code, r.text[:300])
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.error("[GROQ] Failed: %s", e)
        return "I was unable to generate an answer. Please try again."


def generate_answer(query: str, context: str) -> str:
    return generate_answer_openrouter(query, str(context or ""))
