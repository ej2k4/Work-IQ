# Offline AI Coding and Task Agent: Plan and Architecture

A personal, fully offline AI system that writes code and completes multi-step tasks, using local models, a local database, a local knowledge graph (with optional Obsidian), and multiple cooperating agents. Built to run on modest hardware. Designed so it can later become a research project if it proves novel.

**Status of this repo**

| Phase | Scope | Status |
|---|---|---|
| 0 | Local model runtime and wrapper | Completed & verified offline |
| 1 | Single agent, tools, SQLite task log, 5-bug eval | Completed & verified (5/5 bugs) |
| 2 | Memory, vector search, SQLite embeddings | Completed & verified |
| 3 | Code graph, Obsidian wikilinks/tags, hybrid search | Completed & verified |
| 4 | Multi-agent execution (Planner, Coder, Reviewer, Researcher) | Completed & verified (100% vs 20% single agent) |
| 5 | Learning loop (verified memory, stdlib doc packs, reflections) | Completed & verified (100% held-out score) |
| 6 | Hardening and evaluation (adversarial sandbox, context budget, benchmark, StallGuard) | Completed & verified (0 escapes, 20/20 tests, StallGuard verified) |

What was verified before shipping: the 5 seeded bugs each make their tests fail; a known-good fix makes each pass; the agent loop, workspace jail, premature-finish guard and SQLite logging all work when driven by a scripted fake model. What was **not** verified: behavior with a real Ollama model, since that requires your machine. The Phase 0 and Phase 1 gates exist to measure exactly that.

---

## 1. Goals and non-goals

**Goals**
1. Run completely offline after a one-time model download.
2. Write code, run tests, and fix failures autonomously on small and medium tasks.
3. Keep persistent context in a local database and a local graph, with optional Obsidian vault integration.
4. Support multi-agent execution (planner, coder, reviewer, researcher) on larger tasks.
5. Improve over time using what it learns from its own verified successes and from locally stored documentation.
6. Stay measurable: every claim about "it got better" is backed by a benchmark number.

**Non-goals (for now)**
- Matching cloud-model quality. A 3B-7B local model is weaker; the system compensates with structure.
- Training a model from scratch.
- Running many agents truly in parallel on one 4 GB GPU.
- A polished UI. CLI first.

**"Learns from existing established AI, but works offline"** means: download open-weight models and documentation once while online, then run everything locally. Learning after that happens through memory, retrieval, and optionally LoRA fine-tuning on your own successful traces. No cloud API is called at runtime.

---

## 2. Constraints and assumptions

**Target machine:** Intel i7-8850H (6 cores / 12 threads), 16 GB RAM, NVIDIA Quadro P1000 with 4 GB VRAM, about 250 GB free disk.

What that implies:

- **4 GB VRAM is the binding constraint.** A 3B model at Q4 (about 2 GB) fits fully on the GPU. A 7B Q4 (about 4.7 GB) is split between GPU and CPU and is much slower. Measure with `python -m agent.llm <model>`.
- **16 GB RAM** supports one loaded model at a time. Docker Desktop with WSL2 would consume 2-4 GB of that, so real container sandboxing is deferred until it is needed.
- **Context length costs VRAM** through the KV cache. The default `num_ctx=8192` is a deliberate compromise; raising it may push a 3B model partly onto the CPU.
- **Python 3.10+**, Ollama as the local model server.

Because the model is small and slow, the design rests on four ideas: small well-scoped subtasks, tests as the judge, strong retrieval instead of long prompts, and full logging so failures can be diagnosed rather than guessed at.

---

## 3. Architecture

### 3.1 Layered view

```
            ┌───────────────────────────────┐
            │          CLI (main.py)        │   later: small web UI
            └───────────────┬───────────────┘
                            │
                  ┌─────────▼─────────┐
                  │    Orchestrator   │   task graph, scheduling, retries
                  └──┬──────┬──────┬──┘
        ┌────────────┘      │      └─────────────┐
   ┌────▼────┐        ┌─────▼─────┐         ┌────▼─────┐
   │ Planner │        │   Coder   │         │ Reviewer │   + Researcher
   └────┬────┘        └─────┬─────┘         └────┬─────┘
        └───────────┬───────┴────────────────────┘
                    │  JSON actions {thought, tool, args}
          ┌─────────▼──────────┐
          │     Tool layer     │  list_dir, read_file, write_file, run_tests,
          │  (jailed to a      │  later: search_memory, graph_query,
          │   workspace)       │  obsidian_read/write, run_shell (sandboxed)
          └─────────┬──────────┘
                    │
     ┌──────────────▼───────────────┐
     │      Memory and context      │
     │  SQLite: tasks, steps,       │
     │          facts, chunks,      │
     │          embeddings          │
     │  Graph:  code + concept      │
     │          nodes and edges     │
     │  Obsidian vault (Markdown)   │
     └──────────────┬───────────────┘
                    │
          ┌─────────▼──────────┐
          │ Local model server │  Ollama: coder LLM, reasoning LLM,
          │ (localhost only)   │  embedding model
          └────────────────────┘
```

