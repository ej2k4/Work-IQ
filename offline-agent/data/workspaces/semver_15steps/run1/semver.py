def compare_versions(v1: str, v2: str) -> int:
    # Split version strings into components
    v1_components = tuple(map(int, v1.split('.')))
    v2_components = tuple(map(int, v2.split('.')))

    # Pad the shorter version with leading zeros
    v1_components = v1_components + (0,) * (len(v2_components) - len(v1_components))
    v2_components = v2_components + (0,) * (len(v1_components) - len(v2_components))

    # Compare each component
    for i in range(len(v1_components)):
        if v1_components[i] > v2_components[i]:
            return 1
        if v1_components[i] < v2_components[i]:
            return -1

    return 0
