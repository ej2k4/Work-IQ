from typing import Tuple

def compare_versions(v1: str, v2: str) -> int:
    # Convert version strings to numeric tuples
    v1_tuple = tuple(map(int, v1.split('.')))
    if len(v1_tuple) < 3:
        v1_tuple += (0,) * (3 - len(v1_tuple))

    v2_tuple = tuple(map(int, v2.split('.')))
    if len(v2_tuple) < 3:
        v2_tuple += (0,) * (3 - len(v2_tuple))

    if v1_tuple < v2_tuple:
        return -1
    elif v1_tuple > v2_tuple:
        return 1
    return 0
