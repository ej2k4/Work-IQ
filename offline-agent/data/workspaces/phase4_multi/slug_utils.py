def slugify(text: str, separator: str = '-') -> str:
    cleaned = ''.join(c.lower() if c.isalnum() or c in ' _-' else '' for c in text)
    words = [w for w in cleaned.replace('_', ' ').replace('-', ' ').split() if w]
    return separator.join(words)


def unslugify(slug: str, separator: str = '-') -> str:
    words = [w.capitalize() for w in slug.split(separator) if w]
    return ' '.join(words)