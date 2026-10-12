# Graph Report - Link ECU Tunning software remade  (2026-10-13)

## Corpus Check
- 5 files · ~6,018 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 133 nodes · 265 edges · 13 communities (4 shown, 9 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e2d14fe8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- pclink.py
- Module Imports
- Reading Settings
- Tune
- Safe Saving
- encode
- _definitions
- .save

## God Nodes (most connected - your core abstractions)
1. `App` - 36 edges
2. `Tune` - 19 edges
3. `TableView` - 19 edges
4. `main()` - 13 edges
5. `_definitions()` - 10 edges
6. `encode()` - 8 edges
7. `Panel` - 8 edges
8. `_keys()` - 7 edges
9. `decode()` - 7 edges
10. `ValueList` - 7 edges

## Surprising Connections (you probably didn't know these)
- `What is here` --references--> `Tune`  [INFERRED]
  README.md → pclink.py
- `App` --uses--> `Tune`  [INFERRED]
  pclink_gui.py → pclink.py

## Import Cycles
- None detected.

## Communities (13 total, 9 thin omitted)

### Community 1 - "Module Imports"
Cohesion: 0.12
Nodes (4): fmt(), heat(), Panel, ValueList

### Community 3 - "Tune"
Cohesion: 0.12
Nodes (7): Link ECU tune tooling, Tune, File format, Not supported, Open Source Link G5, Use, What is here

### Community 7 - "encode"
Cohesion: 0.31
Nodes (4): decode(), encode(), _keys(), _mx()

### Community 10 - "_definitions"
Cohesion: 0.25
Nodes (4): _definitions(), props(), load_defs(), load_strings()

## Knowledge Gaps
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Tune` connect `Tune` to `pclink.py`, `Module Imports`, `Self Test`, `File Decoding`, `Safe Saving`, `.save`?**
  _High betweenness centrality (0.392) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Tune` (e.g. with `App` and `What is here`) actually correct?**
  _`Tune` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Module Imports` be split into smaller, more focused modules?**
  _Cohesion score 0.11904761904761904 - nodes in this community are weakly interconnected._
- **Why does `App` connect `Safe Saving` to `Module Imports`, `Tune`, `Self Test`, `File Decoding`, `Table Editing`, `Scalar Editing`?**
  _High betweenness centrality (0.380) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `main()` (e.g. with `.find()` and `.get()`) actually correct?**
  _`main()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Should `Tune` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Why does `TableView` connect `Reading Settings` to `Module Imports`, `Safe Saving`?**
  _High betweenness centrality (0.213) - this node is a cross-community bridge._