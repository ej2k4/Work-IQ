from listutils import chunk


def test_chunk_keeps_remainder():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_exact():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
