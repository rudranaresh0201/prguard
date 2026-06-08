import ast
import os
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
load_dotenv(override=True)

import chromadb
from sentence_transformers import SentenceTransformer

EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
CHROMA_PATH = os.getenv("CODE_CHROMA_PATH", str(Path(__file__).resolve().parent.parent / "code_chroma_db"))

_embedder = None
_code_collection = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder

def get_code_collection():
    global _code_collection
    if _code_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _code_collection = client.get_or_create_collection("codebase")
    return _code_collection

def chunk_file_by_functions(filepath: str) -> List[Dict]:
    """Parse a Python file and chunk at function/class level using AST."""
    chunks = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
        if not source.strip():
            return []
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                segment = ast.get_source_segment(source, node)
                if segment and len(segment.split()) > 5:
                    chunks.append({
                        "text": segment,
                        "function": node.name,
                        "file": filepath,
                        "line": node.lineno,
                        "type": "class" if isinstance(node, ast.ClassDef) else "function"
                    })
    except Exception as e:
        pass
    return chunks

def index_repository(repo_path: str = ".") -> int:
    """Index all Python files in the repository at function level."""
    collection = get_code_collection()
    embedder = get_embedder()

    py_files = list(Path(repo_path).rglob("*.py"))
    # Skip test files, migrations, venv
    py_files = [f for f in py_files if not any(
        skip in str(f) for skip in ["__pycache__", ".venv", "venv", "node_modules", "migrations"]
    )]

    total = 0
    for filepath in py_files:
        chunks = chunk_file_by_functions(str(filepath))
        for i, chunk in enumerate(chunks):
            chunk_id = f"{filepath}:{chunk['function']}:{chunk['line']}"
            text = f"File: {chunk['file']}\nFunction: {chunk['function']}\n\n{chunk['text']}"
            embedding = embedder.encode(
                text, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
            collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk["text"]],
                metadatas=[{
                    "file": chunk["file"],
                    "function": chunk["function"],
                    "line": chunk["line"],
                    "type": chunk["type"]
                }]
            )
            total += 1
    return total

def retrieve_similar_code(query: str, top_k: int = 5) -> List[Dict]:
    """Retrieve similar code chunks for a query."""
    collection = get_code_collection()
    embedder = get_embedder()

    if collection.count() == 0:
        return []

    embedding = embedder.encode(
        query, normalize_embeddings=True, show_progress_bar=False
    ).tolist()

    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, distances):
        chunks.append({
            "text": doc,
            "file": meta.get("file", ""),
            "function": meta.get("function", ""),
            "score": round(1 - dist/2, 3)
        })
    return chunks

def extract_modules_from_diff(diff: str) -> List[str]:
    """Extract touched module names from a PR diff."""
    modules = set()
    for line in diff.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            parts = line.split("/")
            if len(parts) > 1:
                for part in parts:
                    if part and not part.startswith(".") and "." not in part:
                        modules.add(part.lower())
    return list(modules)[:5]
