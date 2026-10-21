def compare_versions(v1: str, v2: str) -> int:
    # Numeric tuple comparison
    v1_tuple = tuple(map(int, v1.split('.')))
    v2_tuple = tuple(map(int, v2.split('.')))

    if v1_tuple < v2_tuple:
        return -1
    elif v1_tuple > v2_tuple:
        return 1
    elif v1_tuple == v2_tuple:
        return 0
    return 1