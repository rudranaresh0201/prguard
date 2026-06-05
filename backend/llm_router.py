from .llm import generate_answer as llm_generate


def generate_answer(query: str, context: str) -> str:
    return llm_generate(query, str(context or ""))
