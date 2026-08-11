# Waku human-first repository report

## Reader contract

The HTML is a teaching document for a person evaluating the repository. It must answer, in this order:

1. What the project is for.
2. Which product and engineering capabilities it contains.
3. How each capability works at a useful conceptual level.
4. Which parts are worth reusing and which claims still need runtime verification.
5. Which files, symbols, and relationships support the explanation.

Entrypoints, symbol IDs, confidence labels, and graph edges are evidence. They are not the page's narrative.

## Chosen design

- Add a Waku-specific, evidence-bounded capability overview before the generic index directory.
- Give every Waku compatibility capability a human title and a plain-language summary tied to a concrete source path and symbol.
- Keep all capabilities labelled as compatibility candidates, not curated or runtime-proven claims.
- Move launcher and raw evidence navigation into a secondary “implementation entrypoints and source evidence” section.
- Keep the detailed evidence cards and raw explorer available for verification.

## Rejected alternatives

- **Only rename “entrypoint candidate”.** Rejected because the page would remain entry-first and still force the reader to infer the product.
- **Hide evidence entirely.** Rejected because the report must remain auditable and useful for technical selection.
- **Promote Waku into the six-repository curated benchmark.** Rejected because this repository is currently a compatibility/test corpus; its runtime behavior has not been independently proven by this index.

## Acceptance checks

- The first content heading after the hero asks what the project provides, not where it starts.
- Human capability cards appear before any launcher/candidate grouping.
- The overview covers loop, memory, graph, gateways, voice, tools/MCP, model providers, dashboard/observability, and eval/release.
- Each card links to its evidence-backed detail card.
- The page never opens with “0 source-audited capabilities”.
- Desktop and 390px mobile views have no page-level horizontal overflow.

