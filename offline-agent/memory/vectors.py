"""
vectors.py – Embedding, chunking, and cosine similarity search.

Design:
  - Embedding is done via Ollama's /api/embeddings endpoint
    (model: nomic-embed-text, 768-dim, runs on CPU, ~50 ms/chunk).
  - Vectors are stored as raw float32 bytes in SQLite (no extra DB).
  - Search is brute-force cosine similarity over NumPy arrays.
    Fast enough for tens of thousands of chunks on CPU.
  - Chunking: Python source is split by top-level def/class boundaries
    (simple regex, no tree-sitter dependency yet).
    Non-Python files fall back to fixed windows with overlap.

Public API:
  embed(text)                     -> np.ndarray  (768,) float32
  chunk_code(text, path)          -> list[dict]  each has text/start_line/end_line/ord
  chunk_text(text)                -> list[dict]
  cosine_search(query_vec, rows, top_k) -> list[dict]  sorted by score desc

Usage as a script (index a directory):
  python -m memory.vectors index <directory> [--db data/memory.db] [--source myrepo]
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import requests

# ── Ollama embedding config ───────────────────────────────────────────────────

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

# Chunking constants
CHUNK_LINES = 40          # target lines per chunk for prose / fallback
CHUNK_OVERLAP = 8         # overlap between consecutive prose chunks
MAX_CHUNK_CHARS = 2000    # hard cap: very large chunks are split further


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed(text: str, model: str = EMBED_MODEL) -> np.ndarray:
    """
    Call Ollama /api/embeddings and return a normalised float32 vector.

    Raises requests.HTTPError / requests.ConnectionError on failure.
    """
    r = requests.post(
        f"{OLLAMA}/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=120,
    )
    r.raise_for_status()
    vec = np.array(r.json()["embedding"], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def embed_to_bytes(text: str, model: str = EMBED_MODEL) -> bytes:
    """Embed *text* and return the vector as raw bytes (for SQLite storage)."""
    return embed(text, model).tobytes()


def bytes_to_vec(b: bytes) -> np.ndarray:
    """Deserialise a float32 vector from raw bytes."""
    return np.frombuffer(b, dtype=np.float32).copy()


# ── Chunking ──────────────────────────────────────────────────────────────────

# Matches the start of a top-level Python function or class definition.
_PY_BOUNDARY = re.compile(r"^(def |class )", re.MULTILINE)


def chunk_code(text: str, path: str = "") -> list[dict]:
    """
    Split Python source into chunks at top-level def/class boundaries.

    Falls back to chunk_text for non-.py files or files with no boundaries.
    Each returned dict: {text, ord, start_line, end_line}.
    """
    if not path.endswith(".py"):
        return chunk_text(text)

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    # Find line numbers where top-level defs/classes start.
    boundary_lines: list[int] = []
    for i, line in enumerate(lines):
        if _PY_BOUNDARY.match(line):
            boundary_lines.append(i)

    if not boundary_lines:
        return chunk_text(text)

    # Build segments: [0 .. first_boundary), then each boundary to the next.
    starts = [0] + boundary_lines
    ends = boundary_lines + [len(lines)]

    chunks: list[dict] = []
    for ord_idx, (s, e) in enumerate(zip(starts, ends)):
        segment = "".join(lines[s:e]).strip()
        if not segment:
            continue
        # If segment is very large, sub-chunk it with the prose chunker.
        if len(segment) > MAX_CHUNK_CHARS:
            sub = chunk_text(segment)
            for sub_c in sub:
                sub_c["start_line"] += s
                sub_c["end_line"] += s
                sub_c["ord"] = len(chunks)
                chunks.append(sub_c)
        else:
            chunks.append({
                "text": segment,
                "ord": len(chunks),
                "start_line": s,
                "end_line": e - 1,
            })
    return chunks


def chunk_text(text: str,
               chunk_lines: int = CHUNK_LINES,
               overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Split *text* into fixed-size windows with overlap.

    Each returned dict: {text, ord, start_line, end_line}.
    """
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    chunks: list[dict] = []
    step = max(1, chunk_lines - overlap)
    i = 0
    while i < len(lines):
        window = lines[i: i + chunk_lines]
        segment = "".join(window).strip()
        if segment:
            chunks.append({
                "text": segment,
                "ord": len(chunks),
                "start_line": i,
                "end_line": min(i + chunk_lines, len(lines)) - 1,
            })
        i += step
    return chunks


# ── Similarity search ─────────────────────────────────────────────────────────

