import string

def is_palindrome(s):
    s = s.lower()
    s = s.translate(str.maketrans('', '', string.punctuation + ' '))
    return s == s[::-1]