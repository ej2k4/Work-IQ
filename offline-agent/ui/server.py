"""
server.py – Lightweight offline web server and API for the AI Agent Studio.

Serves the interactive Knowledge Graph, Study Generator, AI Tutor, and Task Monitor.
Runs locally with zero external web dependencies.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import time
import traceback
import urllib.parse

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.llm import chat, chat_raw, DEFAULT_MODEL
from memory.db import DB
from memory.graph import load_graph, hybrid_search, index_workspace_project
from memory.obsidian import index_vault
from study import generate_curriculum_plan, write_curriculum_notes, query_study_graph, list_study_topics

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT", r"C:\Users\admin\Documents\ObsidianVault")
DB_PATH = _PROJECT_ROOT / "data" / "memory.db"
UI_DIR = Path(__file__).resolve().parent


def resolve_node_note(
    node_name: str,
    node_id: str | int | None = None,
    node_kind: str | None = None,
    node_ref: str | None = None,
) -> dict:
    """Resolves or generates a comprehensive Markdown note for any node in the knowledge graph."""
    vault_p = Path(DEFAULT_VAULT)
    db = DB(str(DB_PATH))

    # 1. Look up node in DB if ID or name is provided
    node_id_int = int(node_id) if node_id and str(node_id).isdigit() else None
    if node_id_int:
        row = db.con.execute("SELECT id, name, kind, ref FROM nodes WHERE id=?", (node_id_int,)).fetchone()
        if row:
            node_name = node_name or row[1]
            node_kind = node_kind or row[2]
            node_ref = node_ref or row[3]
    elif node_name:
        row = db.con.execute(
            "SELECT id, name, kind, ref FROM nodes WHERE name=? OR name=? COLLATE NOCASE",
            (node_name, node_name.replace(" ", "_")),
        ).fetchone()
        if row:
            node_id_int = row[0]
            node_kind = node_kind or row[2]
            node_ref = node_ref or row[3]

    # 2. Check Obsidian Vault with intelligent normalized fuzzy matching
    if vault_p.is_dir() and node_name:
        norm = lambda s: re.sub(r"[^a-zA-Z0-9]", "", s.lower())
        t_norm = norm(node_name)
        task_num_match = re.search(r"(\d+)", node_name)
        task_num = task_num_match.group(1) if task_num_match else None

        matched_f: Path | None = None
        for f in vault_p.rglob("*.md"):
            f_norm = norm(f.stem)
            if f.stem.lower() == node_name.lower() or f_norm == t_norm:
                matched_f = f
                break
            if task_num and f"task{task_num}" == f_norm:
                matched_f = f
                break
            if t_norm in f_norm or f_norm in t_norm:
                if matched_f is None:
                    matched_f = f

        if matched_f and matched_f.is_file():
            content = matched_f.read_text(encoding="utf-8", errors="replace")
            return {
                "found": True,
                "source": "vault",
                "in_vault": True,
                "name": matched_f.name,
                "rel_path": str(matched_f.relative_to(vault_p)).replace("\\", "/"),
                "kind": node_kind or "note",
                "content": content,
                "can_save": True,
            }

    # 3. Retrieve Graph Connections for this node (if in DB)
    outgoing = []
    incoming = []
    if node_id_int:
        out_rows = db.con.execute("""
            SELECT n.id, n.name, n.kind, e.rel, n.ref
            FROM edges e 
            JOIN nodes n ON e.dst = n.id 
            WHERE e.src = ? 
            LIMIT 35
        """, (node_id_int,)).fetchall()
        outgoing = [{"id": r[0], "name": r[1], "kind": r[2], "rel": r[3], "ref": r[4]} for r in out_rows]

        in_rows = db.con.execute("""
            SELECT n.id, n.name, n.kind, e.rel, n.ref
            FROM edges e 
            JOIN nodes n ON e.src = n.id 
            WHERE e.dst = ? 
            LIMIT 35
        """, (node_id_int,)).fetchall()
        incoming = [{"id": r[0], "name": r[1], "kind": r[2], "rel": r[3], "ref": r[4]} for r in in_rows]

    def format_connections() -> str:
        md_parts = []
        if outgoing:
            md_parts.append(f"### Outgoing References ({len(outgoing)})")
            for item in outgoing:
                md_parts.append(f"- [[{item['name']}]] *({item['rel']})*")
        if incoming:
            md_parts.append(f"\n### Referenced By ({len(incoming)})")
            for item in incoming:
                md_parts.append(f"- [[{item['name']}]] *({item['rel']})*")
        return "\n".join(md_parts) if md_parts else "_No direct relational connections recorded in memory graph._"

    # 3.5 Workspace Project / File Node Handler
    if (node_ref and node_ref.startswith("workspace:")) or node_kind == "project":
        ws_root = _PROJECT_ROOT / "data" / "workspaces"
        ws_sub = node_ref[len("workspace:"):] if (node_ref and node_ref.startswith("workspace:")) else node_name
        parts = ws_sub.split(":")
        rel_sub = parts[0]
        line_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

        target_ws_p = (ws_root / rel_sub).resolve()

        # Workspace Project Folder
        if target_ws_p.is_dir() or node_kind == "project":
            proj_dir = target_ws_p if target_ws_p.is_dir() else (ws_root / node_name)
            if proj_dir.is_dir():
                py_files = list(proj_dir.rglob("*.py"))
                test_files = [f for f in py_files if f.name.startswith("test_") or f.name.endswith("_test.py")]
                file_list_md = []
                for f in sorted(proj_dir.rglob("*")):
                    if f.is_file() and not any(p.startswith(".") or p in {"__pycache__", ".pytest_cache"} for p in f.parts):
                        rel = f.relative_to(proj_dir)
                        file_list_md.append(f"- 📄 `{rel}` ({f.stat().st_size} bytes)")

                md = f"""# 📦 Workspace Project: `{proj_dir.name}`

