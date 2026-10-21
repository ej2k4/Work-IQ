import re

def slugify(text: str) -> str:
    # Lowercase the text
    text = text.lower()
    # Strip leading/trailing hyphens
    text = text.strip('-')
    # Replace spaces with hyphens
    text = text.replace(' ', '-')
    # Remove consecutive hyphens
    text = re.sub(r'-+', '-', text)
    # Strip special characters
    text = re.sub(r'[^a-z0-9-]', '', text)
    # Remove leading/trailing hyphens again
    text = text.strip('-')
    return text
