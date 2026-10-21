from typing import List

def chunk(lst: List[int], size: int, overlap: int = 0) -> List[List[int]]:
    result = []
    for i in range(0, len(lst), size):
        chunk = lst[i:i + size]
        if overlap > 0 and i + size < len(lst):
            chunk += lst[i + size:i + size + overlap]
        result.append(chunk)
    return result
