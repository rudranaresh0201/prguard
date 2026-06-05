from __future__ import annotations

import os
import re
import threading
import time
import warnings
from difflib import SequenceMatcher
from pathlib import Path

import requests

HF_CACHE_DIR = os.getenv("HF_CACHE_DIR", "").strip()
if HF_CACHE_DIR:
    os.environ["HF_HOME"] = HF_CACHE_DIR
    os.environ["TRANSFORMERS_CACHE"] = HF_CACHE_DIR
    os.environ["HUGGINGFACE_HUB_CACHE"] = HF_CACHE_DIR
    os.environ["HF_HUB_CACHE"] = HF_CACHE_DIR
    os.environ["HF_DATASETS_CACHE"] = HF_CACHE_DIR
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["XDG_CACHE_HOME"] = HF_CACHE_DIR

from typing import Any

from dotenv import load_dotenv
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.utils import logging as hf_logging

from .core.logging import get_logger

load_dotenv()

GENERATION_MAX_TIME = float(os.getenv("LLM_MAX_TIME_SECONDS", "20"))
SECTION_TIMEOUT_SECONDS = 20.0
FAST_MODE = os.getenv("FAST_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}
SECTION_PROMPT = """
You are an expert teacher.

Section goal:
{section_instruction}

Diversity rule:
Do NOT reuse sentences between sections. Each section must contain new phrasing.

Constraints:
- Use only the given context.
- Keep output only for this section.
- Do not include other section headers.
- Avoid copying full context sentences.

Question:
{question}

Context:
{context}

Section Output ({section_name} only):
"""

PROMPT = """You are a precise assistant that answers questions using ONLY the provided context.

RULES:
- Answer in detail using information from the context below.
- If the context contains the answer, explain it thoroughly in 3-5 sentences minimum.
- Use bullet points for lists or multiple points.
- If the answer is NOT in the context, say: "I cannot find this in the provided document."
- Never make up information.

Context:
{context}

Question: {query}

Detailed Answer:"""

_tokenizer: Any | None = None
_model: Any | None = None
_model_load_lock = threading.Lock()
logger = get_logger(__name__)
hf_logging.set_verbosity_error()
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

if HF_CACHE_DIR:
    logger.info("Using HuggingFace cache at %s", HF_CACHE_DIR)


def _normalize_path(path_value: str) -> str:
    return str(Path(path_value).as_posix()).lower().rstrip("/")

def _build_prompt(query: str, context: str) -> str:
    return PROMPT.format(context=context[:8000], query=query)


def _build_section_prompt(
    query: str,
    context: str,
    section_name: str,
    section_instruction: str,
    avoid_text: str = "",
) -> str:
    extra = ""
    if avoid_text.strip():
        extra = (
            "\n\nAvoid repeating these phrases:\n"
            f"{avoid_text.strip()}\n"
        )

    return SECTION_PROMPT.format(
        question=query,
        context=context,
        section_name=section_name,
        section_instruction=section_instruction,
    ) + extra


def _clean_context_before_llm(context: str) -> str:
    text = str(context or "").replace("\r", "")

    # Remove clear noise patterns commonly found in paper front matter.
    text = re.sub(r"\b[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", text)
    text = re.sub(r"\[(?:\d+\s*(?:,\s*\d+)*)\]", " ", text)
    text = re.sub(r"(?i)arXiv:[^\n]+", " ", text)
    text = re.sub(r"(?i)provided proper attribution[^\n]*", " ", text)
    text = re.sub(r"(?i)equal contribution[^\n]*", " ", text)
    text = re.sub(r"(?i)work performed while[^\n]*", " ", text)

    cleaned_blocks: list[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue

        source_line = lines[0] if lines[0].startswith("[Source:") else ""
        body = " ".join(lines[1:] if source_line else lines)

        # Remove citation brackets and collapse whitespace again after line join.
        body = re.sub(r"\[(?:\d+\s*(?:,\s*\d+)*)\]", " ", body)
        body = re.sub(r"\s+", " ", body).strip()

        # Drop author-list heavy spans (many short Proper-Name pairs).
        body = re.sub(
            r"(?:\b[A-Z][a-z]+\s+[A-Z][a-z]+\b(?:\s*[,*†‡]|\s+)){4,}",
            " ",
            body,
        )
        body = re.sub(r"\s+", " ", body).strip()

        if not body:
            continue

        cleaned_blocks.append((source_line + "\n" if source_line else "") + body)

    cleaned = "\n\n".join(cleaned_blocks).strip()
    return cleaned or text


def _clean_generated_answer(answer: str) -> str:
    text = str(answer or "").replace("\r", "").strip()
    text = re.sub(r"\b[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", text)
    text = re.sub(r"\[(?:\d+\s*(?:,\s*\d+)*)\]", " ", text)
    text = re.sub(r"(?i)arXiv:[^\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text.strip()) if segment.strip()]


def _dedupe_sentences(text: str) -> str:
    sentences = _split_sentences(text)
    unique: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        normalized = re.sub(r"\s+", " ", sentence).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(sentence.strip())
    return " ".join(unique).strip()


def _has_obvious_repetition(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not cleaned:
        return False

    if cleaned.count("summary:") > 1 or cleaned.count("key points:") > 1 or cleaned.count("explanation:") > 1:
        return True

    sentences = [re.sub(r"\s+", " ", s).strip().lower() for s in _split_sentences(cleaned) if s.strip()]
    if len(sentences) >= 2 and len(set(sentences)) < len(sentences):
        return True

    words = re.findall(r"[a-z0-9]+", cleaned)
    if len(words) >= 20:
        ngram_counts: dict[str, int] = {}
        for idx in range(0, len(words) - 4):
            key = " ".join(words[idx:idx + 5])
            ngram_counts[key] = ngram_counts.get(key, 0) + 1
            if ngram_counts[key] >= 3:
                return True

    return False


def _format_context(context: str) -> str:
    raw_context = str(context or "")
    chunks = [c.strip() for c in raw_context.split("\n") if c.strip()]
    chunks = list(dict.fromkeys(chunks))
    if not chunks:
        return ""
    return "\n---\n".join(chunks)


def clean_sentences(text: str) -> str:
    sentences = str(text or "").split(". ")
    seen: set[str] = set()
    result: list[str] = []
    for sentence in sentences:
        key = sentence.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(sentence.strip())
    return ". ".join(result)


def clean_formatting(text: str) -> str:
    text = str(text or "")

    # remove markdown bold
    text = re.sub(r"\*\*", "", text)

    # normalize headers
    text = re.sub(r"Summary\s*:\s*", "Summary:\n", text)
    text = re.sub(r"Key Points\s*:\s*", "Key Points:\n", text)
    text = re.sub(r"Explanation\s*:\s*", "Explanation:\n", text)

    # remove duplicate headers
    text = re.sub(r"(Summary:\s*)+", "Summary:\n", text)
    text = re.sub(r"(Key Points:\s*)+", "Key Points:\n", text)
    text = re.sub(r"(Explanation:\s*)+", "Explanation:\n", text)

    # fix broken transitions
    text = re.sub(r"Key Points:\s*Explanation:", "Explanation:", text)

    # remove repeated lines
    lines = text.split("\n")
    seen: set[str] = set()
    clean_lines: list[str] = []

    for line in lines:
        lowered = line.strip().lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            clean_lines.append(line.strip())

    return "\n".join(clean_lines)


def _word_overlap_ratio(text_a: str, text_b: str) -> float:
    words_a = set(re.findall(r"[a-zA-Z0-9]+", text_a.lower()))
    words_b = set(re.findall(r"[a-zA-Z0-9]+", text_b.lower()))
    if not words_a or not words_b:
        return 0.0
    return float(len(words_a & words_b)) / float(max(1, len(words_a | words_b)))


def _string_similarity(text_a: str, text_b: str) -> float:
    left = re.sub(r"\s+", " ", str(text_a or "")).strip().lower()
    right = re.sub(r"\s+", " ", str(text_b or "")).strip().lower()
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    return float(SequenceMatcher(None, left, right).ratio())


def _is_similar(text_a: str, text_b: str, threshold: float = 0.7) -> bool:
    return _string_similarity(text_a, text_b) >= threshold


def _long_phrase_overlap(generated: str, context: str, window: int = 13) -> bool:
    context_words = re.findall(r"[a-zA-Z0-9]+", context.lower())
    if len(context_words) < window:
        return False

    context_ngrams = {
        " ".join(context_words[i : i + window])
        for i in range(0, len(context_words) - window + 1)
    }

    generated_words = re.findall(r"[a-zA-Z0-9]+", generated.lower())
    if len(generated_words) < window:
        return False

    for i in range(0, len(generated_words) - window + 1):
        phrase = " ".join(generated_words[i : i + window])
        if phrase in context_ngrams:
            return True
    return False


def _extract_sections(answer: str) -> tuple[str, list[str], str]:
    text = str(answer or "")
    summary_match = re.search(r"(?is)summary\s*:\s*(.*?)(?:\n\s*key points\s*:|$)", text)
    points_match = re.search(r"(?is)key points\s*:\s*(.*?)(?:\n\s*explanation\s*:|$)", text)
    explanation_match = re.search(r"(?is)explanation\s*:\s*(.*?)(?:\n\s*sources\s*:|$)", text)

    summary = summary_match.group(1).strip() if summary_match else ""
    explanation = explanation_match.group(1).strip() if explanation_match else ""

    key_points: list[str] = []
    if points_match:
        for line in points_match.group(1).split("\n"):
            candidate = line.strip().lstrip("-* ").strip()
            if candidate:
                key_points.append(candidate)

    return summary, key_points, explanation


def _build_distinct_fallback(context: str, query: str) -> str:
    return "\n".join([
        "Summary:",
        "I cannot find relevant information for this query in the provided documents.",
        "",
        "Key Points:",
        "- No matching content was found in the uploaded documents.",
        "- Try rephrasing your question or uploading a document that covers this topic.",
        "",
        "Explanation:",
        "The retrieval system searched the document corpus but did not find chunks"
        " sufficiently relevant to answer this question. This response is intentionally"
        " conservative to avoid presenting invented information as factual.",
    ])


def _build_fast_fallback(query: str, context: str, include_explanation: bool = True) -> str:
    fallback = _build_distinct_fallback(context=context, query=query)
    if include_explanation:
        return fallback

    summary, key_points, _ = _extract_sections(fallback)
    if not summary.strip():
        summary = "Information extracted from the provided context."
    if not key_points:
        key_points = ["Unable to generate additional details from context."]

    return "\n".join([summary] + [f"- {point}" for point in key_points])


def _ensure_explanation_quality(summary: str, explanation: str) -> str:
    summary_text = str(summary or "").strip()
    explanation_text = _clean_generated_answer(explanation)

    if _is_similar(explanation_text, summary_text, 0.7):
        explanation_text = ""

    sentence_count = len(_split_sentences(explanation_text))
    if not explanation_text or sentence_count < 2:
        explanation_text = (
            "The explanation is derived from the retrieved document context and may be limited "
            "when the source text is fragmented or sparse."
        )

    # Keep at most 3 sentences to stay concise but detailed.
    sentences = _split_sentences(explanation_text)
    if len(sentences) > 3:
        explanation_text = " ".join(sentences[:3])

    # If still too similar, force alternate generic wording.
    if _is_similar(explanation_text, summary_text, 0.7):
        explanation_text = (
            "The system identifies relevant statements in the retrieved context, "
            "combines them into a coherent narrative, and avoids unsupported assumptions. "
            "If source material is incomplete, the response remains conservative."
        )

    return explanation_text.strip()


def _strip_section_artifacts(text: str) -> str:
    cleaned = str(text or "").replace("\r", "").strip()
    cleaned = re.sub(r"(?is)^.*?summary\s*:\s*", "", cleaned)
    cleaned = re.sub(r"(?is)^.*?key\s*points\s*:\s*", "", cleaned)
    cleaned = re.sub(r"(?is)^.*?explanation\s*:\s*", "", cleaned)
    return _clean_generated_answer(cleaned)


def _normalize_summary(summary_text: str) -> str:
    cleaned = _strip_section_artifacts(summary_text)
    sentences = _split_sentences(cleaned)
    if not sentences:
        return ""
    return " ".join(sentences[:2]).strip()


def _normalize_key_points(points_text: str) -> list[str]:
    cleaned = _strip_section_artifacts(points_text)
    items: list[str] = []

    for line in cleaned.split("\n"):
        raw = line.strip()
        if not raw:
            continue
        bullet = re.sub(r"^[-*•\d\.)\s]+", "", raw).strip()
        if bullet:
            items.append(bullet)

    if not items:
        items = _split_sentences(cleaned)

    deduped: list[str] = []
    for item in items:
        if any(_is_similar(item, existing, 0.85) for existing in deduped):
            continue
        deduped.append(item)
        if len(deduped) >= 4:
            break

    return deduped


def _normalize_explanation(explanation_text: str) -> str:
    cleaned = _strip_section_artifacts(explanation_text)
    return cleaned.strip()


def _fill_missing_key_points(
    current_points: list[str],
    context: str,
    summary: str,
    explanation: str,
) -> list[str]:
    points = list(current_points)
    for sentence in _split_sentences(re.sub(r"\[Source:[^\]]*\]", " ", context)):
        candidate = sentence.strip()
        if len(candidate.split()) < 5:
            continue
        if _is_similar(candidate, summary, 0.7):
            continue
        if _is_similar(candidate, explanation, 0.7):
            continue
        if any(_is_similar(candidate, existing, 0.7) for existing in points):
            continue
        points.append(candidate)
        if len(points) >= 4:
            break
    return points


def _cross_check_sections(
    summary: str,
    key_points: list[str],
    explanation: str,
    context: str,
) -> tuple[str, list[str], str]:
    expl_sentences = _split_sentences(explanation)

    filtered_points: list[str] = []
    for point in key_points:
        if _is_similar(point, summary, 0.7):
            continue
        if any(_is_similar(point, sentence, 0.7) for sentence in expl_sentences):
            continue
        if any(_is_similar(point, existing, 0.7) for existing in filtered_points):
            continue
        filtered_points.append(point)

    filtered_expl_sentences: list[str] = []
    for sentence in expl_sentences:
        if _is_similar(sentence, summary, 0.7):
            continue
        if any(_is_similar(sentence, point, 0.7) for point in filtered_points):
            continue
        if any(_is_similar(sentence, existing, 0.85) for existing in filtered_expl_sentences):
            continue
        filtered_expl_sentences.append(sentence)

    filtered_explanation = " ".join(filtered_expl_sentences).strip()
    filtered_points = _fill_missing_key_points(
        current_points=filtered_points,
        context=context,
        summary=summary,
        explanation=filtered_explanation,
    )[:4]

    if not filtered_points:
        filtered_points = [
            "Core mechanism identified from the provided context.",
            "Information flow is guided by relevance between tokens.",
            "The model builds stronger representations from weighted interactions.",
        ]

    if not filtered_explanation:
        filtered_explanation = (
            "Step 1: Identify the most relevant parts of the input. "
            "Step 2: Assign stronger weight to relationships that matter more. "
            "Step 3: Combine weighted information to produce a clearer output."
        )

    if not summary.strip():
        summary = "This section gives a high-level view based on the provided context."

    return summary.strip(), filtered_points, filtered_explanation.strip()


def _generate_section_text(
    tokenizer: Any,
    model: Any,
    prompt: str,
    max_new_tokens: int,
) -> tuple[str, bool]:
    started = time.perf_counter()
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1500,
    )

    output = model.generate(
        **inputs,
        max_new_tokens=120,
        do_sample=False,
        num_beams=1,
        repetition_penalty=1.0,
    )

    prompt_token_count = inputs["input_ids"].shape[-1]
    generated_tokens = output[0][prompt_token_count:]
    decoded = tokenizer.decode(generated_tokens, skip_special_tokens=True)
    elapsed = time.perf_counter() - started
    timeout_hit = elapsed >= (SECTION_TIMEOUT_SECONDS - 0.05)
    return decoded, timeout_hit


def _format_sections(summary: str, key_points: list[str], explanation: str) -> str:
    bullets = key_points[:4] if key_points else ["Main idea extracted from the context."]
    body = [summary.strip()]
    body.extend(f"- {point.strip()}" for point in bullets)
    body.append(explanation.strip())
    return "\n".join(part for part in body if part)


def _post_check_sections(answer: str, context: str) -> str:
    summary, key_points, explanation = _extract_sections(answer)

    if not summary.strip() or not explanation.strip():
        return ""

    summary_sentences = _split_sentences(summary)
    explanation_sentences = _split_sentences(explanation)

    # Remove summary sentences that are repeated inside explanation.
    summary_norm = {re.sub(r"\s+", " ", s).lower() for s in summary_sentences}
    filtered_expl = [
        s for s in explanation_sentences
        if re.sub(r"\s+", " ", s).lower() not in summary_norm
    ]
    if filtered_expl:
        explanation = " ".join(filtered_expl)

    # Drop key points that duplicate explanation too strongly.
    dedup_points: list[str] = []
    for point in key_points:
        if _word_overlap_ratio(point, explanation) >= 0.9:
            continue
        if dedup_points and any(_word_overlap_ratio(point, existing) >= 0.9 for existing in dedup_points):
            continue
        dedup_points.append(point)

    # Reject repeated sentences globally.
    all_sentences = _split_sentences(" ".join([summary, " ".join(dedup_points), explanation]))
    normalized_all = [re.sub(r"\s+", " ", s).lower() for s in all_sentences]
    if len(normalized_all) != len(set(normalized_all)):
        return ""

    # Reject direct long copy from context.
    reconstructed = _format_sections(summary, dedup_points, explanation)
    if _long_phrase_overlap(reconstructed, context):
        return ""

    return reconstructed


def _get_model_and_tokenizer():
    global _tokenizer, _model

    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    with _model_load_lock:
        if _tokenizer is not None and _model is not None:
            return _tokenizer, _model

        try:
            logger.info("Loading TinyLlama...")

            model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

            _tokenizer = AutoTokenizer.from_pretrained(model_name)
            _tokenizer.pad_token = _tokenizer.eos_token

            _model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float32
            )

            _model.to("cpu")

            print(_model.generation_config)

            logger.info("MODEL LOADED SUCCESSFULLY")

            return _tokenizer, _model

        except Exception as e:
            import traceback
            logger.exception("MODEL LOAD ERROR")
            traceback.print_exc()
            raise


def generate_answer_local(query: str, context: str) -> str:
    try:
        tokenizer, model = _get_model_and_tokenizer()

        raw_context = str(context or "").strip()
        if not raw_context:
            raw_context = "Use best available information."

        top_chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n+", raw_context) if chunk.strip()][:4]
        safe_context = "\n\n".join(top_chunks)
        if not safe_context:
            safe_context = raw_context

        # Relaxed cleaning: remove only full-line headers, keep sentence content intact.
        header_lines = {
            "design and operation of a modern smart city infrastructure",
            "smart city infrastructure report",
            "technical reference document",
        }
        clean_lines: list[str] = []
        for line in safe_context.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()
            if not stripped:
                clean_lines.append("")
                continue
            if lowered in header_lines:
                continue
            if lowered.startswith("[source:"):
                continue
            clean_lines.append(stripped)
        safe_context = "\n".join(clean_lines).strip()

        # remove HTML tags
        safe_context = re.sub(r"<[^>]+>", " ", safe_context)

        # remove leftover broken tags like 'br>'
        safe_context = re.sub(r"\bbr>\b", " ", safe_context)

        safe_context = re.sub(r"\s+", " ", safe_context).strip()

        # TinyLlama prompt budget: ~1500 tokens total. Context gets 1200 chars (~300 tokens),
        # leaving room for the question, prompt template, and generated answer.
        safe_context = safe_context[:1200]

        RAG_PROMPT = """Answer the question clearly using the context.

        Context:
        {context}
 
        Question:
        {question}

        Give a clear, structured answer with:
        - A short summary (1-2 lines)
        - 2-3 key points
        - A simple explanation

        Do not repeat headings.
        Do not leave sections empty.
        Keep it natural.
        """

        prompt = RAG_PROMPT.format(context=safe_context, question=query)
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=1500,
        )
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        # Generate output (deterministic)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=120,
                do_sample=False,
                num_beams=1,
                repetition_penalty=1.0,
                use_cache=True,
            )

        # CRITICAL: remove prompt tokens from output
        input_length = inputs["input_ids"].shape[1]
        generated_tokens = output[0][input_length:]

        # Decode ONLY generated text
        answer = tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True
        ).strip()

        # remove leading Q/A only if present
        if answer.lower().startswith("q:"):
            parts = answer.split("a:", 1)
            if len(parts) == 2:
                answer = parts[1]

        # remove standalone labels
        answer = re.sub(r"(?i)\bq\s*:\s*", "", answer)
        answer = re.sub(r"(?i)\ba\s*:\s*", "", answer)

        # remove junk phrase
        answer = re.sub(r"(?i)retrieval[- ]based question answering system", "", answer)

        # normalize whitespace
        answer = re.sub(r"\s+", " ", answer).strip()

        # SAFETY: only fallback for empty output
        if not answer:
            return "Not enough relevant information found."

        logger.debug("[DEBUG] CLEAN LLM OUTPUT: %s", answer)

        text = answer.strip()

        if not text:
            return "Not enough relevant information found."

        raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        sentences: list[str] = []
        seen_sentences: set[str] = set()
        for sentence in raw_sentences:
            normalized_sentence = sentence.lower().strip()
            if normalized_sentence in seen_sentences:
                continue
            seen_sentences.add(normalized_sentence)
            sentences.append(sentence)

        if not sentences:
            sentences = [text]

        if len(sentences) == 1:
            summary = sentences[0]
            points = []
            explanation = sentences[0]
        elif len(sentences) <= 3:
            summary = sentences[0]
            points = sentences[1:]
            explanation = " ".join(sentences[1:])
        else:
            summary = sentences[0]
            points = sentences[1:4]
            explanation = " ".join(sentences[4:])

        return f"""Summary:
{summary}

Key Points:
{chr(10).join(f"* {p}" for p in points)}

Explanation:
{explanation}
"""

    except Exception as e:
        import traceback
        logger.exception("[LLM ERROR] %s", e)
        traceback.print_exc()
        return "Not enough relevant information found."


