"""
generate_edu_graph.py – Generates an interconnected educational concept graph
in Obsidian format and indexes it into the agent's SQLite concept graph.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CURRICULUM_NOTES = {
    "Curriculum_Index.md": """---
tags:
  - education/curriculum
  - education/dsa
  - moc
---

# Data Structures & Algorithms Knowledge Map

Welcome to the **Interactive DSA Knowledge Graph**. This graph maps foundational data structures, algorithmic paradigms, and their prerequisite dependencies.

```mermaid
graph TD
    Complexity["[[Time_Complexity_Big_O]]"] --> Array["[[Array]]"]
    Array --> DynamicArray["[[Dynamic_Array]]"]
    Complexity --> BinarySearch["[[Binary_Search]]"]
    Array --> BinarySearch
    Array --> LinkedList["[[Linked_List]]"]
    LinkedList --> Stack["[[Stack]]"]
    LinkedList --> Queue["[[Queue]]"]
    Complexity --> HashTable["[[Hash_Table]]"]
    Array --> BinaryTree["[[Binary_Tree]]"]
    BinaryTree --> BST["[[Binary_Search_Tree]]"]
    BinarySearch --> BST
    BinaryTree --> Traversal["[[Tree_Traversal]]"]
    Queue --> BFS["[[Breadth_First_Search]]"]
    Stack --> DFS["[[Depth_First_Search]]"]
    Traversal --> BFS
    Traversal --> DFS
    Graph["[[Graph_Fundamentals]]"] --> BFS
    Graph --> DFS
    Stack --> DP["[[Dynamic_Programming]]"]
```

## Learning Tracks

### 1. Foundations
- [[Time_Complexity_Big_O]] – Big-O, Big-$\Omega$, and Big-$\Theta$ notation.
- [[Array]] – Contiguous memory allocation, random access, and cache locality.
- [[Dynamic_Array]] – Amortized resizing and geometric growth factors.

### 2. Linear Collections
- [[Linked_List]] – Pointer-based nodes, $O(1)$ insertion, and node manipulation.
- [[Stack]] – LIFO semantics, call stacks, and monotonic stack patterns.
- [[Queue]] – FIFO semantics, buffer queues, and BFS traversal engines.

### 3. Associative & Non-Linear
- [[Hash_Table]] – Hash functions, buckets, load factor, and collision resolution.
- [[Binary_Tree]] – Hierarchical nodes, depth, height, and balanced trees.
- [[Binary_Search_Tree]] – The BST invariant ($L < N < R$) and logarithmic search.
- [[Tree_Traversal]] – Pre-order, in-order, post-order, and level-order traversals.

### 4. Graph & Algorithmic Paradigms
- [[Binary_Search]] – Divide-and-conquer on sorted ranges.
- [[Graph_Fundamentals]] – Vertices, edges, adjacency matrices vs lists.
- [[Breadth_First_Search]] – Level-order exploration using [[Queue]].
- [[Depth_First_Search]] – Deep backtracking exploration using [[Stack]] and [[Recursion]].
- [[Dynamic_Programming]] – Optimal substructure, overlapping subproblems, and memoization.
""",

    "Time_Complexity_Big_O.md": """---
topic: complexity
difficulty: beginner
tags:
  - education/dsa/theory
  - concept/math
---

# Time Complexity and Big-O

**Big-O Notation** characterizes the asymptotic upper bound of an algorithm's runtime or memory consumption as the input size $n$ approaches infinity.

## Formal Definition
$f(n) = O(g(n))$ if and only if there exist positive constants $c$ and $n_0$ such that:
$$0 \le f(n) \le c \cdot g(n) \quad \text{for all } n \ge n_0$$

## Common Complexity Classes
- **$O(1)$ Constant Time**: Hash table lookup ([[Hash_Table]]), array indexing ([[Array]]).
- **$O(\log n)$ Logarithmic Time**: Binary search ([[Binary_Search]]), balanced BST operations ([[Binary_Search_Tree]]).
- **$O(n)$ Linear Time**: Linear scan, linked list traversal ([[Linked_List]]).
- **$O(n \log n)$ Linearithmic Time**: Merge Sort, QuickSort average case.
- **$O(n^2)$ Quadratic Time**: Nested loops, Bubble sort.
- **$O(2^n)$ Exponential Time**: Naive Fibonacci recursion without [[Dynamic_Programming]].

## Related Concepts
- [[Array]] – Direct memory offset yields $O(1)$ lookup.
- [[Binary_Search]] – Halving the search interval yields $O(\log n)$.
- [[Hash_Table]] – Amortized $O(1)$ average performance.
""",

    "Array.md": """---
topic: linear-structures
difficulty: beginner
tags:
  - education/dsa/linear
  - concept/memory
---

# Array

An **Array** is a collection of elements stored at contiguous memory locations. It is the fundamental building block for almost all other data structures.

