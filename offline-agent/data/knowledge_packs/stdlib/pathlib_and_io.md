# Python Pathlib and File I/O Safety Guide

## Cross-Platform Path Handling
- Always use `pathlib.Path` for path operations to remain cross-platform across Windows and POSIX:
  ```python
  from pathlib import Path
  path = Path("docs") / "README.md"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("content", encoding="utf-8")
  ```

## Path Traversal and Safety Checks
- To verify that a requested path stays inside a base workspace folder:
  ```python
  base = Path(workspace_root).resolve()
  target = (base / user_path).resolve()
  if target != base and base not in target.parents:
      raise ValueError(f"Path '{user_path}' escapes workspace jail")
  ```
- Use `.as_posix()` to normalize file paths with forward slashes for cross-platform comparison.
