import ast
import os
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
load_dotenv(override=True)

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

CHROMA_PATH = os.getenv("CODE_CHROMA_PATH", str(Path(__file__).resolve().parent.parent / "code_chroma_db"))

ef = ONNXMiniLM_L6_V2()
_code_collection = None

def get_code_collection():
    global _code_collection
    if _code_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _code_collection = client.get_or_create_collection(
            "codebase", embedding_function=ef
        )
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
    except Exception:
        pass
    return chunks

def extract_chunks_from_file(filepath: str) -> List[Dict]:
    SKIP_EXTENSIONS = {
        '.pyc','.pyo','.pyd','.so','.dll','.exe','.bin',
        '.jpg','.jpeg','.png','.gif','.ico','.svg',
        '.pdf','.zip','.tar','.gz','.lock','.sum'
    }
    ext = os.path.splitext(filepath)[1].lower()
    if ext in SKIP_EXTENSIONS:
        return []
    if ext == '.py':
        return chunk_file_by_functions(filepath)
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return []
    if not lines or len(lines) > 5000:
        return []
    chunks = []
    chunk_size = 30
    overlap = 10
    i = 0
    while i < len(lines):
        chunk_lines = lines[i:i+chunk_size]
        text = ''.join(chunk_lines).strip()
        if text:
            chunks.append({
                "file": filepath,
                "function": f"lines_{i+1}_{min(i+chunk_size,len(lines))}",
                "text": text,
                "start_line": i,
                "end_line": min(i+chunk_size, len(lines)),
            })
        i += chunk_size - overlap
    return chunks

def index_codebase(root_dir: str):
    SKIP_DIRS = {'.git','__pycache__','node_modules',
                 '.venv','venv','env','.env','dist',
                 'build','.next','coverage'}
    collection = get_code_collection()
    all_chunks = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            all_chunks.extend(extract_chunks_from_file(fpath))
    for i in range(0, len(all_chunks), 100):
        batch = all_chunks[i:i+100]
        collection.upsert(
            ids=[f"{c['file']}::{c['function']}" for c in batch],
            documents=[c['text'] for c in batch],
            metadatas=[{"file": c['file'], "function": c['function']} for c in batch]
        )

def retrieve_similar_code(query: str, top_k: int = 5) -> List[Dict]:
    """Retrieve similar code chunks for a query."""
    collection = get_code_collection()

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
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

def extract_modules_from_diff(diff: str) -> Dict:
    """Extract touched file paths and module names from a PR diff."""
    import re
    modules = set()
    files = set()

    for line in diff.split("\n"):
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line.replace("+++ b/", "").replace("--- a/", "").strip()
            if path and path != "/dev/null":
                files.add(path)
                parts = [p for p in path.split("/")
                         if p and not p.startswith(".")
                         and not p.endswith(".py")
                         and p not in ["a", "b", "src", "lib"]]
                modules.update(parts[:3])

    return {"modules": list(modules), "files": list(files)}
