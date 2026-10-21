def compare_versions(v1: str, v2: str) -> int:
    # Convert version strings to numeric tuples
    v1_tuple = tuple(map(int, v1.split('.')))
    v2_tuple = tuple(map(int, v2.split('.')))

    # Determine the length of the longer tuple
    max_len = max(len(v1_tuple), len(v2_tuple))

    # Compare numeric tuples up to the length of the longer tuple
    for i in range(max_len):
        if i < len(v1_tuple) and i < len(v2_tuple):
            if v1_tuple[i] < v2_tuple[i]:
                return -1
            elif v1_tuple[i] > v2_tuple[i]:
                return 1
        elif i < len(v1_tuple):
            return -1
        elif i < len(v2_tuple):
            return 1

    # If both tuples are equal up to the length of the longer tuple, compare lengths
    if len(v1_tuple) != len(v2_tuple):
        return -1 if len(v1_tuple) < len(v2_tuple) else 1

    return 0
