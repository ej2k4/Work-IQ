from slugify import slugify

def test_basic_slugify():
    assert slugify("Hello World") == "hello-world"

def test_special_characters_stripped():
    assert slugify("Python 3.10 & Cool!") == "python-310-cool"

def test_consecutive_spaces_and_hyphens():
    assert slugify("  too   many---spaces  ") == "too-many-spaces"

def test_empty_or_whitespace():
    assert slugify("   ") == ""
