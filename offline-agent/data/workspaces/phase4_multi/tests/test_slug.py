import pytest
from slug_utils import slugify, unslugify


def test_slugify():
    assert slugify('hello world') == 'hello-world'
    assert slugify('hello, world!') == 'hello-world'
    assert slugify('foo   bar') == 'foo-bar'
    assert slugify('hello world', separator='_') == 'hello_world'


def test_unslugify():
    assert unslugify('hello-world') == 'Hello World'
    assert unslugify('hello_world', separator='_') == 'Hello World'
