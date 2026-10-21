"""
benchmark_suite.py – Benchmark tasks across categories for Phase 6 evaluation.

Categories:
1. Algorithms (binary search edge cases)
2. String Parsing (slugify & unicode normalization)
3. Data Structures (LRU Cache eviction)
4. Versioning & SemVer (semantic version comparison)
5. Systems & Reliability (atomic file write with rollback)
6. Multi-file Specification (Module, Pytest Suite, Documentation)
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_PY = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV_PY.exists():
    _VENV_PY = _PROJECT_ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV_PY) if _VENV_PY.exists() else sys.executable


BENCHMARK_TASKS = [
    {
        "id": "algo_bsearch",
        "category": "Algorithms",
        "name": "Binary Search Edge Cases",
        "prompt": "Fix binary_search in bsearch.py so all tests in test_bsearch.py pass. Do not edit test_bsearch.py.",
        "files": {
            "bsearch.py": """def binary_search(arr, target):
    low = 0
    high = len(arr)  # Bug: should be len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid  # Bug: should be mid - 1
    return -1
""",
            "test_bsearch.py": """from bsearch import binary_search

def test_empty_list():
    assert binary_search([], 5) == -1

def test_single_element_found():
    assert binary_search([42], 42) == 0

def test_single_element_not_found():
    assert binary_search([42], 10) == -1

def test_target_at_ends():
    arr = [1, 3, 5, 7, 9]
    assert binary_search(arr, 1) == 0
    assert binary_search(arr, 9) == 4

def test_target_missing_in_range():
    arr = [2, 4, 6, 8, 10]
    assert binary_search(arr, 5) == -1
""",
        },
        "target_test": "test_bsearch.py",
        "source_file": "bsearch.py",
    },
    {
        "id": "str_slugify",
        "category": "String Parsing",
        "name": "URL Slug Generator",
        "prompt": "Fix slugify in slugify.py so all tests in test_slugify.py pass. Do not edit test_slugify.py.",
        "files": {
            "slugify.py": """import re

def slugify(text: str) -> str:
    # Bug: doesn't lower-case, doesn't strip leading/trailing hyphens, collapses poorly
    s = text.replace(" ", "-")
    return s
""",
            "test_slugify.py": """from slugify import slugify

def test_basic_slugify():
    assert slugify("Hello World") == "hello-world"

def test_special_characters_stripped():
    assert slugify("Python 3.10 & Cool!") == "python-310-cool"

def test_consecutive_spaces_and_hyphens():
    assert slugify("  too   many---spaces  ") == "too-many-spaces"

def test_empty_or_whitespace():
    assert slugify("   ") == ""
""",
        },
        "target_test": "test_slugify.py",
        "source_file": "slugify.py",
    },
    {
        "id": "ds_lru",
        "category": "Data Structures",
        "name": "LRU Cache Eviction",
        "prompt": "Fix LRUCache in lru.py so all tests in test_lru.py pass. Do not edit test_lru.py.",
        "files": {
            "lru.py": """from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return -1
        # Bug: doesn't mark as recently used
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache[key] = value
            self.cache.move_to_end(key)
            return
        if len(self.cache) >= self.capacity:
            # Bug: pops most recent (last=True) instead of least recent (last=False)
            self.cache.popitem(last=True)
        self.cache[key] = value
""",
            "test_lru.py": """from lru import LRUCache

def test_lru_basic():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)  # evicts "b", because "a" was accessed
    assert c.get("b") == -1
    assert c.get("a") == 1
    assert c.get("c") == 3

def test_lru_update_existing():
    c = LRUCache(2)
    c.put("x", 10)
    c.put("y", 20)
    c.put("x", 15)  # update x
    c.put("z", 30)  # evicts "y"
    assert c.get("y") == -1
    assert c.get("x") == 15
    assert c.get("z") == 30
""",
        },
        "target_test": "test_lru.py",
        "source_file": "lru.py",
    },
    {
        "id": "parse_semver",
        "category": "Versioning",
        "name": "Semantic Version Comparator",
        "prompt": "Fix compare_versions in semver.py so all tests in test_semver.py pass. Do not edit test_semver.py.",
        "files": {
            "semver.py": """def compare_versions(v1: str, v2: str) -> int:
    # Bug: compares as strings ("1.10.0" < "1.2.0") instead of numeric tuple components
    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    return 0
