# Skills and Repository Pipeline Reference

Date: 2026-08-12

Scope:
- Compare the requested skills.sh packages and official GitHub repos against primary sources.
- Keep the focus on pipeline shape, source files, output artifacts, and whether repo-teacher should adopt or reject the pattern.
- Use official URLs first; add local clone paths where this workspace already has them.

Method:
- Prefer the package/repo root README plus the smallest set of concrete source files that define the execution flow.
- Treat missing LICENSE files as unverified rather than guessing.
- If the requested package name cannot be verified exactly, say so instead of silently substituting a nearby project.

## skills.sh packages

### 1) johnlindquist/claude -> deepwiki
- Official URL: [johnlindquist/claude](https://github.com/johnlindquist/claude), skill file: [skills/deepwiki/SKILL.md](https://github.com/johnlindquist/claude/blob/main/skills/deepwiki/SKILL.md)
- Verified license: none found in the repo root file list on GitHub; treat as unverified / no LICENSE file detected.
- Pipeline source files: `skills/deepwiki/SKILL.md` defines the routing rule, DeepWiki URL rewrite, MCP setup, and fallback GitHub API flow.
- Output artifacts: DeepWiki page views, MCP tool results (`read_wiki_structure`, `read_wiki_contents`, `ask_question`), and WebFetch output. No local on-disk artifact contract is defined in the skill.
- Adopt/reject: adopt as a thin retrieval shortcut only. Reject as a repo-teacher core because it is an external doc lookup wrapper, not a grounded analysis pipeline.

### 2) inkeep/open-knowledge-skills -> codebase-wiki
- Official URL: [skills.sh package page](https://www.skills.sh/inkeep/open-knowledge-skills), [GitHub repo](https://github.com/inkeep/open-knowledge-skills)
- Verified license: MIT, shown on the GitHub repo page and in the repo license file.
- Pipeline source files: `skills/starter-packs/codebase-wiki/README.md` is the verified pack contract; the repo root also publishes `skills/` and `skills/core/` as the generated skill tree.
- Output artifacts: a source-grounded wiki of the surrounding codebase, refreshed as code changes, plus the pack's installable skill tree.
- Adopt/reject: adopt the "agent-maintained wiki that refreshes instead of rotting" idea. Reject the pack as-is if you need CodeGraph/AST-first truth, because the pack description emphasizes wiki authoring, not deterministic repository analysis.

### 3) blocklune/skills -> codebase-to-tutorial
- Official URL: [blocklune/skills](https://github.com/blocklune/skills)
- Verified license: none found in the repo page file list; treat as unverified / no LICENSE file detected.
- Pipeline source files: the verified repo page lists `skills/repo-explorer`, `skills/source-grounded-coding`, `skills/markdown-document-writing`, `skills/git-commit`, and others. I could not verify any current `codebase-to-tutorial` skill in the official repo or the skills.sh catalog from primary sources.
- Output artifacts: installable skills copied into `.claude/skills/` or `.agents/skills/` by `npx skills add BlockLune/skills`.
- Adopt/reject: reject for this comparison. The exact `codebase-to-tutorial` package name is not currently verifiable from official sources, so it should not be used as a reference for the pipeline.

### 4) lmammino/c4-codebase-architecture-skill
- Official URL: [lmammino/c4-codebase-architecture-skill](https://github.com/lmammino/c4-codebase-architecture-skill)
- Verified license: MIT.
- Pipeline source files: `README.md` plus `skills/c4-codebase-architecture/SKILL.md`, `package.json`, and `LICENSE`.
- Output artifacts: Markdown narrative plus C4 diagrams in Mermaid, PlantUML, or Structurizr DSL. The skill explicitly targets System Context, Container, and Component views.
- Adopt/reject: adopt for evidence-based architecture summaries. Reject as the primary repo-teacher pattern if you need business-capability-first reporting, because the skill is architecture-first, not capability-first.

### 5) donnfelker/donnfelker-plugin-marketplace -> codebase-analyzer
- Official URL: [donnfelker/donnfelker-plugin-marketplace](https://github.com/donnfelker/donnfelker-plugin-marketplace)
- Verified license: MIT.
- Pipeline source files: `plugins/codebase-analyzer/skills/codebase-analyzer/SKILL.md` plus `plugins/codebase-analyzer/references/` and the marketplace root `README.md`.
- Output artifacts: a markdown report written to `{TARGET_DIR}/{REPO_NAME}_COMPREHENSIVE_ANALYSIS.md`.
- Adopt/reject: adopt the explicit phase structure and output contract. Reject the repo as a direct blueprint if you need a strict evidence-closed pipeline, because it starts from broad analysis phases rather than a CodeGraph/AST-first fact base.

## official GitHub repos

### 6) AsyncFuncAI/deepwiki-open
- Official URL: [AsyncFuncAI/deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open)
- Local clone: `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open`
- Verified license: MIT, per local clone `LICENSE` and the repo notes.
- Pipeline source files: `README.md`, `api/routers/repo.py`, `api/services/wiki/tasks.py`, `api/services/wiki/structure.py`, `api/services/wiki/content.py`, `api/services/codemap.py`, `src/components/CodeMap.tsx`, `src/components/CodeViewer.tsx`.
- Output artifacts: repo index/prewarm state, wiki tasks, SSE progress streams, code map output, code viewer links, and citation-grounded wiki pages.
- Adopt/reject: strongly adopt the task registry, citation grounding, and clickable source-link pattern. Reject the browser-first interaction style if your first product goal is a dense technical report, not a conversational wiki.

### 7) OpenBMB/RepoAgent
- Official URL: [OpenBMB/RepoAgent](https://github.com/OpenBMB/RepoAgent)
- Local clone: `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/RepoAgent`
- Verified license: Apache-2.0, per the upstream LICENSE and the repo page.
- Pipeline source files: `repo_agent/main.py`, `repo_agent/runner.py`, `repo_agent/project_manager.py`, `repo_agent/file_handler.py`, `repo_agent/change_detector.py`, `repo_agent/chat_engine.py`.
- Output artifacts: `.project_doc_record/` checkpoint data, `markdown_docs/` output, per-file markdown docs, and the `chat-with-repo` interactive mode.
- Adopt/reject: adopt the incremental doc refresh and pre-commit hook idea. Reject as the core architecture for repo-teacher because it is document-generation-first, not evidence-closed or capability-first.

### 8) ahmedkhaleel2004/gitdiagram
- Official URL: [ahmedkhaleel2004/gitdiagram](https://github.com/ahmedkhaleel2004/gitdiagram)
- Local clone: `/Volumes/T7/workspace/ontology/graph/repo/references/repo-teacher-architecture/gitdiagram`
- Verified license: MIT.
- Pipeline source files: `src/features/diagram/api.ts`, `src/features/diagram/graph.ts`, `src/features/diagram/export.ts`, `src/features/diagram/sse.ts`, `src/features/diagram/github-url.ts`, `src/app/api/generate/stream/route.ts`, `src/app/api/diagram-state/route.ts`.
- Output artifacts: validated graph AST, streamed explanation, Mermaid source, PNG export, and persisted diagram state.
- Adopt/reject: adopt the strict validation + persistence model. Reject the product shape as the main repo-teacher target because it optimizes for architecture diagrams, not for stepwise technical teaching with explicit evidence packets.

### 9) yamadashy/repomix
- Official URL: [yamadashy/repomix](https://github.com/yamadashy/repomix)
- Local clone: not found in this workspace.
- Verified license: MIT.
- Pipeline source files: `src/cli/cliRun.ts`, `src/cli/cliReport.ts`, `src/core/packager.ts`, `src/core/output/*`, `src/core/skill/*`, `src/index.ts`.
- Output artifacts: `repomix-output.xml`, `repomix-output.json`, `repomix-output.md`, `repomix-output.txt`/plain output, split output files, and generated `SKILL.md` bundles.
- Adopt/reject: adopt as an evidence-packaging and token-budgeting utility. Reject as the truth layer, because it flattens code into a transport artifact and does not decide what is actually important.

### 10) eli64s/readme-ai
- Official URL: [eli64s/readme-ai](https://github.com/eli64s/readme-ai)
- Local clone: not found in this workspace.
- Verified license: MIT.
- Pipeline source files: `readmeai/cli/main.py`, `readmeai/cli/options.py`, `readmeai/core/pipeline.py`, `readmeai/core/errors.py`, `readmeai/generators/*`, `readmeai/retrievers/*`, `readmeai/postprocessor/*`.
- Output artifacts: generated `README.md` or custom output files, plus optional Docker/CLI/offline runs.
- Adopt/reject: adopt the generation template and provider flexibility. Reject as the core repo-teacher architecture because it is README-centric rather than evidence-centric.

### 11) Egonex-AI/Understand-Anything
- Official URL: [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything)
- Local clone: `/Volumes/T7/workspace/ontology/graph/repo/understand-anything`
- Verified license: MIT.
- Pipeline source files: `understand-anything-plugin/skills/understand/SKILL.md`, `skills/understand/scan-project.mjs`, `skills/understand/compute-batches.mjs`, `skills/understand/extract-structure.mjs`, `skills/understand/merge-batch-graphs.py`, `skills/understand/build-fingerprints.mjs`, `packages/core/src/schema.ts`, `packages/core/src/staleness.ts`, `packages/dashboard`.
- Output artifacts: `.ua/knowledge-graph.json`, intermediate stage JSON under `.ua/intermediate/`, freshness metadata, dashboard/viewer output, and guided tours.
- Adopt/reject: strongly adopt the deterministic scan, batching, merge, fingerprint, and freshness model. Reject the "skill-first" framing as the main product shape; the core pipeline should stay independent and testable.

## What repo-teacher should adopt or reject

- Adopt DeepWiki-Open's SSE task flow, citation grounding, and clickable source links.
- Adopt RepoAgent's incremental refresh and on-disk documentation checkpointing.
- Adopt GitDiagram's strict validation and persisted artifact state, but only as a diagram sidecar.
- Adopt Repomix's packaging, compression, and split-output mechanics for evidence bundles.
- Adopt Readme-AI only for prose templates and output polish.
- Adopt Understand-Anything's deterministic scan -> batch -> merge -> fingerprint -> freshness chain as the strongest end-to-end reference.
- Adopt open-knowledge-skills codebase-wiki only for the wiki refresh metaphor.
- Adopt c4-codebase-architecture-skill only for architecture narrative structure and explicit fact/inference separation.
- Adopt codebase-analyzer only for phased analysis framing and the explicit markdown output contract.
- Reject any source that cannot prove the exact package name or cannot show a current LICENSE file when the license matters to the comparison.

## Stage-by-stage mapping for a CodeGraph/AST-first, business capability-first, evidence-closed human-report pipeline

1. Intake and scope lock
- Input: repository URL, local repo path, target report type, and known exclusions.
- Borrow from: DeepWiki-Open repo preparation and RepoAgent project initialization.
- Output: immutable run manifest with repo identity, commit, and output paths.

2. CodeGraph and AST scan
- Input: raw source tree plus manifest/config files.
- Borrow from: Understand-Anything scan/batch flow, RepoAgent AST use, Repomix compression as a transport adapter only.
- Output: machine-readable code graph, AST slices, file inventory, and change fingerprints.

3. Business capability extraction
- Input: verified code graph plus source slices.
- Borrow from: this repo's own `docs/decisions/0003-business-capability-first-report.md` and `docs/decisions/0004-codegraph-style-capability-query-layer.md`.
- Output: capability inventory that names user goals, boundaries, and observable results before modules or classes.

4. Evidence packet assembly
- Input: capability candidates and supporting file slices.
- Borrow from: DeepWiki-Open citations, Repomix output packing, and Understand-Anything's intermediate artifacts.
- Output: bounded evidence packets with file paths, line spans, and traceable claims.

5. Human-report synthesis
- Input: evidence packets, capability inventory, and stage metadata.
- Borrow from: open-knowledge-skills codebase-wiki for wiki refresh discipline and c4-codebase-architecture-skill for clear narrative hierarchy, but keep the report capability-first.
- Output: a human-readable report with sections for capability, implementation path, evidence, risks, and unknowns.

6. Review and closure
- Input: draft report and evidence packets.
- Borrow from: codebase-analyzer's explicit review phases and RepoAgent's refresh loop.
- Output: a closed report where every non-trivial claim resolves to a source file or a documented uncertainty.

7. Publication artifacts
- Input: finalized report.
- Borrow from: RepoAgent `markdown_docs/`, DeepWiki-Open wiki pages, GitDiagram persisted state, and Understand-Anything `.ua/` outputs.
- Output: markdown report, optional HTML viewer, evidence JSON, and freshness metadata.

## Bottom line

- Best direct reference for the intended repo-teacher direction: Understand-Anything.
- Best reference for citation-grounded interactive repo reading: DeepWiki-Open.
- Best reference for incremental doc refresh and team workflow: RepoAgent.
- Best reference for report packaging: Repomix.
- Best reference for architecture narrative shape: c4-codebase-architecture-skill.
- Best reference for phased codebase analysis: codebase-analyzer.
- Not a fit for the core pipeline: the missing/unclear `blocklune/skills -> codebase-to-tutorial` package, because I could not verify that exact skill from primary sources.
