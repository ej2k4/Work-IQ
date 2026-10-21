"""
db.py – SQLite persistence for tasks, steps, memory, and facts.

Phase 1 schema:
    tasks      – one row per agent run (task text, model, timing, outcome)
    steps      – one row per tool call within a run

Phase 2 schema (added here):
    documents  – indexed source files or notes
    chunks     – text windows within a document
    embeddings – float32 vector blob per chunk
    facts      – lessons and pitfalls extracted from completed tasks
"""
import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id        INTEGER PRIMARY KEY,
    task      TEXT,
    model     TEXT,
    started   REAL,
    finished  REAL,
    status    TEXT,
    summary   TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY,
    task_id     INTEGER,
    n           INTEGER,
    tool        TEXT,
    args        TEXT,
    observation TEXT,
    ts          REAL
);

-- Phase 2 tables -------------------------------------------------------

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    source      TEXT,          -- repo name or vault name
    path        TEXT UNIQUE,   -- absolute or relative path
    kind        TEXT,          -- 'code' | 'note' | 'doc'
    hash        TEXT,          -- sha1 of content at index time
    indexed_at  REAL
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    ord         INTEGER,       -- position within document
    text        TEXT,
    start_line  INTEGER,
    end_line    INTEGER
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id    INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model       TEXT,
    vector      BLOB           -- numpy float32 array serialised with .tobytes()
);

CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY,
    task_id     INTEGER REFERENCES tasks(id),
    kind        TEXT,          -- 'lesson' | 'pitfall'
    text        TEXT,
    verified    INTEGER DEFAULT 1,
    created     REAL
);

CREATE TABLE IF NOT EXISTS fact_embeddings (
    fact_id     INTEGER PRIMARY KEY REFERENCES facts(id) ON DELETE CASCADE,
    model       TEXT,
    vector      BLOB           -- numpy float32 array serialised with .tobytes()
);

-- Phase 3 tables: Code, concept, and task graph -----------------------

CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY,
    kind        TEXT,          -- 'file' | 'class' | 'function' | 'note' | 'tag' | 'task'
    name        TEXT,          -- symbol name, note title, tag name
    ref         TEXT           -- path:line, note path, or identifier
);