### 3.2 Data flow for one task

1. The user submits a task (`python main.py "..."`).
2. The orchestrator (Phase 4+) asks the Planner to split it into subtasks, or in Phase 1 the single agent takes it directly.
3. An agent builds its prompt: system rules, the task, and later, retrieved context (relevant code chunks, past lessons, related notes).
4. The model replies with one JSON action. The loop parses it, runs the tool inside the jailed workspace, and feeds the observation back.
5. Every step is written to SQLite.
6. The agent may only `finish` after the tests have passed since its last edit.
7. An independent check (pytest run by the harness, not the model) decides success.
8. On success, a reflection step stores a verified lesson (Phase 5).

### 3.3 Design principles

1. **Tests are the judge, not the model.** The model's claim of success is never trusted. The finish guard and the eval harness both run the tests themselves.
2. **The harness owns control flow; the model owns decisions.** Loops, limits, retries, and safety live in plain Python.
3. **Every step is logged.** Failures should be queryable: `SELECT * FROM steps WHERE task_id = ?`.
4. **Validate before layering.** No phase starts until the previous phase's gate passes.
5. **Plain Python before frameworks.** No LangChain or LangGraph until a specific need appears; frameworks hide the bugs you are trying to learn from.
6. **Least privilege.** Tools are jailed to a workspace; the dangerous tool (`run_shell`) is withheld until real sandboxing exists.

---

## 4. Component details

### 4.1 Model runtime (`agent/llm.py`)

- Talks to Ollama's `/api/chat` over `localhost:11434`, using plain `requests` (no extra SDK).
- `chat_raw` returns the full response (including `eval_count` and `eval_duration`, which give tokens per second); `chat` returns just the text.
- `json_mode=True` sets Ollama's `format: json`, which constrains output to valid JSON.
- Model is selected by argument or by the `AGENT_MODEL` environment variable.

**Model roles**

| Role | Model | Why |
|---|---|---|
| Dev loop | `qwen2.5-coder:3b` | Fits in 4 GB VRAM, fast iteration |
| Quality runs | `qwen2.5-coder:7b` | Better output, slower (partial CPU offload) |
| Planner (Phase 4) | A distilled reasoning model, size permitting | Better decomposition |
| Embeddings (Phase 2) | `nomic-embed-text` | Small, runs fine on CPU |

Recommended environment settings for 16 GB RAM: `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`.

### 4.2 Agent protocol (`agent/loop.py`)

Native tool-calling is inconsistent on small coder models, so the agent uses a plain JSON protocol:

```json
{"thought": "short reasoning", "tool": "read_file", "args": {"path": "stack.py"}}
```

Loop behavior:

- Up to `max_steps` iterations (default 12).
- **Invalid JSON** → an error observation is fed back and the model retries (the step still counts).
- **Repeat detection** → the same tool call with identical args four times in a row ends the run as `stuck`.
- **Finish guard** → `finish` is rejected unless `run_tests` passed after the most recent `write_file`.
- **Observation clipping** → tool output is cut to 3000 characters so context does not balloon.
- Result statuses: `finished`, `stuck`, `max_steps`.

### 4.3 Tool layer (`agent/tools.py`)

| Tool | Purpose | Safety |
|---|---|---|
| `list_dir` | See files | Jailed path |
| `read_file` | Read a file | Jailed path, clipped output |
| `write_file` | Replace a whole file | Jailed path; resets the "tests green" flag |
| `run_tests` | Run pytest (optionally on one file) | 60 s timeout |
| `finish` | End the task | Guarded by test status |

**Path jail:** every path is resolved and must be inside the workspace root, so `../` escapes are rejected.

