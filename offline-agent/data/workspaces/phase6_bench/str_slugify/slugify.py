import re

def slugify(text: str) -> str:
    # Fix: lower-case, strip leading/trailing hyphens, collapse poorly, handle special characters, remove consecutive hyphens
    s = text.replace(' ', '-').strip('-').lower()
    s = re.sub(r'[^a-z0-9-]', '', s)
    s = re.sub(r'-+', '-', s)
    return s
