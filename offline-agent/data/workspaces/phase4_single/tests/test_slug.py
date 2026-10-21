import pytest
from slug_utils import slugify, unslugify

def test_slugify_basic_string():
    assert slugify('Hello, World! 123') == 'hello-world-123'

def test_slugify_punctuation():
    assert slugify('Hello, World!') == 'hello-world'

def test_slugify_multiple_spaces():
    assert slugify('Hello   World!') == 'hello-world'

def test_slugify_custom_separator():
    assert slugify('Hello, World! 123', separator='_') == 'hello_world_123'

