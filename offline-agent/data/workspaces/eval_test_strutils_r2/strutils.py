import string

def is_palindrome(s):
    s = s.lower()
    s = s.translate(str.maketrans('', '', string.punctuation))
    s = s.replace(' ', '')
    return s == s[::-1]