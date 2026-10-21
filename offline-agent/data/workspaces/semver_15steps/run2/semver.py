def compare_versions(v1: str, v2: str) -> int:
    # Split version strings into tuples of integers
    v1_tuple = tuple(map(int, v1.split('.')))
    v2_tuple = tuple(map(int, v2.split('.')))

    # Compare tuples element by element
    for i in range(max(len(v1_tuple), len(v2_tuple))):
        if i >= len(v1_tuple):
            return 1
        if i >= len(v2_tuple):
            return -1
        if v1_tuple[i] > v2_tuple[i]:
            return 1
        if v1_tuple[i] < v2_tuple[i]:
            return -1

    # If tuples are equal, return 0
    return 0