> **Kind:** `PROJECT` | **Path:** `data/workspaces/{proj_dir.name}`
> **Files:** {len(file_list_md)} | **Python:** {len(py_files)} | **Unit Tests:** {len(test_files)}

## Contained Files
{chr(10).join(file_list_md) if file_list_md else "_No workspace files generated yet._"}

## Relational Graph Neighborhood
{format_connections()}

---
💡 *Switch to the **Code Studio** tab to edit files, run offline unit tests with pytest, or link this project to curriculum nodes.*
"""
                return {
                    "found": True,
                    "source": "workspace_project",
                    "in_vault": False,
                    "name": f"{proj_dir.name}.md",
                    "rel_path": f"Workspaces/{proj_dir.name}.md",
                    "kind": "project",
                    "content": md,
                    "can_save": False,
                    "node_id": node_id_int,
                    "outgoing": outgoing,
                    "incoming": incoming,
                    "workspace_info": {
                        "workspace": proj_dir.name,
                        "is_project": True
                    }
                }

        # Workspace File or Symbol
        if target_ws_p.is_file():
            file_lines = target_ws_p.read_text(encoding="utf-8", errors="replace").splitlines()
            code_snippet = ""
            if line_num and 1 <= line_num <= len(file_lines):
                start_idx = line_num - 1
                extracted = []
                base_indent = len(file_lines[start_idx]) - len(file_lines[start_idx].lstrip())
                for i in range(start_idx, min(len(file_lines), start_idx + 45)):
                    line = file_lines[i]
                    if i > start_idx and line.strip() and (len(line) - len(line.lstrip())) <= base_indent:
                        break
                    extracted.append(line)
                code_snippet = "\n".join(extracted)
            else:
                code_snippet = "\n".join(file_lines[:50])

            proj_name = rel_sub.split("/")[0] if "/" in rel_sub else rel_sub
            file_rel_in_proj = rel_sub[len(proj_name)+1:] if "/" in rel_sub else target_ws_p.name

            md = f"""# 📄 `{target_ws_p.name}`

> **Workspace:** `{proj_name}` | **Kind:** `{node_kind.upper() if node_kind else 'FILE'}`
> **Path:** `data/workspaces/{rel_sub}` {f'(Line {line_num})' if line_num else ''}

## Source Code Preview
```python
{code_snippet}
```

## Relational Connections & Linked Nodes
{format_connections()}
"""
            clean_name = re.sub(r'[^\w\-.]', '_', node_name)
            return {
                "found": True,
                "source": "workspace_file",
                "in_vault": False,
                "name": f"{clean_name}.md",
                "rel_path": f"Workspaces/{proj_name}/{clean_name}.md",
                "kind": node_kind or "file",
                "content": md,
                "can_save": False,
                "node_id": node_id_int,
                "outgoing": outgoing,
                "incoming": incoming,
                "workspace_info": {
                    "workspace": proj_name,
                    "file_path": file_rel_in_proj,
                    "line": line_num,
                    "is_project": False
                }
            }

    # 4. Code Symbol / File Node Handler
    filepath = None
    line_num = None
    if node_ref and not node_ref.startswith(("symbol:", "import:", "tag:", "task:", "workspace:")):
        parts = node_ref.split(":")
        filepath = parts[0]
        if len(parts) > 1 and parts[1].isdigit():
            line_num = int(parts[1])

    code_file_p = (_PROJECT_ROOT / filepath) if filepath else None
    if code_file_p and code_file_p.is_file():
        file_lines = code_file_p.read_text(encoding="utf-8", errors="replace").splitlines()
        code_snippet = ""
        if line_num and 1 <= line_num <= len(file_lines):
            start_idx = line_num - 1
            extracted = []
            base_indent = len(file_lines[start_idx]) - len(file_lines[start_idx].lstrip())
            for i in range(start_idx, min(len(file_lines), start_idx + 45)):
                line = file_lines[i]
                if i > start_idx and line.strip() and (len(line) - len(line.lstrip())) <= base_indent:
                    break
                extracted.append(line)
            code_snippet = "\n".join(extracted)
        else:
            code_snippet = "\n".join(file_lines[:40])

        md = f"""# `{node_name}`

> **Kind:** `{node_kind.upper() if node_kind else 'CODE'}` | **Reference:** `{node_ref}`
> **File:** `{filepath}` {f'(Line {line_num})' if line_num else ''}

## Source Code Definition
```python
{code_snippet}
```