""",
            "test_semver.py": """from semver import compare_versions

def test_equal_versions():
    assert compare_versions("1.2.3", "1.2.3") == 0

def test_minor_double_digits():
    # String comparison fails here because '1' < '2'
    assert compare_versions("1.10.0", "1.2.0") == 1
    assert compare_versions("1.2.0", "1.10.0") == -1

def test_major_and_patch():
    assert compare_versions("2.0.0", "1.9.9") == 1
    assert compare_versions("0.1.1", "0.1.2") == -1

def test_different_component_lengths():
    assert compare_versions("1.0", "1.0.0") == 0
    assert compare_versions("1.2", "1.2.1") == -1
""",
        },
        "target_test": "test_semver.py",
        "source_file": "semver.py",
    },
    {
        "id": "sys_atomic",
        "category": "Systems & Reliability",
        "name": "Atomic File Write",
        "prompt": "Fix atomic_write in atomic.py so all tests in test_atomic.py pass. Do not edit test_atomic.py.",
        "files": {
            "atomic.py": """import os
from pathlib import Path

def atomic_write(filepath: str | Path, content: str) -> None:
    p = Path(filepath)
    # Bug: directly overwrites without writing to temp file and replacing
    # If writing fails halfway or directory doesn't exist, file is corrupted or crashes
    p.write_text(content, encoding="utf-8")
""",
            "test_atomic.py": """import pytest
from pathlib import Path
from atomic import atomic_write

def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "test.txt"
    atomic_write(target, "hello atomic")
    assert target.read_text(encoding="utf-8") == "hello atomic"

def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "sub" / "output.txt"
    atomic_write(target, "deep content")
    assert target.read_text(encoding="utf-8") == "deep content"

def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("initial", encoding="utf-8")
    atomic_write(target, "updated")
    assert target.read_text(encoding="utf-8") == "updated"
""",
        },
        "target_test": "test_atomic.py",
        "source_file": "atomic.py",
    },
]


def setup_benchmark_task(task_def: dict, workspace: Path | str) -> dict:
    """Populate workspace with task files and record original test content for anti-cheating."""
    ws = Path(workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    orig_tests = {}
    for filename, content in task_def["files"].items():
        p = ws / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if filename.startswith("test_") or "/test_" in filename:
            orig_tests[filename] = content
    return orig_tests


def grade_benchmark_task(task_def: dict, workspace: Path | str, orig_tests: dict) -> dict:
    """
    Independent grading harness:
    1. Anti-cheating: verify test files were not modified.
    2. Run pytest with isolated interpreter.
    3. Verify target source file exists and is non-empty.
    """
    ws = Path(workspace).resolve()

    # 1. Anti-cheating check
    for test_file, orig_content in orig_tests.items():
        current_p = ws / test_file
        if not current_p.exists():
            return {"passed": False, "score": 0.0, "reason": f"Test file {test_file} was deleted"}
        if current_p.read_text(encoding="utf-8") != orig_content:
            return {"passed": False, "score": 0.0, "reason": f"Anti-cheating violation: {test_file} was modified"}

    # 2. Source file check
    src_file = task_def.get("source_file")
    if src_file:
        src_p = ws / src_file
        if not src_p.exists() or src_p.stat().st_size == 0:
            return {"passed": False, "score": 0.0, "reason": f"Source file {src_file} missing or empty"}

    # 3. Pytest check
    target_test = task_def.get("target_test", "")
    cmd = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if target_test:
        cmd.append(str(ws / target_test))
    else:
        cmd.append(str(ws))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ws) + os.pathsep + env.get("PYTHONPATH", "")

    try:
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=30, env=env)
        passed = (r.returncode == 0)
        output = (r.stdout + "\n" + r.stderr).strip()
        return {
            "passed": passed,
            "score": 100.0 if passed else 0.0,
            "output": output,
            "reason": "All pytest assertions passed" if passed else "Pytest failed",
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "score": 0.0, "reason": "Pytest timed out after 30s"}
    except Exception as e:
        return {"passed": False, "score": 0.0, "reason": f"Execution error: {e}"}
