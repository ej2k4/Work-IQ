import pytest
from stack import Stack


def test_peek_returns_top():
    s = Stack()
    s.push(1)
    s.push(2)
    assert s.peek() == 2


def test_pop_order():
    s = Stack()
    s.push(1)
    s.push(2)
    assert s.pop() == 2
    assert s.pop() == 1


def test_pop_empty_raises():
    with pytest.raises(IndexError):
        Stack().pop()