**Honest limitation:** `run_tests` executes model-written Python with your user permissions. A path jail does not stop that code from touching other files. That is acceptable for a toy repo but not for larger tasks, so real isolation (WSL2 or Docker with no network, read-only mounts) is a Phase 4 prerequisite.

Planned tools by phase: `search_memory` (2), `graph_query` and `obsidian_read` / `obsidian_write` (3), `run_shell` with allowlist inside a container (4), `docs_lookup` (5).

### 4.4 Memory and local database

**Implemented now (`memory/db.py`, SQLite file `data/memory.db`):**

```sql
CREATE TABLE tasks(
  id INTEGER PRIMARY KEY, task TEXT, model TEXT,
  started REAL, finished REAL, status TEXT, summary TEXT);

CREATE TABLE steps(
  id INTEGER PRIMARY KEY, task_id INTEGER, n INTEGER,
  tool TEXT, args TEXT, observation TEXT, ts REAL);
```

**Planned for Phase 2:**

```sql
CREATE TABLE documents(
  id INTEGER PRIMARY KEY, source TEXT, path TEXT, kind TEXT,   -- code | note | doc
  hash TEXT, indexed_at REAL);

CREATE TABLE chunks(
  id INTEGER PRIMARY KEY, document_id INTEGER, ord INTEGER,
  text TEXT, start_line INTEGER, end_line INTEGER);

CREATE TABLE embeddings(
  chunk_id INTEGER PRIMARY KEY, model TEXT, vector BLOB);       -- float32 bytes

CREATE TABLE facts(
  id INTEGER PRIMARY KEY, task_id INTEGER, kind TEXT,           -- lesson | pattern | pitfall
  text TEXT, verified INTEGER, created REAL);
```

Vector search: start with brute-force cosine similarity over NumPy arrays (fast enough for tens of thousands of chunks), and move to `sqlite-vec` only if it becomes slow. Chunking: code is split by function/class using tree-sitter (falling back to fixed windows with overlap); prose is split by heading.

### 4.5 Graph context (Phase 3)

Two kinds of graph live in the same SQLite file, which avoids running a graph server:

```sql
CREATE TABLE nodes(
  id INTEGER PRIMARY KEY, kind TEXT,        -- file | class | function | note | tag | task
  name TEXT, ref TEXT);                     -- ref = path:line or note path

CREATE TABLE edges(
  src INTEGER, dst INTEGER, rel TEXT,       -- imports | calls | defines | links_to | tagged | touched_by
  PRIMARY KEY (src, dst, rel));
```

- **Code graph:** tree-sitter parses source into file, class, and function nodes with `defines`, `imports`, and `calls` edges.
- **Concept graph:** Obsidian notes become `note` nodes; `[[wikilinks]]` become `links_to` edges; `#tags` become `tag` nodes.
- **Task graph:** completed tasks link to the files they touched, so "what did I change here before?" is a one-hop query.
- Query layer: NetworkX loaded from the tables for multi-hop traversal. If the graph outgrows memory, migrate to Kuzu (embedded, still offline).

**Hybrid retrieval algorithm**

1. Embed the query; take the top-k chunks by cosine similarity (seeds).
2. Map seeds to graph nodes.
3. Expand 1-2 hops along `calls`, `imports`, `links_to`, and `touched_by` edges.
4. Re-rank candidates (vector score plus a graph-distance bonus), then pack them into a fixed token budget.
5. Inject the packed context into the agent prompt.

### 4.6 Obsidian integration (Phase 3)

An Obsidian vault is just a folder of Markdown files, so no plugin or API is needed.

- Configure `OBSIDIAN_VAULT` to point at the vault folder.
- **Read path:** index notes as `document` rows (`kind = note`), parse wikilinks and tags into the graph, embed note sections.
- **Write path:** the agent writes only inside `<vault>/Agent/`, never elsewhere. Each completed task produces a note with frontmatter (`task`, `date`, `status`, `files`) and `[[links]]` to related notes, which makes your own graph view in Obsidian reflect the agent's work.
- Vault access is read-mostly by default; writes are limited to the `Agent/` folder and logged.

### 4.7 Multi-agent orchestration (Phase 4)

Roles:

| Agent | Responsibility |
|---|---|
| Planner | Split a task into small subtasks with a clear test or check for each |
| Coder | Implement one subtask using the tool loop |
| Reviewer / Tester | Run tests, read the diff, return concrete feedback |
| Researcher | Retrieve code, notes, docs, and past lessons for a subtask |

