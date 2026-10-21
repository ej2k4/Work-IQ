def slugify(text: str, separator: str = "-") -> str:
    import string
    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation + string.whitespace))
    text = separator.join(text.split(separator))
    text = text.strip(separator)
    return text

def unslugify(slug: str, separator: str = "-") -> str:
    slug = slug.replace(separator, " ")
    words = slug.title()
    return words

