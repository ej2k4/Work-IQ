"""
phase3_eval.py – Phase 3 evaluation harness for code graph and hybrid retrieval.

Tests the Phase 3 gate from plan.md:
  "Hybrid retrieval beats vector-only on multi-file questions such as
   'what breaks if I change function Y?'"

Protocol:
  1. Build the benchmark repository with cross-file dependencies in data/phase3_repo.
  2. Index into data/phase3_memory.db:
     - Vector indexing: chunks & embeddings via nomic-embed-text.
     - Graph indexing: AST parsing of classes, functions, calls, imports.
  3. Compare Vector-Only Retrieval vs Hybrid (Vector + Graph) Retrieval across
     10 multi-file impact questions ("What breaks if I change function Y?").
  4. Measure caller file recall:
     - Recall of ground-truth caller files in top retrieved context.
  5. Compare Model (qwen2.5-coder) identification accuracy under both contexts.
  6. Judge Phase 3 Gate: Hybrid > Vector-only.

Usage:
    python -m eval.phase3_eval
    python -m eval.phase3_eval --model qwen2.5-coder:3b
    python -m eval.phase3_eval --retrieval-only
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
from eval.phase3_bench import FILES, IMPACT_QUESTIONS, build_phase3_repo
from memory.db import DB
from memory.graph import index_repository_graph, load_graph, find_impact
from memory.vectors import embed, cosine_search, index_directory

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3_DIR = _PROJECT_ROOT / "data" / "phase3_repo"
PHASE3_DB_PATH = _PROJECT_ROOT / "data" / "phase3_memory.db"


def normalize_path(p: str) -> str:
    """Normalize file path for cross-platform comparison."""
    return p.replace("\\", "/").strip().lower()


def evaluate_retrieval(questions: list[dict], file_list: list[str], db: DB) -> list[dict]:
    """
    Evaluate caller file recall: Vector-Only vs Hybrid (Vector + Graph).
    """
    rows = db.all_embeddings()
    G = load_graph(db)
    results = []

    for q in questions:
        target = q["target_function"]
        expected_callers = [normalize_path(f) for f in q["expected_callers"]]

        # ── 1. Vector-Only Retrieval ──────────────────────────────────────────
        qvec = embed(q["query"])
        # Top-5 vector search chunks
        vec_search = cosine_search(qvec, rows, top_k=5, min_score=0.0)

        vec_files = set()
        vec_snippets = []
        for r in vec_search:
            raw_path = db.chunk_path(r["chunk_id"]) or ""
            norm_p = normalize_path(raw_path)
            for rel in file_list:
                if normalize_path(rel) in norm_p:
                    norm_p = normalize_path(rel)
                    break
            vec_files.add(norm_p)
            vec_snippets.append(
                f"File: {norm_p} (lines {r['start_line']}-{r['end_line']})\n"
                f"```python\n{r['text'].strip()[:280]}\n```"
            )

        # Vector recall: how many expected callers were found?
        vec_hits = [c for c in expected_callers if any(c in vf for vf in vec_files)]
        vec_recall = len(vec_hits) / len(expected_callers) if expected_callers else 1.0

        # ── 2. Hybrid Retrieval (Vector + Graph) ──────────────────────────────
        # Use graph to find all callers and dependents of target function
        impacted_nodes = find_impact(G, target, max_hops=2)

        hybrid_files = set(vec_files)
        graph_snippets = []

        for item in impacted_nodes:
            ref = item.get("ref", "")
            raw_p = ref.split(":")[0] if ":" in ref else ref
            norm_p = normalize_path(raw_p)
            for rel in file_list:
                if normalize_path(rel) in norm_p:
                    norm_p = normalize_path(rel)
                    break
            hybrid_files.add(norm_p)
            graph_snippets.append(
                f"[GRAPH DEPENDENT] {item.get('kind')} '{item.get('name')}' in {norm_p} (ref: {ref})"
            )

        # Hybrid recall: how many expected callers were found?
        hybrid_hits = [c for c in expected_callers if any(c in hf for hf in hybrid_files)]
        hybrid_recall = len(hybrid_hits) / len(expected_callers) if expected_callers else 1.0

        results.append({
            "id": q["id"],
            "target": target,
            "query": q["query"],
            "expected_callers": q["expected_callers"],
            "vec_files": list(vec_files),
            "hybrid_files": list(hybrid_files),
            "vec_hits": len(vec_hits),
            "hybrid_hits": len(hybrid_hits),
            "total_callers": len(expected_callers),
            "vec_recall": vec_recall,
            "hybrid_recall": hybrid_recall,
            "vec_snippets": vec_snippets,
            "graph_snippets": graph_snippets,
            "vec_model_correct": False,
            "hybrid_model_correct": False,
            "vec_model_ans": "",
            "hybrid_model_ans": "",
        })

    return results


def main():
    p = argparse.ArgumentParser(description="Phase 3 Code Graph & Hybrid Retrieval Evaluation")
    p.add_argument("--model", default=None,
                   help="Ollama model name (default: qwen2.5-coder:3b)")
    p.add_argument("--retrieval-only", action="store_true",
                   help="Only evaluate retrieval recall without calling LLM")
    p.add_argument("--reindex", action="store_true",
                   help="Force rebuild and re-index of benchmark repo")
    a = p.parse_args()

    model = a.model or DEFAULT_MODEL

    print("=" * 65, flush=True)
    print("  PHASE 3 EVALUATION: CODE GRAPH & HYBRID RETRIEVAL GATE", flush=True)
    print("=" * 65, flush=True)
    print(f"Model:          {model}", flush=True)
    print(f"Benchmark repo: {PHASE3_DIR}", flush=True)
    print(f"Benchmark DB:   {PHASE3_DB_PATH}", flush=True)

    # 1. Build benchmark repository
    if a.reindex or not PHASE3_DIR.exists():
        if PHASE3_DIR.exists():
            shutil.rmtree(PHASE3_DIR)
        PHASE3_DIR.mkdir(parents=True, exist_ok=True)
        file_list = build_phase3_repo(PHASE3_DIR)
        print(f"Built {len(file_list)} files in {PHASE3_DIR}", flush=True)
    else:
        file_list = list(FILES.keys())

    # 2. Index into benchmark DB (Vectors + Code Graph)
    if a.reindex or not PHASE3_DB_PATH.exists():
        if PHASE3_DB_PATH.exists():
            PHASE3_DB_PATH.unlink()
        db = DB(str(PHASE3_DB_PATH))
        print("Indexing benchmark repository into vector memory...", flush=True)
        vstats = index_directory(str(PHASE3_DIR), db, source="phase3_repo", verbose=False)
        print(f"Vector indexing: {vstats}", flush=True)

        print("Indexing code graph into SQLite nodes and edges...", flush=True)
        gstats = index_repository_graph(PHASE3_DIR, db, verbose=False)
        print(f"Graph indexing:  {gstats}", flush=True)
    else:
        db = DB(str(PHASE3_DB_PATH))

    total_embeddings = db.con.execute("SELECT count(*) FROM embeddings").fetchone()[0]
    total_nodes = db.con.execute("SELECT count(*) FROM nodes").fetchone()[0]
    total_edges = db.con.execute("SELECT count(*) FROM edges").fetchone()[0]
    print(f"Indexed chunks: {total_embeddings} | Graph nodes: {total_nodes} | Graph edges: {total_edges}", flush=True)
    print("-" * 65, flush=True)

    # 3. Stage 1: Retrieval Comparison
    print(f"Stage 1: Evaluating Multi-File Retrieval across {len(IMPACT_QUESTIONS)} questions...", flush=True)
    t0 = time.time()
    results = evaluate_retrieval(IMPACT_QUESTIONS, file_list, db)
    t_retrieval = time.time() - t0
    print(f"Retrieval evaluation finished in {t_retrieval:.1f}s\n", flush=True)

    for r in results:
        v_str = f"{r['vec_hits']}/{r['total_callers']}"
        h_str = f"{r['hybrid_hits']}/{r['total_callers']}"
        win = "[WIN]" if r['hybrid_recall'] > r['vec_recall'] else ("[TIE]" if r['hybrid_recall'] == r['vec_recall'] else "[LOSS]")
        print(f"  [{r['id']:02d}] {win:<6} Function: {r['target']:<28} | Vector: {v_str} | Hybrid: {h_str}", flush=True)

    n = len(results)
    avg_vec_recall = sum(r["vec_recall"] for r in results) / n
    avg_hybrid_recall = sum(r["hybrid_recall"] for r in results) / n

    print("\n" + "=" * 65, flush=True)
    print("RETRIEVAL RECALL PERFORMANCE ('What breaks if I change function Y?')", flush=True)
    print("=" * 65, flush=True)
    print(f"Vector-Only Caller Recall:        {avg_vec_recall*100:.1f}%", flush=True)
    print(f"Hybrid (Vector + Graph) Recall:   {avg_hybrid_recall*100:.1f}%", flush=True)
    print(f"Recall Advantage of Graph:        +{(avg_hybrid_recall - avg_vec_recall)*100:+.1f}%", flush=True)

    if a.retrieval_only:
        gate_passed = avg_hybrid_recall > avg_vec_recall and avg_hybrid_recall >= 0.80
        status_str = "PASS" if gate_passed else "FAIL"
        print("-" * 65, flush=True)
        print(f"Phase 3 Gate (Hybrid > Vector-only & >=80% recall): {status_str}", flush=True)
        return

    # 4. Stage 2: Model Impact Analysis (qwen2.5-coder)
    print("\n" + "=" * 65, flush=True)
    print(f"Stage 2: Model Inference ({model}) - Vector-only Context vs Hybrid Context", flush=True)
    print("=" * 65, flush=True)

    vec_model_wins = 0
    hybrid_model_wins = 0

    for r in results:
        target = r["target"]
        expected_callers = [normalize_path(f) for f in r["expected_callers"]]

        # Condition A: Vector-Only Context
        v_context = "\n\n".join(r["vec_snippets"][:4])
        prompt_vec = (
            f"You are analyzing a codebase. Question: What other files in this project break "
            f"or call function '{target}'?\n\n"
            f"Here is retrieved context from the codebase:\n{v_context}\n\n"
            f"List all caller file paths that depend on '{target}'."
        )
        try:
            ans_vec = chat([{"role": "user", "content": prompt_vec}], model=model, json_mode=False).strip()
        except Exception as e:
            ans_vec = f"ERROR: {e}"

        norm_ans_vec = normalize_path(ans_vec)
        vec_found = [c for c in expected_callers if c in norm_ans_vec]

        # Condition B: Hybrid (Vector + Graph) Context
        h_context = v_context + "\n\nCode Graph Callers / Dependencies:\n" + "\n".join(r["graph_snippets"])
        prompt_hybrid = (
            f"You are analyzing a codebase. Question: What other files in this project break "
            f"or call function '{target}'?\n\n"
            f"Here is retrieved context from the codebase and code graph:\n{h_context}\n\n"
            f"List all caller file paths that depend on '{target}'."
        )
        try:
            ans_hybrid = chat([{"role": "user", "content": prompt_hybrid}], model=model, json_mode=False).strip()
        except Exception as e:
            ans_hybrid = f"ERROR: {e}"

        norm_ans_hybrid = normalize_path(ans_hybrid)
        hybrid_found = [c for c in expected_callers if c in norm_ans_hybrid]

        r["vec_model_found"] = len(vec_found)
        r["hybrid_model_found"] = len(hybrid_found)

        v_score = f"{len(vec_found)}/{len(expected_callers)}"
        h_score = f"{len(hybrid_found)}/{len(expected_callers)}"
        diff = len(hybrid_found) - len(vec_found)
        win = "[WIN]" if diff > 0 else ("[TIE]" if diff == 0 else "[LOSS]")
        print(f"[{r['id']:02d}] {win:<6} Function: {target:<26} | Vector: {v_score} | Hybrid: {h_score}", flush=True)

    total_callers = sum(len(r["expected_callers"]) for r in results)
    total_vec_model = sum(r["vec_model_found"] for r in results)
    total_hybrid_model = sum(r["hybrid_model_found"] for r in results)

    print("\n" + "=" * 65, flush=True)
    print("PHASE 3 GATE COMPARISON SUMMARY", flush=True)
    print("=" * 65, flush=True)
    print(f"Vector-Only Context Caller Recall:      {total_vec_model}/{total_callers} ({total_vec_model/total_callers*100:.1f}%)", flush=True)
    print(f"Hybrid (Vector+Graph) Caller Recall:    {total_hybrid_model}/{total_callers} ({total_hybrid_model/total_callers*100:.1f}%)", flush=True)
    print("-" * 65, flush=True)

    gate_passed = total_hybrid_model > total_vec_model and (total_hybrid_model / total_callers >= 0.80)
    status_str = "PASS" if gate_passed else "FAIL"
    print(f"Phase 3 Gate (Hybrid > Vector-only & >=80% callers identified): {status_str}", flush=True)
    print(f"Improvement: +{(total_hybrid_model - total_vec_model)/total_callers*100:+.1f}% callers discovered with graph context", flush=True)


if __name__ == "__main__":
    main()
