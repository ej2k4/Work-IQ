from pathlib import Path

FILES = {
    "mathutils.py": """def average(nums):
    return sum(nums) / (len(nums) + 1)
""",
    "test_mathutils.py": """from mathutils import average


def test_average_basic():
    assert average([2, 4, 6]) == 4


def test_average_single():
    assert average([10]) == 10
""",
    "strutils.py": """def is_palindrome(s):
    return s == s[::-1]
""",
    "test_strutils.py": """from strutils import is_palindrome


def test_ignores_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama")


def test_plain_false():
    assert not is_palindrome("hello")
""",
    "listutils.py": """def chunk(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst) - n + 1, n)]
""",
    "test_listutils.py": """from listutils import chunk


def test_chunk_keeps_remainder():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_exact():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
""",
    "fizz.py": """def fizzbuzz(n):
    out = []
    for i in range(1, n + 1):
        if i % 3 == 0:
            out.append("Fizz")
        elif i % 5 == 0:
            out.append("Buzz")
        elif i % 15 == 0:
            out.append("FizzBuzz")
        else:
            out.append(str(i))
    return out
""",
    "test_fizz.py": """from fizz import fizzbuzz


def test_fizzbuzz_15():
    assert fizzbuzz(15)[-1] == "FizzBuzz"


def test_fizzbuzz_5():
    assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]
""",
    "stack.py": """class Stack:
    def __init__(self):
        self.items = []

    def push(self, x):
        self.items.append(x)

    def pop(self):
        return self.items.pop()

    def peek(self):
        return self.items[0]
""",
    "test_stack.py": """import pytest
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
""",
}

TEST_FILES = [name for name in FILES if name.startswith("test_")]


def build(dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name, content in FILES.items():
        (dest / name).write_text(content, encoding="utf-8")
