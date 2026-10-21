from bsearch import binary_search

def test_empty_list():
    assert binary_search([], 5) == -1

def test_single_element_found():
    assert binary_search([42], 42) == 0

def test_single_element_not_found():
    assert binary_search([42], 10) == -1

def test_target_at_ends():
    arr = [1, 3, 5, 7, 9]
    assert binary_search(arr, 1) == 0
    assert binary_search(arr, 9) == 4

def test_target_missing_in_range():
    arr = [2, 4, 6, 8, 10]
    assert binary_search(arr, 5) == -1
