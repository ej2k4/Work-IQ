"""
phase2_eval.py – Phase 2 evaluation harness for memory and vector retrieval.

Tests the Phase 2 gate from plan.md:
  "On a repo the agent has not seen, 20 'where is X handled?' questions
   score higher with retrieval than without."

Protocol:
  1. Build an unseen 16-file benchmark repository in data/bench_repo.
  2. Index and embed all chunks into data/bench_memory.db via nomic-embed-text.
  3. Precompute vector search for all 20 benchmark questions (embedding model loaded once).
  4. Run model evaluations (qwen2.5-coder loaded once):
     - Condition A (Without Retrieval): Model answers given only the file list.
     - Condition B (With Retrieval): Model answers given the top-3 retrieved snippets.
  5. Compare accuracies and judge Phase 2 gate.

Usage:
    python -m eval.phase2_eval
    python -m eval.phase2_eval --model qwen2.5-coder:3b
    python -m eval.phase2_eval --retrieval-only
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.llm import chat, DEFAULT_MODEL
from eval.bench_repo import BENCH_FILES, QUESTIONS, build_bench_repo
from memory.db import DB
from memory.vectors import embed, cosine_search, index_directory

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = _PROJECT_ROOT / "data" / "bench_repo"
BENCH_DB_PATH = _PROJECT_ROOT / "data" / "bench_memory.db"


def normalize_path(p: str) -> str:
    """Normalize file path for cross-platform comparison."""
    return p.replace("\\", "/").strip().lower()


def retrieve_for_questions(questions: list[dict], file_list: list[str], db: DB) -> list[dict]:
    """
    Run vector retrieval for all questions in one batch while embed model is loaded.
    """
    rows = db.all_embeddings()
    retrieval_results = []

    for q in questions:
        query = q["query"]
        expected = normalize_path(q["expected_file"])

        qvec = embed(query)
        search_results = cosine_search(qvec, rows, top_k=5, min_score=0.0)

        retrieved_files = []
        top_snippets = []
        for r in search_results:
            raw_path = db.chunk_path(r["chunk_id"]) or ""
            norm_p = normalize_path(raw_path)
            for rel in file_list:
                if normalize_path(rel) in norm_p:
                    norm_p = normalize_path(rel)
                    break
            retrieved_files.append(norm_p)
            top_snippets.append(
                f"File: {norm_p} (lines {r['start_line']}-{r['end_line']}, score: {r['score']:.3f})\n"
                f"```python\n{r['text'].strip()[:350]}\n```"
            )

        top1_match = len(retrieved_files) > 0 and expected in retrieved_files[0]
        top3_match = any(expected in rf for rf in retrieved_files[:3])
        rank = 0
        for idx, rf in enumerate(retrieved_files, 1):
            if expected in rf:
                rank = idx
                break
        rr = 1.0 / rank if rank > 0 else 0.0

        retrieval_results.append({
            "id": q["id"],
            "query": query,
            "expected": q["expected_file"],
            "top1_match": top1_match,
            "top3_match": top3_match,
            "rank": rank,
            "rr": rr,
            "top1_retrieved": retrieved_files[0] if retrieved_files else "none",
            "top_snippets": top_snippets,
            "without_retrieval_correct": False,
            "with_retrieval_correct": False,
            "without_retrieval_ans": "",
            "with_retrieval_ans": "",
        })

    return retrieval_results


def main():
    p = argparse.ArgumentParser(description="Phase 2 Memory & Retrieval Evaluation")
    p.add_argument("--model", default=None,
                   help="Ollama model name (default: qwen2.5-coder:3b)")
    p.add_argument("--retrieval-only", action="store_true",
                   help="Only evaluate vector search rankings without calling LLM")
    p.add_argument("--reindex", action="store_true",
                   help="Force rebuild and re-index of benchmark repo")
    a = p.parse_args()

    model = a.model or DEFAULT_MODEL

    print("=" * 65, flush=True)
    print("  PHASE 2 EVALUATION: MEMORY & VECTOR RETRIEVAL GATE", flush=True)
    print("=" * 65, flush=True)
    print(f"Model:          {model}", flush=True)
    print(f"Benchmark repo: {BENCH_DIR}", flush=True)
    print(f"Benchmark DB:   {BENCH_DB_PATH}", flush=True)

    # 1. Build benchmark repository
    if a.reindex or not BENCH_DIR.exists():
        if BENCH_DIR.exists():
            shutil.rmtree(BENCH_DIR)
        BENCH_DIR.mkdir(parents=True, exist_ok=True)
        file_list = build_bench_repo(BENCH_DIR)
        print(f"Built {len(file_list)} benchmark files in {BENCH_DIR}", flush=True)
    else:
        file_list = list(BENCH_FILES.keys())

    # 2. Index into benchmark DB
    if a.reindex or not BENCH_DB_PATH.exists():
        if BENCH_DB_PATH.exists():
            BENCH_DB_PATH.unlink()
        db = DB(str(BENCH_DB_PATH))
        print("Indexing benchmark repository into vector memory...", flush=True)
        stats = index_directory(str(BENCH_DIR), db, source="bench_repo", verbose=False)
        print(f"Indexing complete: {stats}", flush=True)
    else:
        db = DB(str(BENCH_DB_PATH))

    total_embeddings = db.con.execute("SELECT count(*) FROM embeddings").fetchone()[0]
    print(f"Indexed chunks in memory: {total_embeddings}", flush=True)
    print("-" * 65, flush=True)

    # 3. Batch Vector Retrieval (keeps nomic-embed-text loaded once)
    print(f"Stage 1: Vector Retrieval across {len(QUESTIONS)} questions...", flush=True)
    t0 = time.time()
    results = retrieve_for_questions(QUESTIONS, file_list, db)
    t_retrieval = time.time() - t0
    print(f"Vector retrieval finished in {t_retrieval:.1f}s", flush=True)

    n = len(results)
    top1_count = sum(1 for r in results if r["top1_match"])
    top3_count = sum(1 for r in results if r["top3_match"])
    mrr = sum(r["rr"] for r in results) / n

    for r in results:
        mark = "[OK]" if r["top1_match"] else ("[TOP3]" if r["top3_match"] else "[X]")
        print(f"  [{r['id']:02d}] {mark:<7} rank={r['rank']:<2} expected: {r['expected']:<24} got: {r['top1_retrieved']}", flush=True)

    print("\n" + "=" * 65, flush=True)
    print("VECTOR RETRIEVAL PERFORMANCE", flush=True)
    print("=" * 65, flush=True)
    print(f"Vector Retrieval Top-1 Accuracy: {top1_count}/{n} ({top1_count/n*100:.1f}%)", flush=True)
    print(f"Vector Retrieval Top-3 Accuracy: {top3_count}/{n} ({top3_count/n*100:.1f}%)", flush=True)
    print(f"Mean Reciprocal Rank (MRR):      {mrr:.3f}", flush=True)

    if a.retrieval_only:
        gate_passed = top1_count / n >= 0.80
        status_str = "PASS" if gate_passed else "FAIL"
        print("-" * 65, flush=True)
        print(f"Phase 2 Retrieval Gate (Top-1 >= 80%): {status_str}", flush=True)
        return

    # 4. LLM Comparisons (loads qwen2.5-coder once for all questions)
    print("\n" + "=" * 65, flush=True)
    print(f"Stage 2: Model Inference ({model}) - Without Retrieval vs With Retrieval", flush=True)
    print("=" * 65, flush=True)
    files_str = "\n".join(f"- {f}" for f in file_list)

    for r in results:
        query = r["query"]
        expected = normalize_path(r["expected"])

        # Without Retrieval
        prompt_no_rag = (
            f"You are inspecting a Python codebase containing the following files:\n"
            f"{files_str}\n\n"
            f"Question: {query}\n"
            f"Which single file handles this? Reply with ONLY the file path (e.g. 'auth/tokens.py') and nothing else."
        )
        try:
            ans_no = chat([{"role": "user", "content": prompt_no_rag}], model=model, json_mode=False).strip()
        except Exception as e:
            ans_no = f"ERROR: {e}"
        no_rag_correct = expected in normalize_path(ans_no)

        # With Retrieval
        context_str = "\n\n".join(r["top_snippets"][:3])
        prompt_rag = (
            f"You are inspecting a Python codebase containing the following files:\n"
            f"{files_str}\n\n"
            f"Here are the most relevant retrieved code snippets from the codebase:\n"
            f"{context_str}\n\n"
            f"Question: {query}\n"
            f"Which single file handles this? Reply with ONLY the file path (e.g. 'auth/tokens.py') and nothing else."
        )
        try:
            ans_rag = chat([{"role": "user", "content": prompt_rag}], model=model, json_mode=False).strip()
        except Exception as e:
            ans_rag = f"ERROR: {e}"
        rag_correct = expected in normalize_path(ans_rag)

        r["without_retrieval_correct"] = no_rag_correct
        r["with_retrieval_correct"] = rag_correct
        r["without_retrieval_ans"] = ans_no.replace("\n", " ")[:60]
        r["with_retrieval_ans"] = ans_rag.replace("\n", " ")[:60]

        mark_no = "[OK]" if no_rag_correct else "[X]"
        mark_rag = "[OK]" if rag_correct else "[X]"
        print(f"[{r['id']:02d}] No-RAG: {mark_no:<4} | RAG: {mark_rag:<4} | expected: {r['expected']:<22} | RAG ans: {r['with_retrieval_ans'][:30]}", flush=True)

    no_rag_count = sum(1 for r in results if r["without_retrieval_correct"])
    rag_count = sum(1 for r in results if r["with_retrieval_correct"])

    print("\n" + "=" * 65, flush=True)
    print("PHASE 2 GATE COMPARISON SUMMARY", flush=True)
    print("=" * 65, flush=True)
    print(f"Without Retrieval (File-list only): {no_rag_count}/{n} ({no_rag_count/n*100:.1f}%)", flush=True)
    print(f"With Retrieval (Top-3 Chunks):      {rag_count}/{n} ({rag_count/n*100:.1f}%)", flush=True)
    print("-" * 65, flush=True)

    gate_passed = rag_count > no_rag_count and (rag_count / n >= 0.80)
    status_str = "PASS" if gate_passed else "FAIL"
    print(f"Phase 2 Gate (Retrieval > Baseline & >=80% pass): {status_str}", flush=True)
    print(f"Improvement: +{(rag_count - no_rag_count)/n*100:+.1f}% accuracy with memory retrieval", flush=True)


if __name__ == "__main__":
    main()