## Knowledge Graph Context
{format_connections()}
"""
        clean_name = re.sub(r'[^\w\-.]', '_', node_name)
        return {
            "found": True,
            "source": "code",
            "in_vault": False,
            "name": f"{clean_name}.md",
            "rel_path": f"Code/{clean_name}.md",
            "kind": node_kind or "code",
            "content": md,
            "can_save": True,
            "node_id": node_id_int,
            "outgoing": outgoing,
            "incoming": incoming,
        }

    # 5. Task Node Handler
    task_id_match = re.search(r"(\d+)", node_name or (node_ref or ""))
    if (node_kind == "task" or (node_name and node_name.lower().startswith("task"))) and task_id_match:
        t_id = int(task_id_match.group(1))
        t_row = db.con.execute(
            "SELECT id, task, model, status, summary, started FROM tasks WHERE id=?", (t_id,)
        ).fetchone()
        if t_row:
            ts_str = "-"
            if t_row[5]:
                try:
                    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(t_row[5])))
                except Exception:
                    ts_str = str(t_row[5])

            st_rows = db.con.execute(
                "SELECT title, assigned_role, status, result_summary FROM subtasks WHERE task_id=?", (t_id,)
            ).fetchall()
            st_text = "\n".join([f"- **{r[0]}** ({r[1]} - *{r[2]}*): {r[3] or ''}" for r in st_rows]) if st_rows else "_No subtasks logged._"

            f_rows = db.con.execute("SELECT kind, text FROM facts WHERE task_id=?", (t_id,)).fetchall()
            f_text = "\n".join([f"- `[{r[0].upper()}]` {r[1]}" for r in f_rows]) if f_rows else "_No distilled facts recorded._"

            md = f"""# Task #{t_id} Execution Note

> **Status:** `{t_row[3]}` | **Model:** `{t_row[2]}` | **Started:** {ts_str}

## Task Specification
```text
{t_row[1]}
```

## Retrospective Summary
{t_row[4] or 'Autonomous cycle completed successfully.'}

## Subtask Decomposition ({len(st_rows)})
{st_text}

## Distilled Lessons & Insights ({len(f_rows)})
{f_text}

## Relational Graph Neighborhood
{format_connections()}
"""
            return {
                "found": True,
                "source": "task",
                "in_vault": False,
                "name": f"Task-{t_id}.md",
                "rel_path": f"Agent/Task-{t_id}.md",
                "kind": "task",
                "content": md,
                "can_save": True,
                "node_id": node_id_int,
                "outgoing": outgoing,
                "incoming": incoming,
            }

    # 6. General Concept / Module / Tag Node
    display_title = (node_name or "Concept").replace("_", " ")
    md = f"""# {display_title}

> **Kind:** `{node_kind.upper() if node_kind else 'CONCEPT'}` | **Relational Knowledge Node**
> **Graph Degree:** {len(outgoing) + len(incoming)} connections

## Knowledge Graph Neighborhood
{format_connections()}

