from lru import LRUCache

def test_lru_basic():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)  # evicts "b", because "a" was accessed
    assert c.get("b") == -1
    assert c.get("a") == 1
    assert c.get("c") == 3

def test_lru_update_existing():
    c = LRUCache(2)
    c.put("x", 10)
    c.put("y", 20)
    c.put("x", 15)  # update x
    c.put("z", 30)  # evicts "y"
    assert c.get("y") == -1
    assert c.get("x") == 15
    assert c.get("z") == 30
