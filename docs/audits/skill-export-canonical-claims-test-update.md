# Skill Export Canonical Claims Test Update

## Outcome

The Skill export integration test now matches the production trust boundary:

- A freshly built, canonical index still proves relationship-endpoint, test-evidence,
  file/symbol/module, tutorial, codemap, and coverage closure during export.
- A re-signed index containing schema-external `feature` or `project` fields is
  explicitly expected to fail closed with `canonical-source-claims-mismatch`.
- The separate legal-source-path test continues to prove that untrusted Markdown
  and HTML characters are escaped in the generated reference guide.

No validator or Skill export implementation was relaxed.

## Verification

- Targeted integration test: **1 passed**.
- Complete `tests.test_skill_export` suite: **46 passed**.
- `uv run --offline ruff check tests/test_skill_export.py`: **passed**.

