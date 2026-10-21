import pytest
from temp_utils import c_to_f, f_to_c

def test_c_to_f():
    assert c_to_f(0) == 32
    assert c_to_f(100) == 212

def test_f_to_c():
    assert f_to_c(32) == 0
    assert f_to_c(212) == 100