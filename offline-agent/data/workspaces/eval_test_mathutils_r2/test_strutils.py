from strutils import is_palindrome


def test_ignores_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama")


def test_plain_false():
    assert not is_palindrome("hello")
