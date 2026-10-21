from semver import compare_versions

def test_equal_versions():
    assert compare_versions("1.2.3", "1.2.3") == 0

def test_minor_double_digits():
    # String comparison fails here because '1' < '2'
    assert compare_versions("1.10.0", "1.2.0") == 1
    assert compare_versions("1.2.0", "1.10.0") == -1

def test_major_and_patch():
    assert compare_versions("2.0.0", "1.9.9") == 1
    assert compare_versions("0.1.1", "0.1.2") == -1

def test_different_component_lengths():
    assert compare_versions("1.0", "1.0.0") == 0
    assert compare_versions("1.2", "1.2.1") == -1
