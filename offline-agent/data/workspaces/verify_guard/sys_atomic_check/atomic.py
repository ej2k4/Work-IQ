import os
from pathlib import Path

def atomic_write(filepath: str | Path, content: str) -> None:
    p = Path(filepath)
    # Create parent directories if they don't exist
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file first
    temp_path = p.parent / (p.name + '.tmp')
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    # Replace the original file with the temp file
    os.replace(temp_path, p)