CREATE TABLE IF NOT EXISTS edges (
    src         INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    dst         INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    rel         TEXT,          -- 'imports' | 'calls' | 'defines' | 'links_to' | 'tagged' | 'touched_by'
    PRIMARY KEY (src, dst, rel)
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_ref  ON nodes(ref);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_edges_src  ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst  ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_rel  ON edges(rel);

-- Phase 4 tables: Multi-agent task graph ------------------------------

CREATE TABLE IF NOT EXISTS subtasks (
    id             INTEGER PRIMARY KEY,
    task_id        INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    title          TEXT,
    spec           TEXT,
    check_cmd      TEXT,
    status         TEXT DEFAULT 'pending', -- 'pending' | 'running' | 'done' | 'failed'
    attempts       INTEGER DEFAULT 0,
    assigned_role  TEXT DEFAULT 'coder',
    result_summary TEXT DEFAULT '',
    feedback       TEXT DEFAULT '',
    created        REAL
);

CREATE TABLE IF NOT EXISTS subtask_deps (
    subtask_id     INTEGER REFERENCES subtasks(id) ON DELETE CASCADE,
    depends_on     INTEGER REFERENCES subtasks(id) ON DELETE CASCADE,
    PRIMARY KEY (subtask_id, depends_on)
);

CREATE INDEX IF NOT EXISTS idx_subtasks_task_id ON subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_subtasks_status  ON subtasks(status);
"""


class DB:
    """Thin wrapper around an SQLite connection for task + step logging."""

    def __init__(self, path: str = "data/memory.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript(_SCHEMA)
        self.con.commit()

    # ── Task lifecycle ───────────────────────────────────────────────────────

    def start_task(self, task: str, model: str) -> int:
        """Insert a new task row and return its id."""
        cur = self.con.execute(
            "INSERT INTO tasks(task, model, started, status) VALUES (?,?,?,?)",
            (task, model, time.time(), "running"),
        )
        self.con.commit()
        return cur.lastrowid

    def finish_task(self, task_id: int, status: str, summary: str = "") -> None:
        """Update the task row with its final status and summary."""
        self.con.execute(
            "UPDATE tasks SET finished=?, status=?, summary=? WHERE id=?",
            (time.time(), status, summary, task_id),
        )
        self.con.commit()

    # ── Step logging ─────────────────────────────────────────────────────────

    def log_step(self, task_id: int, n: int, tool: str,
                 args: dict, observation: str) -> None:
        """Append one tool-call step to the steps table."""
        self.con.execute(
            "INSERT INTO steps(task_id, n, tool, args, observation, ts) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, n, tool, json.dumps(args), observation[:5000], time.time()),
        )
        self.con.commit()

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_task(self, task_id: int) -> dict | None:
        """Return a task row as a dict, or None if not found."""
        row = self.con.execute(
            "SELECT id, task, model, started, finished, status, summary "
            "FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ("id", "task", "model", "started", "finished", "status", "summary")
        return dict(zip(keys, row))

    def get_steps(self, task_id: int) -> list[dict]:
        """Return all steps for a task as a list of dicts."""
        rows = self.con.execute(
            "SELECT n, tool, args, observation, ts FROM steps "
            "WHERE task_id=? ORDER BY n",
            (task_id,),
        ).fetchall()
        keys = ("n", "tool", "args", "observation", "ts")
        return [dict(zip(keys, r)) for r in rows]

    def recent_tasks(self, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* tasks."""
        rows = self.con.execute(
            "SELECT id, task, model, status, started, finished FROM tasks "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keys = ("id", "task", "model", "status", "started", "finished")
        return [dict(zip(keys, r)) for r in rows]

    # ── Document / chunk indexing (Phase 2) ──────────────────────────────────

    def upsert_document(self, path: str, source: str, kind: str,
                        content_hash: str) -> tuple[int, bool]:
        """
        Insert or update a document row.

        Returns (doc_id, is_new) where is_new is True when the hash changed
        (i.e. the document needs re-chunking and re-embedding).
        """
        row = self.con.execute(
            "SELECT id, hash FROM documents WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            cur = self.con.execute(
                "INSERT INTO documents(source, path, kind, hash, indexed_at) "
                "VALUES (?,?,?,?,?)",
                (source, path, kind, content_hash, time.time()),
            )
            self.con.commit()
            return cur.lastrowid, True
        doc_id, old_hash = row
        if old_hash == content_hash:
            return doc_id, False
        # Content changed: update hash and wipe old chunks/embeddings.
        self.con.execute(
            "UPDATE documents SET hash=?, indexed_at=? WHERE id=?",
            (content_hash, time.time(), doc_id),
        )
        self.con.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        self.con.commit()
        return doc_id, True

    def insert_chunks(self, doc_id: int, chunks: list[dict]) -> list[int]:
        """
        Bulk-insert chunks for a document. Each dict must have:
            text, ord, start_line, end_line
        Returns list of new chunk ids.
        """
        ids = []
        for c in chunks:
            cur = self.con.execute(
                "INSERT INTO chunks(document_id, ord, text, start_line, end_line) "
                "VALUES (?,?,?,?,?)",
                (doc_id, c["ord"], c["text"], c["start_line"], c["end_line"]),
            )
            ids.append(cur.lastrowid)
        self.con.commit()
        return ids

    def insert_embedding(self, chunk_id: int, model: str,
                         vector_bytes: bytes) -> None:
        """Store a serialised float32 embedding for a chunk."""
        self.con.execute(
            "INSERT OR REPLACE INTO embeddings(chunk_id, model, vector) "
            "VALUES (?,?,?)",
            (chunk_id, model, vector_bytes),
        )
        self.con.commit()

    def all_embeddings(self) -> list[tuple[int, bytes, str, int, int]]:
        """
        Return all stored embeddings joined with chunk metadata.

        Each row: (chunk_id, vector_bytes, text, start_line, end_line).
        """
        rows = self.con.execute(
            "SELECT e.chunk_id, e.vector, c.text, c.start_line, c.end_line "
            "FROM embeddings e JOIN chunks c ON e.chunk_id = c.id"
        ).fetchall()
        return rows

    def chunk_path(self, chunk_id: int) -> str | None:
        """Return the file path for the document that owns this chunk."""
        row = self.con.execute(
            "SELECT d.path FROM chunks c "
            "JOIN documents d ON c.document_id = d.id "
            "WHERE c.id=?",
            (chunk_id,),
        ).fetchone()
        return row[0] if row else None

    # ── Facts (Phase 2) ──────────────────────────────────────────────────────

    def save_fact(self, task_id: int, kind: str, text: str, embed_now: bool = True) -> int:
        """Persist a lesson or pitfall extracted from a completed task and optionally embed it."""
        cur = self.con.execute(
            "INSERT INTO facts(task_id, kind, text, verified, created) "
            "VALUES (?,?,?,1,?)",
            (task_id, kind, text, time.time()),
        )
        self.con.commit()
        fact_id = cur.lastrowid
        if embed_now:
            try:
                from memory.vectors import embed, EMBED_MODEL
                vec = embed(text)
                self.insert_fact_embedding(fact_id, EMBED_MODEL, vec.tobytes())
            except Exception:
                pass  # best-effort embedding
        return fact_id

    def insert_fact_embedding(self, fact_id: int, model: str, vector_bytes: bytes) -> None:
        """Store a serialised float32 embedding for a fact."""
        self.con.execute(
            "INSERT OR REPLACE INTO fact_embeddings(fact_id, model, vector) VALUES (?,?,?)",
            (fact_id, model, vector_bytes),
        )
        self.con.commit()

    def all_fact_embeddings(self, kind: str | None = None) -> list[tuple[int, bytes, str, str]]:
        """Return (fact_id, vector_bytes, text, kind) for all embedded facts."""
        if kind:
            q = ("SELECT fe.fact_id, fe.vector, f.text, f.kind "
                 "FROM fact_embeddings fe JOIN facts f ON fe.fact_id = f.id "
                 "WHERE f.kind = ? AND f.verified = 1")
            return self.con.execute(q, (kind,)).fetchall()
        else:
            q = ("SELECT fe.fact_id, fe.vector, f.text, f.kind "
                 "FROM fact_embeddings fe JOIN facts f ON fe.fact_id = f.id "
                 "WHERE f.verified = 1")
            return self.con.execute(q).fetchall()

    def search_facts(self, query: str, kind: str | None = None, top_k: int = 3, min_score: float = 0.45) -> list[dict]:
        """Semantically search verified lessons/pitfalls using cosine similarity."""
        try:
            from memory.vectors import embed, cosine_search
            qvec = embed(query)
            rows = self.all_fact_embeddings(kind=kind)
            if not rows:
                return []
            adapted_rows = [(r[0], r[1], r[2], 0, 0) for r in rows]
            matches = cosine_search(qvec, adapted_rows, top_k=top_k, min_score=min_score)
            results = []
            for m in matches:
                f_kind = next((r[3] for r in rows if r[0] == m["chunk_id"]), kind or "fact")
                results.append({
                    "fact_id": m["chunk_id"],
                    "kind": f_kind,
                    "text": m["text"],
                    "score": m["score"],
                })
            return results
        except Exception:
            # Fallback to recency if embedding search is unavailable
            facts = self.recent_facts(kind=kind or "lesson", limit=top_k)
            return [{"fact_id": None, "kind": kind or "lesson", "text": f, "score": 1.0} for f in facts]

    def recent_facts(self, kind: str = "lesson", limit: int = 10) -> list[str]:
        """Return the text of the most recent verified facts of a given kind."""
        rows = self.con.execute(
            "SELECT text FROM facts WHERE kind=? AND verified=1 "
            "ORDER BY id DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
        return [r[0] for r in rows]

    # ── Graph context (Phase 3) ──────────────────────────────────────────────

    def upsert_node(self, kind: str, name: str, ref: str) -> int:
        """
        Insert a node into the graph if not already present; return its ID.
        Identified uniquely by (kind, name, ref).
        """
        row = self.con.execute(
            "SELECT id FROM nodes WHERE kind=? AND name=? AND ref=?",
            (kind, name, ref),
        ).fetchone()
        if row:
            return row[0]
        cur = self.con.execute(
            "INSERT INTO nodes(kind, name, ref) VALUES (?,?,?)",
            (kind, name, ref),
        )
        self.con.commit()
        return cur.lastrowid

    def add_edge(self, src: int, dst: int, rel: str) -> None:
        """Add a directed relation from src node to dst node."""
        if src == dst:
            return
        self.con.execute(
            "INSERT OR IGNORE INTO edges(src, dst, rel) VALUES (?,?,?)",
            (src, dst, rel),
        )
        self.con.commit()

    def find_node(self, name: str | None = None, ref: str | None = None,
                  kind: str | None = None) -> dict | None:
        """Find a single node matching specified filters."""
        nodes = self.find_nodes(name=name, ref=ref, kind=kind)
        return nodes[0] if nodes else None

    def find_nodes(self, name: str | None = None, ref: str | None = None,
                   kind: str | None = None) -> list[dict]:
        """Query nodes matching optional filters."""
        query = "SELECT id, kind, name, ref FROM nodes WHERE 1=1"
        params: list = []
        if name is not None:
            query += " AND name=?"
            params.append(name)
        if ref is not None:
            query += " AND ref=?"
            params.append(ref)
        if kind is not None:
            query += " AND kind=?"
            params.append(kind)
        rows = self.con.execute(query, params).fetchall()
        return [{"id": r[0], "kind": r[1], "name": r[2], "ref": r[3]} for r in rows]

    def get_neighbors(self, node_id: int, direction: str = "both",
                      rel: str | None = None) -> list[dict]:
        """
        Get all adjacent nodes connected by edges.

        direction: 'out' (src->dst), 'in' (dst->src), or 'both'
        """
        results = []
        if direction in ("out", "both"):
            q = ("SELECT n.id, n.kind, n.name, n.ref, e.rel, 'out' "
                 "FROM edges e JOIN nodes n ON e.dst = n.id WHERE e.src=?")
            params = [node_id]
            if rel:
                q += " AND e.rel=?"
                params.append(rel)
            for r in self.con.execute(q, params).fetchall():
                results.append({
                    "id": r[0], "kind": r[1], "name": r[2], "ref": r[3],
                    "rel": r[4], "direction": r[5],
                })

        if direction in ("in", "both"):
            q = ("SELECT n.id, n.kind, n.name, n.ref, e.rel, 'in' "
                 "FROM edges e JOIN nodes n ON e.src = n.id WHERE e.dst=?")
            params = [node_id]
            if rel:
                q += " AND e.rel=?"
                params.append(rel)
            for r in self.con.execute(q, params).fetchall():
                results.append({
                    "id": r[0], "kind": r[1], "name": r[2], "ref": r[3],
                    "rel": r[4], "direction": r[5],
                })
        return results

    def all_graph(self) -> tuple[list[dict], list[dict]]:
        """Return all nodes and edges in the graph."""
        nodes = [
            {"id": r[0], "kind": r[1], "name": r[2], "ref": r[3]}
            for r in self.con.execute("SELECT id, kind, name, ref FROM nodes").fetchall()
        ]
        edges = [
            {"src": r[0], "dst": r[1], "rel": r[2]}
            for r in self.con.execute("SELECT src, dst, rel FROM edges").fetchall()
        ]
        return nodes, edges

    def clear_graph(self) -> None:
        """Clear all nodes and edges from the graph."""
        self.con.execute("DELETE FROM edges")
        self.con.execute("DELETE FROM nodes")
        self.con.commit()

    def record_task_touched_file(self, task_id: int, file_path: str) -> None:
        """Record that a task touched a specific file."""
        t_node = self.upsert_node("task", f"task_{task_id}", f"task:{task_id}")
        f_node = self.upsert_node("file", Path(file_path).name, file_path)
        self.add_edge(f_node, t_node, "touched_by")

    # ── Task Graph & Orchestration (Phase 4) ─────────────────────────────────

    def create_subtask(self, task_id: int, title: str, spec: str,
                       check_cmd: str, assigned_role: str = "coder") -> int:
        """Insert a new subtask into the task graph."""
        cur = self.con.execute(
            "INSERT INTO subtasks(task_id, title, spec, check_cmd, status, "
            "assigned_role, created) VALUES (?,?,?,?,'pending',?,?)",
            (task_id, title, spec, check_cmd, assigned_role, time.time()),
        )
        self.con.commit()
        return cur.lastrowid

    def add_subtask_dep(self, subtask_id: int, depends_on_id: int) -> None:
        """Record a dependency: subtask_id cannot run until depends_on_id is done."""
        self.con.execute(
            "INSERT OR IGNORE INTO subtask_deps(subtask_id, depends_on) VALUES (?,?)",
            (subtask_id, depends_on_id),
        )
        self.con.commit()

    def get_subtask(self, subtask_id: int) -> dict | None:
        """Fetch a single subtask by id."""
        row = self.con.execute(
            "SELECT id, task_id, title, spec, check_cmd, status, attempts, "
            "assigned_role, result_summary, feedback, created FROM subtasks WHERE id=?",
            (subtask_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("id", "task_id", "title", "spec", "check_cmd", "status",
                "attempts", "assigned_role", "result_summary", "feedback", "created")
        return dict(zip(keys, row))

    def get_subtasks(self, task_id: int) -> list[dict]:
        """Fetch all subtasks for a task, ordered by id."""
        rows = self.con.execute(
            "SELECT id, task_id, title, spec, check_cmd, status, attempts, "
            "assigned_role, result_summary, feedback, created FROM subtasks "
            "WHERE task_id=? ORDER BY id",
            (task_id,),
        ).fetchall()
        keys = ("id", "task_id", "title", "spec", "check_cmd", "status",
                "attempts", "assigned_role", "result_summary", "feedback", "created")
        return [dict(zip(keys, r)) for r in rows]

    def get_ready_subtasks(self, task_id: int) -> list[dict]:
        """
        Return subtasks with status='pending' whose dependencies are all status='done'.
        """
        # A subtask is ready if:
        # 1. status is 'pending'
        # 2. It has no dependencies that are NOT 'done'
        query = """
        SELECT s.id, s.task_id, s.title, s.spec, s.check_cmd, s.status,
               s.attempts, s.assigned_role, s.result_summary, s.feedback, s.created
        FROM subtasks s
        WHERE s.task_id = ? AND s.status = 'pending'
          AND NOT EXISTS (
              SELECT 1 FROM subtask_deps d
              JOIN subtasks dep_s ON d.depends_on = dep_s.id
              WHERE d.subtask_id = s.id AND dep_s.status != 'done'
          )
        ORDER BY s.id
        """
        rows = self.con.execute(query, (task_id,)).fetchall()
        keys = ("id", "task_id", "title", "spec", "check_cmd", "status",
                "attempts", "assigned_role", "result_summary", "feedback", "created")
        return [dict(zip(keys, r)) for r in rows]

    def update_subtask_status(self, subtask_id: int, status: str,
                              result_summary: str = "", feedback: str = "",
                              increment_attempt: bool = False) -> None:
        """Update a subtask's status, feedback, summary, and attempt counter."""
        if increment_attempt:
            self.con.execute(
                "UPDATE subtasks SET status=?, result_summary=?, feedback=?, "
                "attempts = attempts + 1 WHERE id=?",
                (status, result_summary, feedback, subtask_id),
            )
        else:
            self.con.execute(
                "UPDATE subtasks SET status=?, result_summary=?, feedback=? WHERE id=?",
                (status, result_summary, feedback, subtask_id),
            )
        self.con.commit()

