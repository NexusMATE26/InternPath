# Working draft — DSA mini project proposal (1–2 pages when formatted)

**Title:** InternPath — An Algorithm-Based Internship Readiness and Skill Planning System

## Problem statement
Engineering students seeking internships need to identify suitable opportunities, compare their current skills against stated requirements, and understand the prerequisite order needed to close gaps. A naive implementation scans and sorts everything repeatedly and may generate invalid study plans where prerequisite knowledge is missing. InternPath solves the computational parts of the problem through a structured internship catalogue, hash-based skill and record retrieval, balanced-tree deadline indexing, sorting/searching, and a directed skill prerequisite graph.

## Objectives
1. Develop a small, testable C++20 engine integrated into a web-based student demonstration.
2. Implement core data structures ourselves (dynamic array, linked lists, stack, queue, hash table, AVL tree, graph) for appropriate operational roles.
3. Implement matching and gap-analysis logic using bounded integer scores while clearly identifying student self-reported levels versus verified evidence.
4. Detect cycles and generate valid skill preparation stages using DFS and topological sorting.
5. Compare linear/binary/AVL/hash lookups and insertion/merge/quick sorting using reproducible tests and benchmarks.
6. Explain the choice and theoretical complexity of each data structure or algorithm with instrumented traces and validation tests.

## Proposed system summary
The web client displays internship requirements and students' skills. A Python API delegates algorithmic operations to the custom C++20 engine. The engine calculates relative requirement coverage, prioritizes gaps, and produces prerequisite-valid learning stages. A separate DSA Lab exposes algorithm traces, performance data and invariants without interrupting the student experience.

## DSA alignment
- Arrays: dense skill values and ranking buffers.
- Linked lists: hash collision chains and mutable task/history records.
- Stacks: undo pending edits and graph cycle paths.
- Queues: BFS/topological progression and ordered event processing.
- Hash tables: exact identifiers and duplicate detection.
- AVL tree: dynamic deadline-order index and range queries.
- Graphs: prerequisite DAG with DFS, BFS and Kahn's algorithm.
- Sorting: merge, quick and insertion sorts.
- Searching: linear, binary, hashing and AVL range lookup.

**Deliverable:** Code, live demo, algorithm report, tests, benchmarks and explanation of all DSA choices. This is the DSA framing of the same product also entered into InnovaX; verify reuse rules and acknowledge AI assistance appropriately.