## Context & Notes
This concept is an interconnected entity in the offline agent's knowledge graph.
- Click **Save to Vault** to save this note into your Obsidian vault as a permanent markdown file.
- Or use the **AI Study Generator** to synthesize an exhaustive, multi-chapter curriculum on this topic.
"""
    clean_name = re.sub(r'[^\w\-.]', '_', node_name or "concept")
    return {
        "found": True,
        "source": "graph",
        "in_vault": False,
        "name": f"{clean_name}.md",
        "rel_path": f"Concepts/{clean_name}.md",
        "kind": node_kind or "concept",
        "content": md,
        "can_save": True,
        "node_id": node_id_int,
        "outgoing": outgoing,
        "incoming": incoming,
    }


def classify_node(name: str, kind: str, ref: str, edu_topics: list[str]) -> tuple[str, str | None, bool]:
    """Classifies a knowledge graph node into distinct architectural categories and educational topics."""
    ref_norm = (ref or "").replace("\\", "/")
    name_norm = name or ""

    # 1. Workspace Projects and Files
    if kind == "project" or (ref_norm.startswith("workspace:") and "/" not in ref_norm[10:]):
        return "workspace_project", None, False
    if ref_norm.startswith("workspace:"):
        if kind == "class":
            return "code_class", None, False
        if kind == "function":
            return "code_function", None, False
        return "workspace_file", None, False

    # 2. Codebase structural components
    if kind == "file" or (ref_norm.endswith(".py") and ":" not in ref_norm):
        return "code_file", None, False
    if kind == "class":
        return "code_class", None, False
    if kind == "function" or (re.search(r":\d+", ref_norm) or ref_norm.startswith("symbol:")):
        return "code_function", None, False
    if kind == "module" or ref_norm.startswith("import:"):
        return "code_module", None, False
    if kind == "tag" or name_norm.startswith("#"):
        return "tag", None, False

    # 2. Agent Execution Tasks
    if ref_norm.startswith("Agent/Task") or "Task-" in name_norm or kind == "task":
        return "task", None, False

    # 3. Educational Curriculum Topics
    topic = None
    is_curr = False
    if "Education/" in ref_norm or ref_norm.startswith("Education/"):
        parts = ref_norm.split("/")
        if "Education" in parts:
            idx = parts.index("Education")
            if len(parts) > idx + 1:
                topic = parts[idx + 1]
    elif ref_norm.startswith("note:"):
        note_name = ref_norm.split("note:", 1)[1]
        for t in edu_topics:
            if t.lower() in note_name.lower():
                topic = t
                break

    # If topic wasn't detected from ref, test against known edu_topics
    if not topic and edu_topics:
        for t in edu_topics:
            if t.lower() == name_norm.lower() or t.lower() in name_norm.lower():
                topic = t
                break

    if "curriculum" in name_norm.lower() or name_norm == "Curriculum_Index" or "Curriculum" in ref_norm:
        is_curr = True

    if topic:
        return "education", topic, is_curr
    if is_curr:
        return "curriculum", None, True
    if ref_norm.startswith("Agent/"):
        return "task", None, False

    return "concept", None, False


class AgentStudioHandler(http.server.BaseHTTPRequestHandler):
    """Handles static UI files and JSON API endpoints."""

    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, content_type: str):
        if not file_path.is_file():
            self.send_error(404, f"File not found: {file_path.name}")
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as e:
            traceback.print_exc()
            self._send_json({"error": str(e)}, 500)

    def _handle_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Static assets
        if path == "/" or path == "/index.html":
            self._send_file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        elif path == "/styles.css":
            self._send_file(UI_DIR / "styles.css", "text/css; charset=utf-8")
            return
        elif path == "/app.js":
            self._send_file(UI_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # API Endpoints
        if path == "/api/stats":
            db = DB(str(DB_PATH))
            vault_p = Path(DEFAULT_VAULT)
            notes_count = len(list(vault_p.rglob("*.md"))) if vault_p.is_dir() else 0
            tasks_count = db.con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            lessons_count = db.con.execute("SELECT COUNT(*) FROM facts WHERE kind='lesson'").fetchone()[0]
            nodes_count = db.con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges_count = db.con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

            ws_root = _PROJECT_ROOT / "data" / "workspaces"
            workspaces_count = len([d for d in ws_root.iterdir() if d.is_dir() and not d.name.startswith(".")]) if ws_root.is_dir() else 0
            workspace_files_count = len([f for f in ws_root.rglob("*") if f.is_file() and not any(p.startswith(".") or p in {"__pycache__", ".pytest_cache"} for p in f.parts)]) if ws_root.is_dir() else 0

            self._send_json({
                "vault_path": str(vault_p),
                "notes_count": notes_count,
                "tasks_count": tasks_count,
                "lessons_count": lessons_count,
                "nodes_count": nodes_count,
                "edges_count": edges_count,
                "workspaces_count": workspaces_count,
                "workspace_files_count": workspace_files_count,
                "topics": list_study_topics(vault_p),
            })
            return

        elif path == "/api/graph":
            db = DB(str(DB_PATH))
            G = load_graph(db)
            vault_p = Path(DEFAULT_VAULT)
            edu_topics = list_study_topics(vault_p) if vault_p.is_dir() else []

            nodes_data = []
            category_counts: dict[str, int] = {}
            topic_counts: dict[str, int] = {}

            for n, d in G.nodes(data=True):
                # Clean up display name
                name = d.get("name", str(n))
                kind = d.get("kind", "concept")
                ref = d.get("ref", "")
                cat, topic, is_curr = classify_node(name, kind, ref, edu_topics)

                category_counts[cat] = category_counts.get(cat, 0) + 1
                if topic:
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1

                nodes_data.append({
                    "id": str(n),
                    "name": name,
                    "kind": kind,
                    "ref": ref,
                    "category": cat,
                    "topic": topic,
                    "is_curriculum": is_curr,
                })

            edges_data = []
            for u, v, d in G.edges(data=True):
                edges_data.append({
                    "source": str(u),
                    "target": str(v),
                    "rel": d.get("rel", "links_to"),
                })

            self._send_json({
                "nodes": nodes_data,
                "edges": edges_data,
                "categories": category_counts,
                "topics": topic_counts,
                "edu_topics": edu_topics,
            })
            return

        elif path == "/api/tasks":
            db = DB(str(DB_PATH))
            rows = db.con.execute(
                "SELECT id, task, model, status, summary, started FROM tasks ORDER BY id DESC LIMIT 50"
            ).fetchall()
            tasks = []
            for r in rows:
                ts = r[5]
                ts_str = "-"
                if ts:
                    try:
                        ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
                    except Exception:
                        ts_str = str(ts)
                tasks.append({
                    "id": r[0],
                    "task": r[1],
                    "model": r[2],
                    "status": r[3],
                    "summary": r[4],
                    "created_at": ts_str,
                })
            self._send_json(tasks)
            return

        elif path == "/api/task_steps":
            tid = query.get("id", [None])[0]
            if not tid:
                self._send_json({"error": "Missing task id"}, 400)
                return
            db = DB(str(DB_PATH))
            steps = db.get_steps(int(tid))
            self._send_json(steps)
            return

        elif path == "/api/agent_dashboard":
            db = DB(str(DB_PATH))
            total_tasks = db.con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            status_counts = dict(db.con.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
            finished_tasks = status_counts.get("finished", 0)
            failed_tasks = status_counts.get("failed", 0)
            running_tasks = status_counts.get("running", 0)
            stuck_tasks = status_counts.get("stuck", 0)
            max_steps_tasks = status_counts.get("max_steps", 0)
            success_rate = round((finished_tasks / max(total_tasks, 1)) * 100, 1)

            total_steps = db.con.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
            total_subtasks = db.con.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0]
            total_facts = db.con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

            dur_row = db.con.execute(
                "SELECT AVG(finished - started) FROM tasks WHERE finished > started AND status='finished'"
            ).fetchone()
            avg_duration = round(dur_row[0], 1) if (dur_row and dur_row[0]) else 0.0

            tool_rows = db.con.execute(
                "SELECT tool, COUNT(*) FROM steps GROUP BY tool ORDER BY COUNT(*) DESC LIMIT 8"
            ).fetchall()
            tool_usage = [
                {"tool": r[0], "count": r[1], "pct": round((r[1] / max(total_steps, 1)) * 100, 1)}
                for r in tool_rows
            ]

            model_rows = db.con.execute(
                "SELECT model, COUNT(*), SUM(CASE WHEN status='finished' THEN 1 ELSE 0 END) FROM tasks GROUP BY model"
            ).fetchall()
            model_stats = [
                {"model": r[0] or "default", "total": r[1], "finished": r[2]}
                for r in model_rows
            ]

            facts_rows = db.con.execute(
                "SELECT id, task_id, kind, text FROM facts ORDER BY id DESC LIMIT 5"
            ).fetchall()
            recent_facts = [
                {"id": r[0], "task_id": r[1], "kind": r[2], "text": r[3]}
                for r in facts_rows
            ]

            task_rows = db.con.execute("""
                SELECT t.id, t.task, t.model, t.status, t.summary, t.started, t.finished,
                       (SELECT COUNT(*) FROM steps s WHERE s.task_id = t.id) as step_count
                FROM tasks t
                ORDER BY t.id DESC LIMIT 60
            """).fetchall()

            tasks_list = []
            for r in task_rows:
                ts = r[5]
                ts_str = "-"
                if ts:
                    try:
                        ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
                    except Exception:
                        ts_str = str(ts)
                dur = round(r[6] - r[5], 1) if (r[6] and r[5] and r[6] > r[5]) else 0
                tasks_list.append({
                    "id": r[0],
                    "task": r[1],
                    "model": r[2],
                    "status": r[3],
                    "summary": r[4],
                    "created_at": ts_str,
                    "duration": dur,
                    "step_count": r[7],
                })

            self._send_json({
                "kpis": {
                    "total_tasks": total_tasks,
                    "finished_tasks": finished_tasks,
                    "failed_tasks": failed_tasks,
                    "running_tasks": running_tasks,
                    "stuck_tasks": stuck_tasks,
                    "max_steps_tasks": max_steps_tasks,
                    "success_rate": success_rate,
                    "total_steps": total_steps,
                    "total_subtasks": total_subtasks,
                    "total_facts": total_facts,
                    "avg_duration": avg_duration,
                },
                "status_breakdown": status_counts,
                "tool_usage": tool_usage,
                "model_stats": model_stats,
                "recent_facts": recent_facts,
                "tasks": tasks_list,
            })
            return

        elif path == "/api/task_trace":
            tid = query.get("id", [None])[0]
            if not tid:
                self._send_json({"error": "Missing task id"}, 400)
                return
            db = DB(str(DB_PATH))
            task_data = db.get_task(int(tid))
            if not task_data:
                self._send_json({"error": "Task not found"}, 404)
                return
            steps = db.get_steps(int(tid))
            facts_rows = db.con.execute(
                "SELECT kind, text FROM facts WHERE task_id=?", (int(tid),)
            ).fetchall()
            subtasks_rows = db.con.execute(
                "SELECT id, title, spec, status, assigned_role, result_summary, feedback FROM subtasks WHERE task_id=?", (int(tid),)
            ).fetchall()
            self._send_json({
                "task": task_data,
                "steps": steps,
                "facts": [{"kind": r[0], "text": r[1]} for r in facts_rows],
                "subtasks": [
                    {
                        "id": r[0],
                        "title": r[1],
                        "spec": r[2],
                        "status": r[3],
                        "role": r[4],
                        "summary": r[5],
                        "feedback": r[6],
                    }
                    for r in subtasks_rows
                ]
            })
            return

        elif path == "/api/note":
            note_name = query.get("name", [""])[0].strip()
            node_id = query.get("id", [""])[0].strip()
            node_kind = query.get("kind", [""])[0].strip()
            node_ref = query.get("ref", [""])[0].strip()

            if not note_name and not node_id:
                self._send_json({"error": "Missing note name or id"}, 400)
                return

            result = resolve_node_note(note_name, node_id, node_kind, node_ref)
            self._send_json(result)
            return

        elif path == "/api/workspaces":
            ws_root = _PROJECT_ROOT / "data" / "workspaces"
            workspaces = []
            if ws_root.is_dir():
                for d in ws_root.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        files = [f for f in d.rglob("*") if f.is_file() and not any(p.startswith(".") or p in {"__pycache__", ".pytest_cache"} for p in f.parts)]
                        has_tests = any(f.name.startswith("test_") or f.name.endswith("_test.py") for f in files)
                        mtime = d.stat().st_mtime
                        workspaces.append({
                            "name": d.name,
                            "path": str(d.relative_to(_PROJECT_ROOT)).replace("\\", "/"),
                            "file_count": len(files),
                            "has_tests": has_tests,
                            "mtime": mtime,
                            "mtime_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
                        })
            workspaces.sort(key=lambda x: x["mtime"], reverse=True)
            self._send_json(workspaces)
            return

        elif path == "/api/workspace/files":
            ws_name = query.get("workspace", [""])[0].strip()
            if not ws_name:
                self._send_json({"error": "Missing workspace parameter"}, 400)
                return
            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / ws_name).resolve()
            if not ws_dir.is_dir():
                self._send_json({"error": "Workspace not found"}, 404)
                return

            files_data = []
            for f in sorted(ws_dir.rglob("*")):
                if f.is_file() and not any(p.startswith(".") or p in {"__pycache__", ".pytest_cache", ".venv"} for p in f.parts):
                    rel = str(f.relative_to(ws_dir)).replace("\\", "/")
                    files_data.append({
                        "name": f.name,
                        "path": rel,
                        "size": f.stat().st_size,
                        "ext": f.suffix.lower(),
                        "is_test": f.name.startswith("test_") or f.name.endswith("_test.py"),
                        "mtime": f.stat().st_mtime,
                    })
            self._send_json({"workspace": ws_name, "files": files_data})
            return

        elif path == "/api/workspace/file":
            ws_name = query.get("workspace", [""])[0].strip()
            file_rel = query.get("path", [""])[0].strip()
            if not ws_name or not file_rel:
                self._send_json({"error": "Missing workspace or path parameter"}, 400)
                return
            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / ws_name).resolve()
            target_file = (ws_dir / file_rel).resolve()
            if not str(target_file).startswith(str(ws_dir)):
                self._send_json({"error": "Forbidden path"}, 403)
                return
            if not target_file.is_file():
                self._send_json({"error": "File not found"}, 404)
                return

            content = target_file.read_text(encoding="utf-8", errors="replace")
            db = DB(str(DB_PATH))
            ref = f"workspace:{ws_name}/{file_rel.replace('\\', '/')}"

            node_row = db.con.execute("SELECT id, name, kind FROM nodes WHERE ref=?", (ref,)).fetchone()
            node_id = node_row[0] if node_row else None
            links = []
            if node_id:
                out_rows = db.con.execute("""
                    SELECT n.id, n.name, n.kind, e.rel, n.ref, 'outgoing' as dir
                    FROM edges e JOIN nodes n ON e.dst = n.id WHERE e.src = ?
                """, (node_id,)).fetchall()
                in_rows = db.con.execute("""
                    SELECT n.id, n.name, n.kind, e.rel, n.ref, 'incoming' as dir
                    FROM edges e JOIN nodes n ON e.src = n.id WHERE e.dst = ?
                """, (node_id,)).fetchall()
                links = [
                    {"id": r[0], "name": r[1], "kind": r[2], "rel": r[3], "ref": r[4], "direction": r[5]}
                    for r in (out_rows + in_rows)
                ]

            self._send_json({
                "workspace": ws_name,
                "path": file_rel,
                "name": target_file.name,
                "size": len(content),
                "content": content,
                "node_id": node_id,
                "ref": ref,
                "links": links
            })
            return

        elif path == "/api/graph/nodes_search":
            q = query.get("q", [""])[0].strip()
            limit = int(query.get("limit", [30])[0])
            db = DB(str(DB_PATH))
            vault_p = Path(DEFAULT_VAULT)
            edu_topics = list_study_topics(vault_p) if vault_p.is_dir() else []
            if q:
                like_pattern = f"%{q}%"
                rows = db.con.execute(
                    "SELECT id, name, kind, ref FROM nodes WHERE name LIKE ? OR ref LIKE ? LIMIT ?",
                    (like_pattern, like_pattern, limit)
                ).fetchall()
            else:
                rows = db.con.execute(
                    "SELECT id, name, kind, ref FROM nodes ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()

            results = []
            for r in rows:
                cat, topic, is_curr = classify_node(r[1], r[2], r[3], edu_topics)
                results.append({
                    "id": r[0],
                    "name": r[1],
                    "kind": r[2],
                    "ref": r[3],
                    "category": cat,
                    "topic": topic
                })
            self._send_json(results)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as e:
            traceback.print_exc()
            self._send_json({"error": str(e)}, 500)

    def _handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            body = json.loads(post_body)
        except Exception:
            body = {}

        if path == "/api/study/generate":
            topic = body.get("topic", "").strip()
            if not topic:
                self._send_json({"error": "Topic is required"}, 400)
                return

            vault_p = Path(DEFAULT_VAULT).resolve()
            db = DB(str(DB_PATH))

            # 1. Plan curriculum
            plan = generate_curriculum_plan(topic)

            # 2. Write notes to Obsidian
            created_files = write_curriculum_notes(plan, vault_p)

            # 3. Index into graph
            stats = index_vault(vault_p, db=db, verbose=False)

            self._send_json({
                "success": True,
                "topic": topic,
                "notes_created": len(created_files),
                "graph_stats": stats,
                "curriculum_name": f"{re.sub(r'[^\\w\\-]', '_', plan['topic']).strip('_')}_Curriculum",
            })
            return

        elif path == "/api/study/ask":
            question = body.get("question", "").strip()
            if not question:
                self._send_json({"error": "Question is required"}, 400)
                return

            db = DB(str(DB_PATH))
            answer = query_study_graph(question, db=db)
            self._send_json({"question": question, "answer": answer})
            return

        elif path == "/api/note/save":
            rel_path = body.get("rel_path", "").strip()
            content = body.get("content", "")
            if not rel_path:
                self._send_json({"error": "rel_path is required"}, 400)
                return

            vault_p = Path(DEFAULT_VAULT)
            target_file = (vault_p / rel_path).resolve()
            if not str(target_file).startswith(str(vault_p.resolve())):
                self._send_json({"error": "Forbidden path"}, 403)
                return

            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")

            # Re-index vault so new note is in memory.db
            db = DB(str(DB_PATH))
            try:
                index_vault(vault_p, db=db, verbose=False)
            except Exception:
                pass

            self._send_json({
                "success": True,
                "name": target_file.name,
                "rel_path": str(target_file.relative_to(vault_p)).replace("\\", "/"),
            })
            return

        elif path == "/api/note/synthesize":
            topic = body.get("topic", "").strip() or body.get("name", "").strip()
            if not topic:
                self._send_json({"error": "Topic is required"}, 400)
                return

            vault_p = Path(DEFAULT_VAULT).resolve()
            db = DB(str(DB_PATH))

            plan = generate_curriculum_plan(topic)
            created_files = write_curriculum_notes(plan, vault_p)
            try:
                index_vault(vault_p, db=db, verbose=False)
            except Exception:
                pass

            main_topic_name = f"{re.sub(r'[^\w\-]', '_', plan['topic']).strip('_')}_Curriculum"
            resolved = resolve_node_note(main_topic_name)
            self._send_json({
                "success": True,
                "topic": topic,
                "notes_created": len(created_files),
                "note": resolved,
            })
            return

        elif path == "/api/workspace/file":
            ws_name = body.get("workspace", "").strip()
            rel_path = body.get("path", "").strip()
            content = body.get("content", "")

            if not ws_name or not rel_path:
                self._send_json({"error": "workspace and path are required"}, 400)
                return

            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / ws_name).resolve()
            target_file = (ws_dir / rel_path).resolve()
            if not str(target_file).startswith(str(ws_dir)):
                self._send_json({"error": "Forbidden path"}, 403)
                return

            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")

            # Re-index workspace into graph
            db = DB(str(DB_PATH))
            stats = index_workspace_project(ws_dir, db)

            self._send_json({
                "success": True,
                "workspace": ws_name,
                "path": rel_path,
                "size": len(content),
                "graph_stats": stats,
            })
            return

        elif path == "/api/workspace/run":
            ws_name = body.get("workspace", "").strip()
            command = body.get("command", "pytest").strip()
            target_file = body.get("file", "").strip()
            args = body.get("args", "").strip()

            if not ws_name:
                self._send_json({"error": "workspace is required"}, 400)
                return
            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / ws_name).resolve()
            if not ws_dir.is_dir():
                self._send_json({"error": "Workspace not found"}, 404)
                return

            cmd_args = [sys.executable]
            if command == "pytest":
                cmd_args.extend(["-m", "pytest", "-v"])
                if target_file:
                    is_test_file = target_file.startswith("test_") or target_file.endswith("_test.py")
                    target_p = ws_dir / target_file
                    if is_test_file and target_p.is_file():
                        cmd_args.append(target_file)
                    else:
                        cand_test = f"test_{target_file}"
                        if (ws_dir / cand_test).is_file():
                            cmd_args.append(cand_test)
                        # otherwise omit target_file to let pytest auto-discover workspace tests
            elif command == "python":
                if not target_file:
                    self._send_json({"error": "target file is required for python execution"}, 400)
                    return
                cmd_args.append(target_file)
            else:
                if command.startswith("pytest"):
                    cmd_args.extend(["-m", "pytest"] + command.split()[1:])
                elif command.startswith("python"):
                    cmd_args.extend(command.split()[1:])
                else:
                    cmd_args.extend(["-c", command])

            if args:
                cmd_args.extend(args.split())

            t0 = time.time()
            try:
                proc = subprocess.run(
                    cmd_args,
                    cwd=str(ws_dir),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    env={**os.environ, "PYTHONPATH": str(ws_dir)},
                )
                duration = round(time.time() - t0, 3)
                self._send_json({
                    "success": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "duration": duration,
                    "command": " ".join(cmd_args),
                })
            except subprocess.TimeoutExpired:
                self._send_json({
                    "success": False,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": "Execution timed out (45s limit exceeded).",
                    "duration": round(time.time() - t0, 3),
                    "command": " ".join(cmd_args),
                })
            except Exception as ex:
                self._send_json({
                    "success": False,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": str(ex),
                    "duration": round(time.time() - t0, 3),
                    "command": " ".join(cmd_args),
                })
            return

        elif path == "/api/workspace/agent_code":
            ws_name = body.get("workspace", "").strip()
            prompt = body.get("prompt", "").strip()
            target_file_name = body.get("file", "").strip()
            mode = body.get("mode", "offline").strip()
            model_name = body.get("model", "qwen2.5-coder:3b").strip()
            link_node_id = body.get("link_node_id")

            if not ws_name or not prompt:
                self._send_json({"error": "workspace and prompt are required"}, 400)
                return

            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / ws_name).resolve()
            ws_dir.mkdir(parents=True, exist_ok=True)

            existing_files = list(ws_dir.glob("*.py"))
            context_code = ""
            if existing_files:
                for ef in existing_files[:3]:
                    txt = ef.read_text(encoding="utf-8", errors="replace")
                    context_code += f"\n# --- File: {ef.name} ---\n{txt[:1200]}\n"

            sys_prompt = (
                "You are an expert autonomous software engineer working offline. "
                "Write clean, production-ready Python code. "
                "Output your code inside a single ```python ... ``` code block. "
                "Include unit tests if appropriate."
            )
            user_msg = f"Task: {prompt}\n\nWorkspace existing files:\n{context_code}\n\nTarget File: {target_file_name or 'Auto-detect best filename'}"

            code_text = ""
            agent_commentary = ""
            try:
                resp = chat_raw(
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    model=model_name if mode == "offline" else None,
                    timeout=120,
                )
                msg_content = resp.get("message", {}).get("content", "")
                agent_commentary = msg_content

                code_blocks = re.findall(r"```(?:python)?\s*([\s\S]*?)```", msg_content)
                if code_blocks:
                    code_text = code_blocks[0].strip()
                else:
                    code_text = msg_content.strip()
            except Exception as e:
                agent_commentary = f"Generated offline template (Ollama status: {str(e)})"
                code_text = f'''"""
{prompt}
Autonomously prepared by Offline Agent Studio.
"""

def solution():
    """Implementation for: {prompt}"""
    print("Executing solution...")
    return True

if __name__ == "__main__":
    solution()
'''

            if not target_file_name:
                first_line = prompt.lower()
                if "test" in first_line:
                    target_file_name = "test_agent_gen.py"
                else:
                    target_file_name = "agent_solution.py"

            saved_file = ws_dir / target_file_name
            saved_file.write_text(code_text, encoding="utf-8")

            db = DB(str(DB_PATH))
            g_stats = index_workspace_project(ws_dir, db)

            created_node_id = None
            if link_node_id:
                try:
                    file_ref = f"workspace:{ws_name}/{target_file_name}"
                    node_row = db.con.execute("SELECT id FROM nodes WHERE ref=?", (file_ref,)).fetchone()
                    if node_row:
                        created_node_id = node_row[0]
                        db.add_edge(created_node_id, int(link_node_id), "implements")
                except Exception:
                    pass

            self._send_json({
                "success": True,
                "file": target_file_name,
                "code": code_text,
                "commentary": agent_commentary,
                "graph_stats": g_stats,
                "created_node_id": created_node_id,
            })
            return

        elif path == "/api/workspace/create":
            name = re.sub(r"[^\w\-]", "_", body.get("name", "").strip()).strip("_")
            desc = body.get("description", "").strip()
            if not name:
                self._send_json({"error": "name is required"}, 400)
                return
            ws_dir = (_PROJECT_ROOT / "data" / "workspaces" / name).resolve()
            if ws_dir.exists():
                self._send_json({"error": "Workspace project already exists"}, 400)
                return
            ws_dir.mkdir(parents=True, exist_ok=True)
            (ws_dir / "README.md").write_text(f"# {name}\n\n{desc or 'Agent workspace project created in Agent Studio.'}\n", encoding="utf-8")
            (ws_dir / "main.py").write_text(f'"""\n{name} entry point.\n"""\n\ndef main():\n    print("Hello from {name}!")\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
            (ws_dir / "test_main.py").write_text(f'"""\nTests for {name}.\n"""\nimport main\n\ndef test_main():\n    assert callable(main.main)\n', encoding="utf-8")

            db = DB(str(DB_PATH))
            stats = index_workspace_project(ws_dir, db)
            self._send_json({
                "success": True,
                "name": name,
                "path": str(ws_dir.relative_to(_PROJECT_ROOT)).replace("\\", "/"),
                "graph_stats": stats,
            })
            return

        elif path == "/api/graph/link":
            src_id = body.get("src_id")
            src_ref = body.get("src_ref")
            dst_id = body.get("dst_id")
            dst_ref = body.get("dst_ref")
            rel = body.get("rel", "implements").strip() or "implements"

            db = DB(str(DB_PATH))
            if not src_id and src_ref:
                r = db.con.execute("SELECT id FROM nodes WHERE ref=?", (src_ref,)).fetchone()
                if r:
                    src_id = r[0]
            if not dst_id and dst_ref:
                r = db.con.execute("SELECT id FROM nodes WHERE ref=?", (dst_ref,)).fetchone()
                if r:
                    dst_id = r[0]

            if not src_id or not dst_id:
                self._send_json({"error": "Valid source and destination nodes required"}, 400)
                return

            db.add_edge(int(src_id), int(dst_id), rel)

            s_name = db.con.execute("SELECT name FROM nodes WHERE id=?", (int(src_id),)).fetchone()
            d_name = db.con.execute("SELECT name FROM nodes WHERE id=?", (int(dst_id),)).fetchone()

            self._send_json({
                "success": True,
                "src_id": int(src_id),
                "src_name": s_name[0] if s_name else str(src_id),
                "dst_id": int(dst_id),
                "dst_name": d_name[0] if d_name else str(dst_id),
                "rel": rel,
            })
            return

        elif path == "/api/graph/unlink":
            src_id = body.get("src_id")
            dst_id = body.get("dst_id")
            rel = body.get("rel")

            if not src_id or not dst_id:
                self._send_json({"error": "src_id and dst_id are required"}, 400)
                return

            db = DB(str(DB_PATH))
            if rel:
                db.con.execute("DELETE FROM edges WHERE src=? AND dst=? AND rel=?", (int(src_id), int(dst_id), rel))
            else:
                db.con.execute("DELETE FROM edges WHERE (src=? AND dst=?) OR (src=? AND dst=?)", (int(src_id), int(dst_id), int(dst_id), int(src_id)))
            db.con.commit()

            self._send_json({"success": True})
            return

        self.send_error(404, "Endpoint not found")


def run_server(port: int = 8000):
    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, AgentStudioHandler)
    print("=" * 65)
    print(f"  AI AGENT & KNOWLEDGE GRAPH STUDIO RUNNING")
    print("=" * 65)
    print(f"  Web UI URL:   http://localhost:{port}")
    print(f"  Obsidian:     {DEFAULT_VAULT}")
    print(f"  Memory DB:    {DB_PATH}")
    print("  Press Ctrl+C to stop.")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8000
    run_server(port)
