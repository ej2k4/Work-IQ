from mathutils import average


def test_average_basic():
    assert average([2, 4, 6]) == 4


def test_average_single():
    assert average([10]) == 10