## Memory Model
Because memory is contiguous, the address of element $i$ is calculated directly:
$$\text{Address}(i) = \text{Base} + i \times \text{ElementSize}$$
This arithmetic enables **$O(1)$ random access**.

## Performance
- **Access by Index:** $O(1)$
- **Search (Unsorted):** $O(n)$
- **Search (Sorted):** $O(\log n)$ via [[Binary_Search]]
- **Insertion / Deletion at End:** $O(1)$ (with [[Dynamic_Array]])
- **Insertion / Deletion at Beginning / Middle:** $O(n)$ due to element shifting.

## Python Example
```python
# Fixed-size concept using list
arr = [10, 20, 30, 40, 50]
print(arr[2])  # O(1) -> 30
```

## Dependent Structures
- [[Dynamic_Array]] – Resizable array wrapper.
- [[Hash_Table]] – Uses an array of buckets internally.
- [[Binary_Search]] – Operates directly on sorted contiguous arrays.
""",

    "Dynamic_Array.md": """---
topic: linear-structures
difficulty: beginner
tags:
  - education/dsa/linear
  - concept/amortized
---

# Dynamic Array

A **Dynamic Array** (e.g., Python's `list`, C++ `std::vector`, Java `ArrayList`) is an [[Array]] that automatically resizes when capacity is exhausted.

## Geometric Resizing & Amortized Analysis
When the underlying array fills up:
1. Allocate a new array of double capacity ($2 \times \text{capacity}$).
2. Copy existing $n$ elements to the new block ($O(n)$ cost).
3. Deallocate the old array.

Although resizing costs $O(n)$, doubling ensures $n$ insertions happen before the next resize.  
$$\text{Amortized Cost per Append} = \frac{O(n)}{n} = O(1)$$

## Related Concepts
- [[Array]] – The underlying primitive structure.
- [[Time_Complexity_Big_O]] – Demonstrates the difference between worst-case ($O(n)$) and amortized ($O(1)$) time.
""",

    "Linked_List.md": """---
topic: linear-structures
difficulty: beginner
tags:
  - education/dsa/linear
  - concept/pointers
---

# Linked List

A **Linked List** is a linear collection of data elements whose order is not given by their physical placement in memory. Instead, each element contains a pointer (or reference) to the next node.

## Node Structure
```python
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
```

## Trade-offs vs Array
| Feature | [[Array]] | Linked List |
| :--- | :--- | :--- |
| **Random Access** | $O(1)$ | $O(n)$ |
| **Insert at Head** | $O(n)$ | $O(1)$ |
| **Cache Locality** | Excellent | Poor (pointer chasing) |

## Related Concepts
- [[Stack]] – Frequently implemented via singly linked lists.
- [[Queue]] – Implemented efficiently with head and tail pointers.
""",

    "Stack.md": """---
topic: linear-structures
difficulty: beginner
tags:
  - education/dsa/linear
  - concept/lifo
---

# Stack

A **Stack** is an abstract data type that serves as a collection of elements with two principal operations:
- **`push(val)`**: Adds an element to the top of the collection.
- **`pop()`**: Removes the most recently added element (**LIFO** — Last In, First Out).

## Common Uses
1. **Call Stack**: Function invocation and [[Recursion]] tracking.
2. **Expression Evaluation**: Dijkstra's Two-Stack algorithm, reverse polish notation.
3. **Graph Traversal**: Underpins [[Depth_First_Search]].

## Related Concepts
- [[Linked_List]] – Natural backing store with $O(1)$ push/pop at head.
- [[Depth_First_Search]] – Iterative DFS explicitly manages a Stack.
- [[Queue]] – The dual FIFO counterpart.
""",

    "Queue.md": """---
topic: linear-structures
difficulty: beginner
tags:
  - education/dsa/linear
  - concept/fifo
---

# Queue

A **Queue** is a collection that maintains elements in **FIFO** (First In, First Out) order:
- **`enqueue(val)`**: Inserts element at the rear.
- **`dequeue()`**: Removes element from the front.

## Key Applications
- Breadth-first level exploration in [[Breadth_First_Search]].
- Asynchronous task scheduling and IO buffers.

## Related Concepts
- [[Linked_List]] – Efficient implementation with head/tail pointers.
- [[Stack]] – Dual LIFO structure.
- [[Breadth_First_Search]] – Essential driver for shortest-path graph search.
""",

    "Binary_Search.md": """---
topic: search-algorithms
difficulty: intermediate
tags:
  - education/dsa/algorithms
  - concept/divide-conquer
---

# Binary Search

**Binary Search** is an efficient divide-and-conquer algorithm that finds the position of a target value within a sorted [[Array]].

## Invariant and Algorithm
At each step, compare target to the middle element:
- If target matches middle: return index.
- If target is less: search left half ($high = mid - 1$).
- If target is greater: search right half ($low = mid + 1$).

## Time Complexity
At each iteration, search space is cut in half:
$$n \to \frac{n}{2} \to \frac{n}{4} \to \dots \to 1 \implies O(\log n)$$

## Related Concepts
- [[Time_Complexity_Big_O]] – Canonical $O(\log n)$ example.
- [[Array]] – Requires random access to compute $mid = (low + high) // 2$.
- [[Binary_Search_Tree]] – Generalizes binary search to hierarchical node structures.
""",

    "Binary_Tree.md": """---
topic: trees
difficulty: intermediate
tags:
  - education/dsa/trees
  - concept/hierarchy
---

# Binary Tree

A **Binary Tree** is a non-linear hierarchical data structure where each node has at most two children, referred to as the **left child** and the **right child**.

## Node Representation
```python
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
```

## Key Properties
- Height of a balanced tree with $n$ nodes: $h = \lfloor \log_2 n \rfloor$.
- Maximum nodes at depth $d$: $2^d$.

## Related Concepts
- [[Tree_Traversal]] – Techniques to systematically visit every node.
- [[Binary_Search_Tree]] – Constrains children with an ordering property.
""",

    "Binary_Search_Tree.md": """---
topic: trees
difficulty: intermediate
tags:
  - education/dsa/trees
  - concept/search
---

# Binary Search Tree (BST)

A **Binary Search Tree** is a [[Binary_Tree]] that satisfies the **BST Invariant**:
- Every node in the **left subtree** has a key **strictly less** than the node's key.
- Every node in the **right subtree** has a key **strictly greater** than the node's key.

$$\text{All}(L) < \text{Root} < \text{All}(R)$$

## Operations
- **Search:** $O(h)$ where $h$ is tree height.
- **Insert:** $O(h)$.
- **Delete:** $O(h)$ using in-order successor.

In a balanced tree, $h = O(\log n)$. In a degenerate tree (e.g. sorted input), $h = O(n)$.

## Related Concepts
- [[Binary_Tree]] – The structural foundation.
- [[Binary_Search]] – Employs the identical decision logic on pointers rather than array indices.
- [[Tree_Traversal]] – An in-order traversal of a BST produces sorted output.
""",

    "Tree_Traversal.md": """---
topic: trees
difficulty: intermediate
tags:
  - education/dsa/trees
  - education/dsa/algorithms
---

# Tree Traversal

**Tree Traversal** is the process of visiting every node in a [[Binary_Tree]] exactly once.

## 1. Depth-First Traversals (via [[Stack]] or [[Depth_First_Search]])
- **Pre-Order (Node, Left, Right)**: Useful for copying or serializing trees.
- **In-Order (Left, Node, Right)**: Produces ascending order in a [[Binary_Search_Tree]].
- **Post-Order (Left, Right, Node)**: Useful for bottom-up cleanup or subtree evaluation.

## 2. Breadth-First Traversal (via [[Queue]] or [[Breadth_First_Search]])
- **Level-Order**: Visits nodes level by level from top to bottom.

## Related Concepts
- [[Binary_Tree]] – The structure being traversed.
- [[Breadth_First_Search]] – Equivalent to Level-Order traversal.
- [[Depth_First_Search]] – Paradigm powering pre/in/post order.
""",

    "Hash_Table.md": """---
topic: associative
difficulty: intermediate
tags:
  - education/dsa/hashing
  - concept/fast-lookup
---

# Hash Table

A **Hash Table** (hash map) maps keys to values for highly efficient associative lookups.

## Mechanics
1. Pass key $K$ into a hash function: $h = \text{hash}(K)$.
2. Map hash value into an array bucket index: $index = h \pmod{\text{bucket\_count}}$.
3. Store $(K, V)$ pair in bucket.

## Collision Resolution
- **Separate Chaining:** Each bucket contains a [[Linked_List]] of entries.
- **Open Addressing:** Linear probing or double hashing within the main [[Array]].

## Performance
- **Average Case:** $O(1)$ search, insert, delete.
- **Worst Case:** $O(n)$ if all keys collide into one bucket.

## Related Concepts
- [[Time_Complexity_Big_O]] – Showcases amortized expected $O(1)$.
- [[Array]] – The internal backing storage.
- [[Linked_List]] – Used in separate chaining.
""",

    "Graph_Fundamentals.md": """---
topic: graphs
difficulty: intermediate
tags:
  - education/dsa/graphs
  - concept/networks
---

# Graph Fundamentals

A **Graph** $G = (V, E)$ consists of a set of **vertices (nodes)** $V$ and a set of **edges** $E$ connecting pairs of vertices.

## Representations
1. **Adjacency Matrix:** $V \times V$ matrix with 1s and 0s. $O(1)$ edge lookup, $O(V^2)$ memory.
2. **Adjacency List:** Array/dictionary mapping each vertex to its list of neighbors. $O(V + E)$ memory.

## Traversal Engines
- [[Breadth_First_Search]] – Finds the shortest path in unweighted graphs.
- [[Depth_First_Search]] – Explores full branches, detects cycles, topological sort.

## Related Concepts
- [[Breadth_First_Search]] – Explores level-by-level using a [[Queue]].
- [[Depth_First_Search]] – Explores depth-first using a [[Stack]].
""",

    "Breadth_First_Search.md": """---
topic: graph-algorithms
difficulty: intermediate
tags:
  - education/dsa/algorithms
  - concept/shortest-path
---

# Breadth-First Search (BFS)

**Breadth-First Search** explores a graph or tree level by level, visiting all immediate neighbors before moving to the next distance tier.

## Mechanism
Driven by a FIFO [[Queue]]:
1. Enqueue starting node, mark visited.
2. While queue is not empty:
   - Dequeue node $u$.
   - For each unvisited neighbor $v$ of $u$: mark visited and enqueue $v$.

## Property
**Guaranteed to find the shortest path** in terms of edge count in an unweighted graph.

## Complexity
- Time: $O(V + E)$
- Space: $O(V)$

## Related Concepts
- [[Queue]] – The core data structure driving BFS.
- [[Graph_Fundamentals]] – The network topology explored.
- [[Depth_First_Search]] – The complementary deep-first exploration.
""",

    "Depth_First_Search.md": """---
topic: graph-algorithms
difficulty: intermediate
tags:
  - education/dsa/algorithms
  - concept/backtracking
---

# Depth-First Search (DFS)

**Depth-First Search** explores as far as possible along each branch before backtracking.

## Mechanism
Driven by a LIFO [[Stack]] (either explicitly or via function call recursion):
1. Visit node $u$, mark visited.
2. For each unvisited neighbor $v$: recursively call DFS on $v$.

## Applications
- Cycle detection in directed and undirected graphs.
- Topological sorting (dependency resolution).
- Solving mazes and pathfinding puzzles.

## Related Concepts
- [[Stack]] – Powers iterative DFS.
- [[Tree_Traversal]] – Pre-order, in-order, and post-order are instances of DFS.
- [[Breadth_First_Search]] – The complementary level-wise search.
""",

    "Dynamic_Programming.md": """---
topic: algorithmic-paradigms
difficulty: advanced
tags:
  - education/dsa/advanced
  - concept/optimization
---

# Dynamic Programming (DP)

**Dynamic Programming** is an algorithmic optimization technique that solves complex problems by breaking them down into simpler, overlapping subproblems.

## Two Core Prerequisites
1. **Optimal Substructure:** The optimal solution to the problem contains optimal solutions to its subproblems.
2. **Overlapping Subproblems:** The same subproblems are solved multiple times.

## Approaches
- **Top-Down with Memoization:** Recursive exploration using a [[Hash_Table]] or cache to store computed results.
- **Bottom-Up with Tabulation:** Iterative table-filling using an [[Array]].

## Classic Examples
- Fibonacci sequence: reduces naive $O(2^n)$ down to $O(n)$ time.
- Longest Common Subsequence (LCS).
- 0/1 Knapsack problem.

## Related Concepts
- [[Time_Complexity_Big_O]] – Demonstrates exponential to polynomial speedups.
- [[Hash_Table]] – Essential for memoization tables.
- [[Array]] – The foundation of bottom-up tabulation tables.
"""
}


def build_and_index_educational_graph(vault_path: Path | str, db_path: Path | str | None = None) -> dict:
    """Generate notes in vault and index them into SQLite."""
    vroot = Path(vault_path).resolve()
    edu_dir = vroot / "Education" / "Data_Structures"
    edu_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating educational notes in: {edu_dir}")
    created = []
    for filename, content in CURRICULUM_NOTES.items():
        fpath = edu_dir / filename
        fpath.write_text(content.strip(), encoding="utf-8")
        created.append(fpath.name)
        print(f"  + Created: {filename}")

    # Index into DB if db_path provided
    stats = {}
    if db_path:
        from memory.db import DB
        from memory.obsidian import index_vault
        db = DB(str(db_path))
        print("\nIndexing vault into vector embeddings & concept graph...")
        stats = index_vault(vroot, db=db, verbose=True)

    return {"notes_created": len(created), "vault_dir": str(edu_dir), "stats": stats}


if __name__ == "__main__":
    vault = os.environ.get("OBSIDIAN_VAULT", r"C:\Users\admin\Documents\ObsidianVault")
    db_file = Path(__file__).resolve().parent.parent / "data" / "memory.db"
    res = build_and_index_educational_graph(vault, db_file)
    print(f"\nDone! Created {res['notes_created']} connected educational notes in {res['vault_dir']}")
