# Production refactor plan

The current behavior is protected before moving orchestration. The goal is to
make `repo_teacher.cli` an argument parser and dependency-composition surface,
while the application command layer owns long-running stages and publication.

## Locked behavior

- `inventory` uses one CodeGraph-first global model pass and stops at the
  business-capability approval artifact.
- `report` requires an approved inventory by default; `--auto-inventory` is an
  explicit exploratory override.
- both long-running commands operate on a consistent repository snapshot.
- published project paths point to the original repository, never the
  temporary snapshot.
- the immutable current-generation publisher remains the only publication
  boundary.
- human and canonical-index renderers select their schema variant explicitly.

## Move order

1. Move command orchestration to `repo_teacher.commands.inventory` and
   `repo_teacher.commands.report` without changing synthesis algorithms.
2. Keep compatibility wrappers in `cli.py` so external tests and integrations
   do not break in one release.
3. Move remaining private synthesis helpers in later small slices; do not mix
   that mechanical move with capability semantics.
4. Verify unit, integration, cache reuse, source drift, atomic publication and
   one real Coze inventory run.

## Deliberately rejected

- Rewriting the synthesis implementation during the package move: it would
  combine behavior change with architecture change and make regressions hard
  to isolate.
- Making `report` silently discover and approve its own capability list: it
  removes the human decision gate that is the product's primary quality
  control.