def generate_answer_openrouter(query: str, context: str) -> str:
    import os, requests, json

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    if not api_key:
        raise ValueError("OPENROUTER_API_KEY missing")

    prompt = f"""You are a precise assistant that answers questions using ONLY the provided context.

RULES:
- Answer in detail using information from the context below.
- Explain thoroughly in 3-5 sentences minimum.
- Use bullet points for lists or multiple points.
- If the answer is NOT in the context, say: "I cannot find this in the provided document."
- Never make up information.

Context:
{context[:8000]}

Question: {query}

Detailed Answer:"""

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),  # IMPORTANT: use data, not json
        timeout=20,
    )

    logger.debug("[OPENROUTER] Response status=%s", r.status_code)
    logger.debug("[OPENROUTER] Response preview=%s", r.text[:200])

    r.raise_for_status()

    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_answer(query: str, context: str) -> str:
    use_openrouter = os.getenv("USE_OPENROUTER", "").strip().lower()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if use_openrouter == "true":
        if not openrouter_key:
            logger.warning("[LLM] USE_OPENROUTER=true but OPENROUTER_API_KEY is not set")
            return (
                "LLM is not configured. "
                "Set OPENROUTER_API_KEY in backend/.env to enable answer generation."
            )
        try:
            answer = generate_answer_openrouter(query, context)
            if answer:
                return answer
        except Exception as exc:
            logger.warning("[OPENROUTER FAILED] %s", exc)
            return (
                "Answer generation is temporarily unavailable (OpenRouter request failed). "
                "Please try again in a moment."
            )

    # Local model path — only taken when USE_OPENROUTER is not 'true'.
    # TinyLlama requires ~4GB RAM. If unavailable, it will crash the process with SIGSEGV.
    # Only attempt it when disk and RAM are actually available.
    return generate_answer_local(query, context)


def _preload_model_once() -> None:
    try:
        _get_model_and_tokenizer()
    except Exception as exc:
        logger.warning("Model preload skipped: %s", exc)

