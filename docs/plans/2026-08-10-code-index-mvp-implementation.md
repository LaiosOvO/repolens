# Code Index MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Build a zero-dependency local CLI that indexes a repository into deterministic JSON and a directly-openable interactive HTML report.

**Architecture:** A Python package separates snapshot/scanning, language analyzers, index assembly, and HTML rendering. The CLI composes these pieces and a standard-library HTTP server optionally serves generated reports.

**Tech Stack:** Python 3.11+ standard library, `unittest`, HTML/CSS/vanilla JavaScript.

---

### Task 1: Package and contract

**Files:**
- Create: `pyproject.toml`
- Create: `src/repo_teacher/__init__.py`
- Create: `src/repo_teacher/models.py`
- Create: `tests/test_models.py`

**Steps:**
1. Write failing tests for stable entity IDs and JSON serialization.
2. Run `python -m unittest tests.test_models -v` and confirm failure.
3. Implement immutable-friendly dataclasses and serialization helpers.
4. Rerun the test and confirm pass.

### Task 2: Repository snapshot and scanner

**Files:**
- Create: `src/repo_teacher/snapshot.py`
- Create: `src/repo_teacher/scanner.py`
- Create: `tests/test_scanner.py`

**Steps:**
1. Write fixtures for Git metadata, ignored directories, language counts, large files and syntax-independent diagnostics.
2. Run the focused test and confirm failure.
3. Implement safe subprocess Git reads and deterministic file enumeration.
4. Rerun the focused test and confirm pass.

### Task 3: Language analyzers

**Files:**
- Create: `src/repo_teacher/analyzers/base.py`
- Create: `src/repo_teacher/analyzers/python.py`
- Create: `src/repo_teacher/analyzers/javascript.py`
- Create: `src/repo_teacher/analyzers/__init__.py`
- Create: `tests/test_analyzers.py`

**Steps:**
1. Write tests for Python definitions/imports/calls and JS/TS declarations/imports/exports.
2. Confirm the tests fail.
3. Implement Python AST analysis and conservative JS/TS extraction.
4. Confirm analyzer tests pass, including syntax-error degradation.

### Task 4: Unified index builder

**Files:**
- Create: `src/repo_teacher/indexer.py`
- Create: `tests/test_indexer.py`

**Steps:**
1. Write an end-to-end index contract test.
2. Confirm failure.
3. Assemble files, symbols, relationships, module summaries, diagnostics and reading paths.
4. Confirm deterministic ordering and repeatable JSON output.

### Task 5: Standalone HTML report

**Files:**
- Create: `src/repo_teacher/report.py`
- Create: `tests/test_report.py`

**Steps:**
1. Write tests for embedded JSON safety, sections, search controls and no external assets.
2. Confirm failure.
3. Implement an editorial summary plus searchable file/symbol/relationship views.
4. Confirm report tests pass.

### Task 6: CLI and documentation

**Files:**
- Create: `src/repo_teacher/cli.py`
- Create: `src/repo_teacher/__main__.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`

**Steps:**
1. Write a CLI end-to-end test for `index`.
2. Confirm failure.
3. Implement `index` and `serve` commands with useful error messages.
4. Document install, quick start, output and MVP limitations.
5. Confirm CLI tests pass.

### Task 7: Full verification

**Files:**
- Generate: `examples/self-index/index.json`
- Generate: `examples/self-index/index.html`

**Steps:**
1. Run `python -m unittest discover -s tests -v`.
2. Install the package in editable mode without dependencies.
3. Index `dev/repo` itself and inspect summary counts.
4. Open the HTML at desktop and mobile widths and verify no page-level overflow.
5. Run `serve`, request the page locally, and confirm HTTP 200.