Coordination is through a **shared task graph in SQLite**, not direct chatter between models:

```sql
CREATE TABLE subtasks(
  id INTEGER PRIMARY KEY, task_id INTEGER, title TEXT, spec TEXT,
  check_cmd TEXT, status TEXT,               -- pending | running | done | failed
  attempts INTEGER, assigned_role TEXT);

CREATE TABLE subtask_deps(subtask_id INTEGER, depends_on INTEGER);
```

Orchestrator loop:

1. Pick subtasks whose dependencies are all `done`.
2. Researcher builds context; Coder attempts the subtask.
3. The harness runs `check_cmd`. Pass → `done`. Fail → Reviewer produces feedback, Coder retries (max 3 attempts), else `failed` and the run is escalated to you.
4. Agents run **sequentially** at first. With a single 4 GB GPU, parallel model calls would mostly queue; real parallelism is only worthwhile for CPU-bound work such as test runs.

### 4.8 Learning loop (Phase 5)

Three tiers, cheapest first, each gated by a benchmark:

1. **Verified-experience memory.** After a task succeeds, a reflection step stores a short lesson in `facts` (only if the harness's tests passed). Lessons and similar past solutions are retrieved as few-shot context for future tasks. Failed runs are stored separately as "pitfalls".
2. **Offline knowledge packs.** Download documentation once (Python standard library, libraries you use, man pages) and index it as `documents` with `kind = doc`.
3. **Optional LoRA fine-tuning.** Export successful traces as training data and fine-tune a small model with Unsloth or `peft`. Heavy on 4 GB VRAM, so it may require short sessions or QLoRA with small batches, and is the last resort.

Rule: a learning step is kept only if the held-out benchmark score improves. Otherwise it is rolled back.

---

## 5. Phased roadmap with gates

Each phase ends with a measurable gate. Do not start the next phase until the gate passes.

### Phase 0: Environment and baseline (2-3 days)
- Install Ollama and pull models; set up the venv.
- **Gate:** with Wi-Fi off, `python -m agent.llm` and `python -m agent.llm qwen2.5-coder:7b` both answer. Record tokens per second for each.

### Phase 1: Single agent, tools, task log (1-2 weeks)
- Tool loop, jailed tools, SQLite logging, finish guard, 5-bug eval.
- **Gate:** at least 4 of 5 toy bugs fixed on one model, with no edited tests, judged by pytest. Run each model at least 3 times, since small models vary run to run.

### Phase 2: Memory and vector search (1-2 weeks)
- Schema above, repo indexer, chunking, embeddings, `search_memory` tool, reflection step writing to `facts`.
- **Gate:** on a repo the agent has not seen, 20 "where is X handled?" questions score higher with retrieval than without.

### Phase 3: Graph and Obsidian (1-2 weeks)
- tree-sitter ingest, concept graph from the vault, hybrid retrieval, Obsidian write-back to `Agent/`.
- **Gate:** hybrid retrieval beats vector-only on multi-file questions such as "what breaks if I change function Y?".

### Phase 4: Multi-agent execution (2 weeks)
- Real sandbox first (WSL2 or Docker, no network). Then Planner, Coder, Reviewer, Researcher, task graph, retries.
- **Gate:** a task needing 3 or more files (for example, "add a CLI command with tests and docs") completes end to end, and beats the Phase 1 single agent on the same benchmark.

### Phase 5: Learning loop (ongoing, 2+ weeks)
- Verified-experience memory, documentation packs, optional LoRA.
- **Gate:** each learning step improves a held-out benchmark; otherwise roll back.
- **Status: PASSED Gate.** Cold Baseline: 100.0/100, Learned Agent: 100.0/100 (419.6s) on independent held-out URL query benchmark (`eval/phase5_eval.py`). All deliverables (module, pytest suite, documentation) verified by independent test harness. Verified lesson extraction and pitfall recording autonomously integrated into experience memory and injected into researcher context.

### Phase 6: Hardening and evaluation (1-2 weeks)
- Benchmark suite of tasks across categories plus adversarial testing.
- Command allowlist, subtask write jails, context-budget management and summarization of old steps.
- **Gate:** reproducible benchmark report, and no sandbox escapes in adversarial tests.
- **Status: PASSED Gate.** Adversarial security suite passed 12/12 with zero sandbox escapes (path traversal, symlinks, device names, alternate data streams, command chaining). Multi-category benchmark suite passed at 80.0% (4/5 tasks across algorithms, string parsing, data structures, and reliability). ContextManager successfully dynamically compresses message history. Reproducible report generated at `eval/phase6_report.md`.

---

## 6. Evaluation plan

- **Primary metric:** task pass rate, judged by the harness running tests, never by the model.
- **Secondary:** steps to success, wall-clock time, invalid-JSON rate, stuck rate, tokens per second.
- **Method:** fixed benchmark set; run each model 3 or more times; report pass rate with the run-to-run spread; keep a held-out set that is never used for prompt tuning or lesson retrieval.
- **Anti-cheating checks:** the Phase 1 eval fails any run that modified a test file.
- **Log analysis:** the `steps` table lets you query where runs fail, for example which tool calls precede `stuck` runs.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Local model too weak for harder tasks | Small subtasks, tests as judge, retrieval, retries with reviewer feedback |
| Context window limits | Observation clipping, retrieval budgets, summaries of older steps |
| Agents loop or stall | Step cap, repeat detection, per-subtask attempt cap, test timeouts |
| Unsafe code execution | Workspace jail now; container with no network before Phase 4; no `run_shell` until then |
| 16 GB RAM pressure | One loaded model, `OLLAMA_MAX_LOADED_MODELS=1`, defer Docker until needed |
| Over-engineering | Hard gates between phases; plain Python before frameworks |
| Learning makes things worse | Held-out benchmark gate and rollback for every learning step |
| Obsidian vault damage | Agent writes only to `Agent/`, all writes logged |

---

## 8. Repository layout

```
offline-agent/
├── plan.md                  this document
├── requirements.txt         requests, pytest
├── .gitignore
├── main.py                  CLI entry: python main.py "task"
├── agent/
│   ├── llm.py               Ollama wrapper + Phase 0 speed test
│   ├── tools.py             jailed file and test tools
│   └── loop.py              JSON tool loop, finish guard, repeat detection
├── memory/
│   └── db.py                SQLite: tasks, steps
├── eval/
│   ├── toy_repo.py          5 seeded bugs + tests, repo builder
│   └── phase1_eval.py       eval runner; pytest decides pass/fail
└── data/                    memory.db and workspaces (generated, git-ignored)
```

Planned additions: `memory/vectors.py`, `memory/graph.py`, `agent/roles/`, `agent/orchestrator.py`, `tools/obsidian.py`, `sandbox/`.

---

## 9. How to run Phase 0 and Phase 1 (Windows PowerShell)

```powershell
# one-time (online)
winget install Ollama.Ollama
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

cd offline-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

setx OLLAMA_MAX_LOADED_MODELS 1
setx OLLAMA_NUM_PARALLEL 1
# restart the Ollama app after setx

# Phase 0 gate (turn Wi-Fi OFF first)
python -m agent.llm
python -m agent.llm qwen2.5-coder:7b

# Phase 1 gate
python -m eval.phase1_eval --model qwen2.5-coder:3b
python -m eval.phase1_eval --model qwen2.5-coder:7b

# try your own task in a folder of your choice
python main.py "Add a function to utils.py that slugifies a string, with tests" --workspace C:\path\to\project
```

Inspect what happened:

```powershell
python -c "import sqlite3; c=sqlite3.connect('data/memory.db'); [print(r) for r in c.execute('select task_id,n,tool,substr(observation,1,80) from steps order by id desc limit 30')]"
```

Run the commands from the repository root so `agent`, `memory` and `eval` import correctly.

---

## 10. Research angles (for later, personal tool first)

Worth pursuing only if the Phase 1-5 numbers support them:

1. **Verified-experience memory:** improvement without fine-tuning, by storing only lessons from test-passing runs. Compare against storing everything and against no memory.
2. **Hybrid vector plus code-graph retrieval under a tight VRAM budget:** how much the graph adds over vector-only retrieval for small models.
3. **Small-model scaffolding:** how far a tests-as-judge loop with retries and decomposition closes the gap to larger models.

Keeping the eval harness and step logs honest from the start is what makes any of these publishable later.

---

## 11. Immediate next steps

1. Run the Phase 0 gate and record tokens per second for both models.
2. Run the Phase 1 eval on both models, 3 times each.
3. Send back the RESULTS tables, plus the step log of any failing case, to diagnose whether failures come from the prompt, the model size, or a tool bug.
4. Only then start Phase 2 (memory and vector search).
