import os
from pathlib import Path

def atomic_write(filepath: str | Path, content: str) -> None:
    p = Path(filepath)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f'Error writing to {filepath}: {e}')
