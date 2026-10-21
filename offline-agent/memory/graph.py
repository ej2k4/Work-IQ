"""
graph.py – Code graph, concept graph, and hybrid retrieval.

Extracts symbol relationships from code (classes, functions, calls, imports)
and concepts from Markdown/Obsidian (notes, wikilinks, tags) into SQLite
nodes and edges tables.

Provides NetworkX graph representation and hybrid retrieval:
  1. Vector search yields seed chunks.
  2. Graph maps seeds to nodes and traverses calls/imports/links edges.
  3. Graph-distance bonus re-ranks candidates for multi-file impact queries.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

import networkx as nx

from memory.db import DB

# Regex for Markdown wikilinks [[Target]] or [[Target|Alias]] or [[Target#Heading]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
# Regex for Markdown tags (e.g. #python, #bug/fix, ignoring # in code blocks or URLs)
_TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_\-\/]+)")


# ── Code AST Analyzer ─────────────────────────────────────────────────────────

class PythonCodeVisitor(ast.NodeVisitor):
    """AST visitor extracting files, classes, functions, calls, and imports."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.current_scope: list[str] = []
        self.classes: list[dict] = []
        self.functions: list[dict] = []
        self.imports: list[dict] = []
        self.calls: list[dict] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({
                "module": alias.name,
                "name": alias.name,
                "line": node.lineno,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            full_name = f"{mod}.{alias.name}" if mod else alias.name
            self.imports.append({
                "module": mod,
                "name": alias.name,
                "full_name": full_name,
                "line": node.lineno,
            })
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        scope = "::".join(self.current_scope + [node.name])
        self.classes.append({
            "name": node.name,
            "scope": scope,
            "line": node.lineno,
            "parent": self.current_scope[-1] if self.current_scope else None,
        })
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        scope = "::".join(self.current_scope + [node.name])
        parent = self.current_scope[-1] if self.current_scope else None
        self.functions.append({
            "name": node.name,
            "scope": scope,
            "line": node.lineno,
            "parent": parent,
        })
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # handle same as FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        caller = self.current_scope[-1] if self.current_scope else None
        callee_name = None
        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee_name = node.func.attr

        if callee_name and caller:
            self.calls.append({
                "caller": caller,
                "callee": callee_name,
                "line": node.lineno,
            })
        self.generic_visit(node)


# ── Code Ingestion ───────────────────────────────────────────────────────────

def index_python_code_graph(file_path: Path, code_text: str, db: DB,
                           root_path: Path | None = None) -> dict:
    """
    Parse a Python file and record its classes, functions, calls, and imports
    into the nodes and edges tables in SQLite.
    """
    rel_path = str(file_path.relative_to(root_path)) if root_path else str(file_path)
    norm_path = rel_path.replace("\\", "/")

    stats = {"nodes": 0, "edges": 0}

    try:
        tree = ast.parse(code_text, filename=norm_path)
    except SyntaxError:
        return stats  # skip files with syntax errors

    visitor = PythonCodeVisitor(norm_path)
    visitor.visit(tree)

    # 1. File node
    file_node_id = db.upsert_node("file", Path(norm_path).name, norm_path)
    stats["nodes"] += 1

    # Map name -> node_id for local scopes
    local_func_nodes: dict[str, int] = {}

    # 2. Classes
    for cls in visitor.classes:
        ref = f"{norm_path}:{cls['line']}"
        cls_id = db.upsert_node("class", cls["name"], ref)
        db.add_edge(file_node_id, cls_id, "defines")
        stats["nodes"] += 1
        stats["edges"] += 1

    # 3. Functions
    for fn in visitor.functions:
        ref = f"{norm_path}:{fn['line']}"
        fn_id = db.upsert_node("function", fn["name"], ref)
        local_func_nodes[fn["name"]] = fn_id
        db.add_edge(file_node_id, fn_id, "defines")
        stats["nodes"] += 1
        stats["edges"] += 1

    # 4. Imports
    for imp in visitor.imports:
        mod_name = imp.get("name") or imp.get("module")
        if mod_name:
            imp_id = db.upsert_node("module", mod_name, f"import:{mod_name}")
            db.add_edge(file_node_id, imp_id, "imports")
            stats["edges"] += 1

    # 5. Calls
    for call in visitor.calls:
        caller_name = call["caller"]
        callee_name = call["callee"]
        caller_id = local_func_nodes.get(caller_name)
        if not caller_id:
            caller_id = db.upsert_node("function", caller_name, f"{norm_path}:{call['line']}")
        callee_id = db.upsert_node("function", callee_name, f"symbol:{callee_name}")
        db.add_edge(caller_id, callee_id, "calls")
        stats["edges"] += 1

    return stats


# ── Concept Graph (Obsidian / Markdown) ──────────────────────────────────────

def index_markdown_concept_graph(file_path: Path, md_text: str, db: DB,
                                root_path: Path | None = None) -> dict:
    """
    Parse a Markdown file and record note, wikilinks [[Target]], and #tags
    into the nodes and edges tables in SQLite.
    """
    rel_path = str(file_path.relative_to(root_path)) if root_path else str(file_path)
    norm_path = rel_path.replace("\\", "/")
    note_title = file_path.stem

    stats = {"nodes": 0, "edges": 0}

    # 1. Note node
    note_id = db.upsert_node("note", note_title, norm_path)
    stats["nodes"] += 1

    # 2. Wikilinks [[target]]
    for link_target in _WIKILINK_RE.findall(md_text):
        target_name = link_target.strip()
        if target_name:
            target_id = db.upsert_node("note", target_name, f"note:{target_name}")
            db.add_edge(note_id, target_id, "links_to")
            stats["edges"] += 1

    # 3. Tags #tag
    for tag in _TAG_RE.findall(md_text):
        tag_name = tag.strip().lower()
        if tag_name:
            tag_id = db.upsert_node("tag", f"#{tag_name}", f"tag:{tag_name}")
            db.add_edge(note_id, tag_id, "tagged")
            stats["edges"] += 1

    return stats


# ── Directory Graph Ingestion ────────────────────────────────────────────────

def index_repository_graph(directory: str | Path, db: DB,
                           verbose: bool = False) -> dict:
    """
    Walk a codebase/vault, index all Python and Markdown files into the code/concept graph.
    """
    root = Path(directory).resolve()
    stats = {"files": 0, "nodes": 0, "edges": 0}

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") or part in {"__pycache__", ".venv", "node_modules", "data", "eval"}
               for part in rel_parts):
            continue

        ext = p.suffix.lower()
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if ext == ".py":
            res = index_python_code_graph(p, content, db, root_path=root)
            stats["files"] += 1
            stats["nodes"] += res["nodes"]
            stats["edges"] += res["edges"]
        elif ext in {".md", ".markdown"}:
            res = index_markdown_concept_graph(p, content, db, root_path=root)
            stats["files"] += 1
            stats["nodes"] += res["nodes"]
            stats["edges"] += res["edges"]

    if verbose:
        print(f"Indexed graph for {directory}: {stats}")
    return stats


# ── Workspace Projects & Agent Code Ingestion ────────────────────────────────

def index_workspace_project(workspace_dir: str | Path, db: DB, verbose: bool = False) -> dict:
    """
    Index an agent workspace project into the graph.
    Creates a project node, connects contained files, and extracts AST symbols.
    """
    ws = Path(workspace_dir).resolve()
    if not ws.is_dir():
        return {"nodes": 0, "edges": 0, "files": 0}

    stats = {"nodes": 0, "edges": 0, "files": 0}
    proj_name = ws.name
    # 1. Project node
    proj_id = db.upsert_node("project", proj_name, f"workspace:{proj_name}")
    stats["nodes"] += 1

    file_nodes: dict[str, int] = {}

    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(ws).parts
        if any(part.startswith(".") or part in {"__pycache__", ".pytest_cache", ".venv", "node_modules"} for part in rel_parts):
            continue

        ext = p.suffix.lower()
        if ext not in {".py", ".md", ".json", ".txt", ".sh", ".toml", ".yaml", ".yml"}:
            continue

        rel_path = str(p.relative_to(ws)).replace("\\", "/")
        ref = f"workspace:{proj_name}/{rel_path}"

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        file_id = db.upsert_node("file", p.name, ref)
        file_nodes[rel_path] = file_id
        db.add_edge(proj_id, file_id, "contains")
        stats["nodes"] += 1
        stats["edges"] += 1
        stats["files"] += 1

        if ext == ".py":
            try:
                tree = ast.parse(content, filename=rel_path)
                visitor = PythonCodeVisitor(rel_path)
                visitor.visit(tree)
                local_funcs = {}

                for cls in visitor.classes:
                    cls_id = db.upsert_node("class", cls["name"], f"{ref}:{cls['line']}")
                    db.add_edge(file_id, cls_id, "defines")
                    stats["nodes"] += 1
                    stats["edges"] += 1

                for fn in visitor.functions:
                    fn_id = db.upsert_node("function", fn["name"], f"{ref}:{fn['line']}")
                    local_funcs[fn["name"]] = fn_id
                    db.add_edge(file_id, fn_id, "defines")
                    stats["nodes"] += 1
                    stats["edges"] += 1

                for imp in visitor.imports:
                    mod_name = imp.get("name") or imp.get("module")
                    if mod_name:
                        imp_id = db.upsert_node("module", mod_name, f"import:{mod_name}")
                        db.add_edge(file_id, imp_id, "imports")
                        stats["edges"] += 1

                for call in visitor.calls:
                    caller_id = local_funcs.get(call["caller"])
                    if caller_id:
                        callee_id = db.upsert_node("function", call["callee"], f"symbol:{call['callee']}")
                        db.add_edge(caller_id, callee_id, "calls")
                        stats["edges"] += 1

            except SyntaxError:
                pass

        elif ext == ".md":
            for link in _WIKILINK_RE.findall(content):
                target_name = link.strip()
                if target_name:
                    target_id = db.upsert_node("note", target_name, f"note:{target_name}")
                    db.add_edge(file_id, target_id, "links_to")
                    stats["edges"] += 1

    # Link test files to their target source files if naming matches
    for rel_path, file_id in file_nodes.items():
        fname = Path(rel_path).name
        if fname.startswith("test_") and fname.endswith(".py"):
            target_name = fname[5:]
            for other_rel, other_id in file_nodes.items():
                if Path(other_rel).name == target_name:
                    db.add_edge(file_id, other_id, "tests")
                    stats["edges"] += 1

    if verbose:
        print(f"Indexed workspace project {proj_name}: {stats}")
    return stats


def index_all_workspaces(workspaces_root: str | Path, db: DB, verbose: bool = False) -> dict:
    """Index all workspaces under data/workspaces into the graph."""
    ws_dir = Path(workspaces_root).resolve()
    if not ws_dir.is_dir():
        return {"workspaces": 0, "nodes": 0, "edges": 0, "files": 0}

    total_stats = {"workspaces": 0, "nodes": 0, "edges": 0, "files": 0}
    for sub in sorted(ws_dir.iterdir()):
        if sub.is_dir() and not sub.name.startswith("."):
            s = index_workspace_project(sub, db, verbose=verbose)
            total_stats["workspaces"] += 1
            total_stats["nodes"] += s["nodes"]
            total_stats["edges"] += s["edges"]
            total_stats["files"] += s["files"]
    return total_stats


# ── NetworkX Graph & Traversal ───────────────────────────────────────────────

def load_graph(db: DB) -> nx.DiGraph:
    """
    Construct an in-memory NetworkX DiGraph from the SQLite nodes and edges tables.
    """
    G = nx.DiGraph()
    nodes, edges = db.all_graph()

    for n in nodes:
        G.add_node(n["id"], kind=n["kind"], name=n["name"], ref=n["ref"])

    for e in edges:
        G.add_edge(e["src"], e["dst"], rel=e["rel"])

    return G


def find_impact(G: nx.DiGraph, symbol_name: str, max_hops: int = 2) -> list[dict]:
    """
    Find all nodes that depend on or call symbol_name (e.g. for answering:
    'What breaks if I change function Y?').

    Traverses incoming edges along 'calls', 'imports', 'links_to', 'defines'.
    """
    # Find matching target node(s)
    target_ids = [n for n, d in G.nodes(data=True) if d.get("name") == symbol_name]
    if not target_ids:
        # Try case-insensitive or partial match
        target_ids = [
            n for n, d in G.nodes(data=True)
            if symbol_name.lower() in d.get("name", "").lower()
        ]

    if not target_ids:
        return []

    impacted: list[dict] = []
    visited = set()

    for start_id in target_ids:
        queue = [(start_id, 0)]
        visited.add(start_id)

        while queue:
            curr, depth = queue.pop(0)
            if depth > 0:
                node_data = G.nodes[curr]
                impacted.append({
                    "id": curr,
                    "kind": node_data.get("kind"),
                    "name": node_data.get("name"),
                    "ref": node_data.get("ref"),
                    "depth": depth,
                })

            if depth < max_hops:
                # Inspect incoming edges: who calls or imports curr?
                for pred in G.predecessors(curr):
                    if pred not in visited:
                        visited.add(pred)
                        queue.append((pred, depth + 1))

    return impacted


def find_dependencies(G: nx.DiGraph, symbol_name: str, max_hops: int = 2) -> list[dict]:
    """
    Find what symbol_name depends on (outgoing calls, imports, defines).
    """
    target_ids = [n for n, d in G.nodes(data=True) if d.get("name") == symbol_name]
    if not target_ids:
        return []

    deps: list[dict] = []
    visited = set()

    for start_id in target_ids:
        queue = [(start_id, 0)]
        visited.add(start_id)

        while queue:
            curr, depth = queue.pop(0)
            if depth > 0:
                node_data = G.nodes[curr]
                deps.append({
                    "id": curr,
                    "kind": node_data.get("kind"),
                    "name": node_data.get("name"),
                    "ref": node_data.get("ref"),
                    "depth": depth,
                })

            if depth < max_hops:
                for succ in G.successors(curr):
                    if succ not in visited:
                        visited.add(succ)
                        queue.append((succ, depth + 1))

    return deps


# ── Hybrid Retrieval ─────────────────────────────────────────────────────────

def hybrid_search(
    query: str,
    db: DB,
    top_k: int = 5,
    graph_hops: int = 2,
    graph_weight: float = 0.25,
) -> dict:
    """
    Hybrid Retrieval Algorithm (plan.md Section 4.5):
      1. Embed query and retrieve top-k chunks by cosine similarity (seeds).
      2. Map seed chunks to graph nodes (matching file path / symbols).
      3. Expand 1-2 hops along calls, imports, links_to, touched_by.
      4. Re-rank with graph connectivity bonus.
      5. Return seeds + connected impact graph.
    """
    from memory.vectors import embed, cosine_search

    # Step 1: Vector search
    qvec = embed(query)
    rows = db.all_embeddings()
    seed_chunks = cosine_search(qvec, rows, top_k=top_k, min_score=0.0)

    # Step 2: Load graph & map seed files
    G = load_graph(db)
    connected_nodes: list[dict] = []
    connected_node_ids = set()

    for sc in seed_chunks:
        fpath = db.chunk_path(sc["chunk_id"]) or ""
        norm_fpath = fpath.replace("\\", "/")
        fname = Path(norm_fpath).name

        # Find nodes in this file
        matched_nodes = [
            n for n, d in G.nodes(data=True)
            if norm_fpath in d.get("ref", "").replace("\\", "/") or d.get("name") == fname
        ]

        # Step 3: Expand 1-2 hops
        for nid in matched_nodes:
            # Check callers / dependents
            for pred in G.predecessors(nid):
                if pred not in connected_node_ids:
                    connected_node_ids.add(pred)
                    d = G.nodes[pred]
                    edge_data = G.get_edge_data(pred, nid)
                    connected_nodes.append({
                        "id": pred,
                        "kind": d.get("kind"),
                        "name": d.get("name"),
                        "ref": d.get("ref"),
                        "relation": edge_data.get("rel") if edge_data else "related_to",
                        "related_symbol": G.nodes[nid].get("name"),
                        "direction": "caller",
                    })

            # Check callees / dependencies
            for succ in G.successors(nid):
                if succ not in connected_node_ids:
                    connected_node_ids.add(succ)
                    d = G.nodes[succ]
                    edge_data = G.get_edge_data(nid, succ)
                    connected_nodes.append({
                        "id": succ,
                        "kind": d.get("kind"),
                        "name": d.get("name"),
                        "ref": d.get("ref"),
                        "relation": edge_data.get("rel") if edge_data else "calls",
                        "related_symbol": G.nodes[nid].get("name"),
                        "direction": "callee",
                    })

    return {
        "query": query,
        "seed_chunks": seed_chunks,
        "connected_graph": connected_nodes[:10],
    }
