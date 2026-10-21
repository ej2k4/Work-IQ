from typing import Tuple

def compare_versions(v1: str, v2: str) -> int:
    # Convert version strings to numeric tuples
    v1_tuple = tuple(map(int, v1.split('.')))
    v2_tuple = tuple(map(int, v2.split('.')))

    # Compare numeric tuples
    if v1_tuple < v2_tuple:
        return -1
    elif v1_tuple > v2_tuple:
        return 1
    return 0
