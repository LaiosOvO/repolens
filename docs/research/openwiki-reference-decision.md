# OpenWiki as a Reference Project for Repo Teacher

## Verdict

OpenWiki is **worth referencing, but only selectively**.

It is a strong reference for the **infrastructure layer** of Repo Teacher:

- page-link graph visualization
- incremental update / reload behavior
- internal link and source-reference hygiene
- interactive reading experience
- multi-stage agent synthesis scaffolding

It is **not** a good primary reference for Repo Teacher’s **content model**:

- Repo Teacher needs a human-facing report that starts with essence, then runtime / state / hard parts, and only then source evidence.
- Repo Teacher also needs a capability graph that models code capabilities, feature slices, and module dependencies.
- OpenWiki’s graph is a **page-link wiki graph**, not a **code graph**.

The local clone at `/Volumes/T7/workspace/ontology/graph/repo/openwiki` matches the official `langchain-ai/openwiki` main branch on the files inspected here. The checked local HEAD was `7531d61`. I checked the local repository first, then verified the official GitHub repository.

## Target Contract in Repo Teacher

Repo Teacher’s current contract is already different from OpenWiki:

- `dev/repo/src/repo_teacher/human_report.py:17-177` defines a report schema with `chapters`, `source_refs`, `runtime_story`, `construction`, `mechanism_model`, `state_flow`, `difficulty_map`, `design_choices`, `boundary`, and `reuse_plan`.
- `dev/repo/tests/test_human_report.py:146-188` asserts that the composed human report must lead with the explanation, not with raw entrypoints, and that the narrative is organized for human reading.
- `dev/repo/src/repo_teacher/capability_graph.py:11-30` and `dev/repo/tests/test_capability_graph.py:72-180` show that the graph is about capability slices, callers/callees, and module dependencies, not a wiki page graph.

That means OpenWiki can influence the delivery mechanism, but not the report semantics.

## Adopt / Do Not Adopt Matrix

| Area | Decision | What to reuse | Why | Evidence |
| --- | --- | --- | --- | --- |
| Function tree / chapter decomposition | Do not adopt as-is | Only the deterministic index / section maintenance idea | OpenWiki organizes wiki pages and OKF indexes, but it does not model a report chapter contract like `essence -> mechanism/state/hard parts -> evidence` | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/okf/index-sync.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/okf/index-labels.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/okf-middleware.ts`; Target: `/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/human_report.py:17-177` |
| Source references | Adopt selectively | Internal-link validation, stamped broken-link repair, and source-link rendering patterns | OpenWiki is strong at keeping wiki links valid and repairable, but its citations are page/document references, not Repo Teacher’s evidence-bounded source refs | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/wiki-link-validator.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/agent/wiki-link-validator.test.ts`; Official: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/src/agent/wiki-link-validator.ts` |
| Graph | Adopt | Interactive page-link graph, sidebar, backlinks, and live reload | This is the clearest reusable pattern for Repo Teacher’s UI layer, but it is a wiki graph, not a code graph | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/server.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/page.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/graph.ts`; Official: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/src/visualize/server.ts` |
| Incremental updates | Adopt | `update` no-op short-circuit, snapshot-style change detection, file watcher reload | Repo Teacher needs cheap re-runs and stable artifacts; OpenWiki already has that operational pattern | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/okf/index-sync.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/server.ts`; Official: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/src/agent/index.ts` |
| LLM synthesis | Adopt selectively | Multi-stage agent composition, skeleton critique, translation middleware | Useful as a scaffolding pattern, but OpenWiki’s synthesis objective is wiki maintenance, not report generation with a fixed narrative contract | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/index.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/skeleton_critic.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/agent/translation-middleware.ts`; Official: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/src/agent/index.ts` |
| Front-end reading experience | Adopt | Split-pane reader, search/filter, theme toggle, backlinks, graph + markdown side-by-side | This is a strong UX reference for Repo Teacher’s HTML report reader | Local: `/Volumes/T7/workspace/ontology/graph/repo/openwiki/src/visualize/page.ts`, `/Volumes/T7/workspace/ontology/graph/repo/openwiki/test/visualize/page.test.ts`; Official: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/src/visualize/page.ts` |

## The Four Best References

If the goal is to borrow only the highest-value mechanisms, the four best OpenWiki references are:

1. **Interactive graph UI** for page relationships, not code semantics.
2. **Incremental update / no-op detection** so reruns are cheap and stable.
3. **Internal-link validation and repair** so generated docs do not rot.
4. **Split-pane reading experience** for human consumption.

I would **not** copy the OpenWiki content model directly into Repo Teacher.

## Source Evidence

### Official GitHub repository

- Repository: `https://github.com/langchain-ai/openwiki`
- README: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/README.md`
- License: `https://raw.githubusercontent.com/langchain-ai/openwiki/main/LICENSE`

### Key OpenWiki files inspected locally

- `repo/openwiki/README.md`
- `repo/openwiki/package.json`
- `repo/openwiki/src/agent/index.ts`
- `repo/openwiki/src/agent/wiki-link-validator.ts`
- `repo/openwiki/src/okf/index-sync.ts`
- `repo/openwiki/src/visualize/server.ts`
- `repo/openwiki/src/visualize/page.ts`
- `repo/openwiki/src/visualize/graph.ts`
- `repo/openwiki/test/agent/wiki-link-validator.test.ts`
- `repo/openwiki/test/visualize/page.test.ts`

### Key Repo Teacher target files

- `dev/repo/src/repo_teacher/human_report.py`
- `dev/repo/src/repo_teacher/capability_graph.py`
- `dev/repo/tests/test_human_report.py`
- `dev/repo/tests/test_capability_graph.py`

## Notes

- OpenWiki’s visualizer is explicitly for a **wiki page graph** and exposes `/api/graph` plus `/events`; it does not expose a code-call graph.
- OpenWiki’s internal-link validator validates Markdown links and heading anchors across the wiki tree, which is useful for documentation hygiene, but it does not define Repo Teacher’s report-level evidence contract.
- The official repository uses MIT license.
