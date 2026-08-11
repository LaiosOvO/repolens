# Production Repo Teacher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the deterministic MVP into a production-grade local repository teaching product with incremental indexing, feature-level code paths, grounded tutorials/Codemaps, and Skill export.

**Architecture:** Keep one Python package and a versioned JSON contract. Deterministic analyzers and an evidence store form the trusted base; feature/tutorial generation consumes only that base, with an optional OpenAI-compatible local LLM enhancer that is never authoritative. Generated HTML and Skills are static artifacts, while the local HTTP server is a restricted convenience layer.

**Tech Stack:** Python 3.11+ standard library, `unittest`, HTML/CSS/vanilla JavaScript; optional external analyzers and OpenAI-compatible HTTP without required runtime dependencies.

---

### Task 1: Schema 2.0 and evidence contract

**Files:** modify `src/repo_teacher/models.py`, create `src/repo_teacher/evidence.py`, modify `tests/test_models.py`, create `tests/test_evidence.py`.

1. Add records for evidence, features, feature steps, tutorials, Codemaps, coverage and changes.
2. Write failing tests for stable IDs, path/line validation, snippet hash and JSON serialization.
3. Implement evidence extraction and grounding.
4. Run focused tests and retain schema 1 readers where safe.

### Task 2: Incremental, atomic indexing

**Files:** create `src/repo_teacher/incremental.py`, modify `indexer.py`, `cli.py`, create `tests/test_incremental.py`.

1. Test added/changed/deleted/unchanged classification.
2. Reuse previous symbols and relationships for unchanged hashes.
3. Add atomic JSON/HTML writes and exclusive output lock.
4. Report reuse counters and durations; test concurrent-lock failure.

### Task 3: Feature and component discovery

**Files:** create `src/repo_teacher/features.py`, modify analyzers and `indexer.py`, create `tests/test_features.py`.

1. Detect Python/JS CLI commands, HTTP routes, entrypoints and public APIs.
2. Resolve a bounded path through the existing relationship graph.
3. Attach test and configuration evidence without claiming dynamic behavior.
4. Provide module fallbacks when no user-facing entry exists.

### Task 4: Tutorial, Codemap and coverage critic

**Files:** create `tutorials.py`, `coverage.py`, optional `llm.py`; add focused tests.

1. Build deterministic total—detail—summary tutorials from feature paths.
2. Generate Codemap nodes, edges and citation-backed steps.
3. Score entry/test/config/error/security/persistence coverage and list gaps.
4. Add optional structured LLM refinement; reject unknown evidence IDs and fall back on timeout/schema errors.

### Task 5: Agent Skill export

**Files:** create `exporter.py`, modify `cli.py`, create `tests/test_exporter.py` and `tests/test_cli.py` cases.

1. Accept repeated `--feature` and `--module` selectors.
2. Generate concise `SKILL.md`, `agents/openai.yaml`, `references/module-index.json`, `references/code-map.md`, `scripts/verify_snapshot.py` and `manifest.json`.
3. Constrain names and paths; include only selected evidence.
4. Validate a generated fixture Skill with the installed Skill validator.

### Task 6: Summary-first report and restricted server

**Files:** rewrite `report.py`, modify `cli.py`, update `tests/test_report.py`, add server tests.

1. Put repository purpose, feature candidates, reuse verdict and coverage risks above raw metrics.
2. Add feature navigation, tutorial steps, Codemap, evidence snippets, module selection and export commands.
3. Preserve standalone file behavior, responsive layout and exact/heuristic labels.
4. Restrict HTTP paths, add CSP/security headers, disable listing, and implement `/healthz`.

### Task 7: Reference repository benchmark

**Files:** create `scripts/benchmark_references.py`, generate `examples/reference-indexes/*`, update `README.md` and `REFERENCE-PROJECTS.md`.

1. Index all six full clones from `/Volumes/T7/workspace/ontology/graph/repo`.
2. Run cold and warm passes and save counts, duration, reuse and diagnostics.
3. Inspect at least one feature tutorial per repo against source.
4. Run the full suite, compile checks, HTTP checks, desktop/mobile visual QA and Skill validation.

