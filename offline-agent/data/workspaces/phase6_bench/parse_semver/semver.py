def compare_versions(v1: str, v2: str) -> int:
    # Convert version strings to tuples of integers
    v1_tuple = tuple(map(int, v1.split('.')))
    v2_tuple = tuple(map(int, v2.split('.')))

    # Pad the shorter tuple with zeros
    if len(v1_tuple) < len(v2_tuple):
        v1_tuple += (0,) * (len(v2_tuple) - len(v1_tuple))
    elif len(v2_tuple) < len(v1_tuple):
        v2_tuple += (0,) * (len(v1_tuple) - len(v2_tuple))

    # Compare the tuples
    for i in range(max(len(v1_tuple), len(v2_tuple))):
        if v1_tuple[i] < v2_tuple[i]:
            return -1
        elif v1_tuple[i] > v2_tuple[i]:
            return 1
    return 0
