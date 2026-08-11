# Skill Export Fix Round 3

Status: **fix candidate complete; independent re-audit required**

This round addresses the remaining ownership, crash-recovery, freshness, and
subgraph-closure findings from the second Skill export audit.  It is not an
approval report and must not be used to mark the module production-complete.

## Safety properties implemented

### Private, identity-bound transactions

- Staging and backup entries no longer live as arbitrary siblings of the public
  Skill destination.  They live below a destination-specific `0700` private
  state directory.
- A transaction is accepted only when its strict journal schema, random
  transaction ID, target name, private transaction directory, ownership marker,
  generation ID, Skill marker SHA-256, and whole-tree SHA-256 agree.
- Recovery never quarantines or deletes the public target.  It restores an
  exact digest-bound backup only while the target entry is absent.  Unknown or
  inconsistent states are preserved and fail closed.
- Publish and rollback use no-follow directory-entry identities and held parent
  directory descriptors.  If the target is replaced after its ownership check,
  the rename is rejected and the replacement is preserved.
- A forged journal cannot escape the private transaction parent or select an
  unmarked directory for cleanup.

### Source identity and freshness

- Export now requires the complete project identity emitted by the current
  index schema.
- `is_git` must be a boolean and must equal the source repository's live Git
  identity.
- Git exports require matching non-empty commit and resolved Git root; deleting
  or rewriting those fields cannot downgrade a Git repository to non-Git
  freshness checks.
- Non-Git exports still require a complete source re-scan with identical file
  membership and content hashes.
- The core schema, analysis fingerprint, integrity checksum, complete scan, and
  source validation gates remain mandatory; this patch does not bypass them.

### Export payload closure

- Project identity fields are mandatory in the exported payload.
- Path-shaped `feature.entrypoint` values must resolve to an included file.
- `file.symbols` is now checked in both directions: every declared symbol must
  belong to the file and every included symbol must appear in its defining
  file's membership list.
- `module.entrypoints` remains closed to included files and the matching module.
- Selected source-path entrypoints are pulled into the transitive export
  closure.
- Skill markers now bind a random generation ID and the exported JSON payload
  digest in addition to the required-file manifest.

## Adversarial regression coverage

The round-three tests cover:

- forged recovery journal pointing at an unowned transaction directory;
- journal path traversal toward a user-owned sibling directory;
- target replacement after ownership inspection but before rename;
- deleted `is_git` or `commit` identity fields;
- rewritten Git identity attempting to downgrade to non-Git;
- path-shaped dangling feature entrypoint;
- missing reverse `file.symbols` membership;
- crash between backup and publication using the new private transaction shape;
- stale, dirty, incomplete, symlinked, tampered, and non-owned destinations;
- a fresh full export of the pinned Understand Anything reference repository.

## Verification evidence

- Focused Skill, persistence, and CLI suite: PASS, 37 tests.
- Full Ruff check on `src` and `tests`: PASS.
- `compileall` on `src` and `tests`: PASS.
- Understand Anything cold index validation: PASS, 0 errors and 0 warnings.
- Understand Anything full Skill export: PASS, 3 source-audited features,
  3 files, 5 evidence records, and 0 dangling references.
- Understand Anything internal Skill validator: PASS.
- Official Codex `quick_validate.py`: PASS (`Skill is valid!`).
- Full repository suite: PASS, 157 tests in 71.692 seconds.

## Remaining gate

An independent audit Agent must review this candidate.  Any request-changes
verdict reopens the module; this document does not self-certify completion.