def cosine_search(
    query_vec: np.ndarray,
    rows: list[tuple[int, bytes, str, int, int]],
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[dict]:
    """
    Brute-force cosine similarity search.

    Args:
        query_vec: normalised float32 query vector.
        rows:      list of (chunk_id, vector_bytes, text, start_line, end_line)
                   as returned by DB.all_embeddings().
        top_k:     number of results to return.
        min_score: minimum similarity threshold (default 0.0). Results with
                   score < min_score are excluded.

    Returns list of dicts sorted by score descending:
        {chunk_id, score, text, start_line, end_line}
    """
    if not rows:
        return []

    ids, vecs, texts, starts, ends = [], [], [], [], []
    for chunk_id, vector_bytes, text, start_line, end_line in rows:
        ids.append(chunk_id)
        vecs.append(bytes_to_vec(vector_bytes))
        texts.append(text)
        starts.append(start_line)
        ends.append(end_line)

    matrix = np.stack(vecs)           # (N, D)
    scores = matrix @ query_vec       # cosine similarity (vectors are normalised)

    top_indices = np.argsort(scores)[::-1]
    results = []
    for i in top_indices:
        score = float(scores[i])
        if score < min_score:
            break
        results.append({
            "chunk_id": ids[i],
            "score": score,
            "text": texts[i],
            "start_line": starts[i],
            "end_line": ends[i],
        })
        if len(results) >= top_k:
            break
    return results


# ── Indexer ───────────────────────────────────────────────────────────────────

# File extensions to index as code
_CODE_EXTS = {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
# File extensions to index as prose/docs
_DOC_EXTS  = {".md", ".txt", ".rst"}


def index_directory(
    directory: str,
    db,
    source: str = "",
    embed_model: str = EMBED_MODEL,
    verbose: bool = True,
) -> dict:
    """
    Walk *directory*, chunk every .py / .md file, embed each chunk, and
    store everything in *db*.  Already-indexed unchanged files are skipped.

    Returns a summary dict: {indexed, skipped, chunks, errors}.
    """
    import hashlib

    root = Path(directory).resolve()
    source = source or root.name
    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "errors": 0}

    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        ext = fpath.suffix.lower()
        if ext not in _CODE_EXTS and ext not in _DOC_EXTS:
            continue
        # Skip hidden dirs, __pycache__, .venv, data/, eval/, etc.
        rel_parts = fpath.relative_to(root).parts
        if any(p.startswith(".") or p in {"__pycache__", ".venv", "node_modules", "data", "eval"}
               for p in rel_parts):
            continue

        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            if verbose:
                print(f"  ERROR reading {fpath}: {e}")
            stats["errors"] += 1
            continue

        content_hash = hashlib.sha1(text.encode()).hexdigest()
        kind = "code" if ext in _CODE_EXTS else "doc"
        path_str = str(fpath)

        doc_id, is_new = db.upsert_document(path_str, source, kind, content_hash)
        if not is_new:
            stats["skipped"] += 1
            if verbose:
                print(f"  skip  {fpath.relative_to(root)}  (unchanged)")
            continue

        # Chunk
        chunks = chunk_code(text, path_str) if ext in _CODE_EXTS else chunk_text(text)
        if not chunks:
            stats["skipped"] += 1
            continue

        chunk_ids = db.insert_chunks(doc_id, chunks)

        # Embed each chunk
        embedded = 0
        for cid, chunk in zip(chunk_ids, chunks):
            try:
                vec_bytes = embed_to_bytes(chunk["text"], embed_model)
                db.insert_embedding(cid, embed_model, vec_bytes)
                embedded += 1
            except Exception as e:
                if verbose:
                    print(f"    embed error chunk {cid}: {e}")
                stats["errors"] += 1

        stats["indexed"] += 1
        stats["chunks"] += embedded
        if verbose:
            print(f"  index {fpath.relative_to(root)}  "
                  f"({len(chunks)} chunks, {embedded} embedded)")

    return stats


# ── CLI entry-point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from memory.db import DB

    parser = argparse.ArgumentParser(description="Index a directory into vector memory")
    sub = parser.add_subparsers(dest="cmd")

    idx = sub.add_parser("index", help="Embed and store a directory")
    idx.add_argument("directory", help="Path to index")
    idx.add_argument("--db",     default="data/memory.db")
    idx.add_argument("--source", default="", help="Label for this repo/vault")
    idx.add_argument("--model",  default=EMBED_MODEL)

    search = sub.add_parser("search", help="Query the vector index")
    search.add_argument("query", help="Natural-language query")
    search.add_argument("--db",  default="data/memory.db")
    search.add_argument("--top", type=int, default=5)
    search.add_argument("--min-score", type=float, default=0.0,
                        help="Minimum similarity score threshold (e.g. 0.55)")
    search.add_argument("--model", default=EMBED_MODEL)

    args = parser.parse_args()

    if args.cmd == "index":
        db = DB(args.db)
        print(f"Indexing {args.directory} → {args.db}")
        stats = index_directory(args.directory, db,
                                source=args.source, embed_model=args.model)
        print(f"\nDone: {stats}")

    elif args.cmd == "search":
        db = DB(args.db)
        print(f"Embedding query with {args.model}...")
        qvec = embed(args.query, args.model)
        rows = db.all_embeddings()
        results = cosine_search(qvec, rows, top_k=args.top, min_score=args.min_score)
        print(f"\nTop {args.top} results for: {args.query!r} (min_score={args.min_score})\n")
        if not results:
            print("No matching results above threshold.")
        for i, r in enumerate(results, 1):
            path = db.chunk_path(r["chunk_id"]) or "?"
            print(f"[{i}] score={r['score']:.3f}  {path}  "
                  f"lines {r['start_line']}-{r['end_line']}")
            print(f"     {r['text'][:200].strip()!r}")
            print()

    else:
        parser.print_help()
        sys.exit(1)
