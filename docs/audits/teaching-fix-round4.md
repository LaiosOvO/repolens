# Teaching / Feature / Tutorial / CodeMap 修复记录（Round 4）

日期：2026-08-10  
范围：`features.py`、`capability_catalog.py`、`artifacts.py`、`report.py` 与对应测试 / golden。  
状态：修复实现已完成，等待独立复审；本文不自行给出 PASS。

## 1. 修复结论

本轮把“看起来像框架调用”“人工写下的关系描述”和“建议阅读顺序”从已确认实现事实中拆开：

- HTTP / CLI 只有在 receiver 能回溯到本文件中的框架 import、constructor 或 factory 时才进入 confirmed。
- 66 个固定版本职责切片逐项绑定源码 hash 与行范围；`symbol_id` 只在单一精确符号覆盖整个切片范围时填写。
- `relationship_id` 只引用索引中真实存在、且 source / target 都属于同一能力审计符号集合的边；同一端点对不会重复包装成多条“主链”。
- 无法证明静态边时统一输出 `location-only` 和具体原因。contract 中的人工作用描述保留为待验证阅读假设，不再冒充实现流。
- 普通 feature 不再递归 BFS 扩展调用图，只展示入口与入口直接解析到的一跳调用。
- tutorial 改为“结论（用途 / 入口）—拆解（职责主链 / 状态 / 依赖 / 错误）—结论（复用边界）”；内容由真实 claim、evidence snippet 与 relationship 状态生成。
- CodeMap 的实线 resolved relationship、虚线 suggested reading order 和 relationship gap 分开输出；虚线明确不是 implementation flow。

## 2. Framework provenance

### Python

仅识别由下列已证明 constructor / factory 产生的 receiver：

- HTTP server：FastAPI、APIRouter、Flask、Blueprint、Starlette Router。
- CLI：ArgumentParser、Click Group / Command、Typer。
- HTTP client（例如 httpx / requests）会被识别为 client，不能产生服务端 route。

未绑定的 `app.get(...)`、`router.post(...)`、`program.command(...)` 不再产生 confirmed 或 candidate feature。

### JavaScript / TypeScript

ESM 与 CommonJS 使用同一 provenance 规则，已覆盖：

- `import express` / `require("express")` 后构造的 Express app / Router。
- `import fastify` / `require("fastify")()` 产生的 Fastify instance。
- `@koa/router` / `koa-router` constructor。
- Commander 的 ESM、destructured CommonJS 与 property constructor。
- axios、普通 object、未绑定 app / program 的负向对抗。

对应专项：`tests/test_features.py`。

## 3. 六仓 66 个切片闭包

真实 rebuild + `validate_index` 的首轮结果如下。关系数是 step 上挂载的真实 relationship 数，不含 reading-order：

| 仓库 | 能力 | 切片 | 精确 symbol | 真实 relationship | location-only | 已知技术 claim |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge | 3 | 11 | 10 | 6 | 5 | 8 |
| PocketFlow code2tutorial | 2 | 7 | 7 | 0 | 7 | 6 |
| OpenWiki | 3 | 10 | 0 | 0 | 10 | 9 |
| Understand Anything | 3 | 9 | 0 | 0 | 9 | 11 |
| CodeBoarding | 3 | 11 | 11 | 7 | 4 | 11 |
| DeepWiki Open | 5 | 18 | 10 | 5 | 13 | 14 |
| **合计** | **19** | **66** | **38** | **18** | **48** | **59** |

说明：OpenWiki / Understand Anything 当前 TypeScript 分析结果不能为这些多行职责切片提供覆盖整个范围的精确符号，因此诚实降级为 location-only；没有拿同文件重叠符号或阅读顺序补数。

具有真实能力内主链的核心能力包括：

- SourceBridge execution path：4 个真实调用关系。
- SourceBridge graph store：`StoreIndexResult -> Store` receiver-type 关系；所有能力 / 技术证据均位于 `internal/graph/store.go`，没有 `testhelper`。
- SourceBridge code tour：`generate_code_tour -> TourStop` 真实构造调用。
- CodeBoarding full analysis、component clustering、call graph builder：合计 7 个真实调用 / contains 关系。
- DeepWiki CodeMap service 与 wiki structure：合计 5 个真实调用关系。

本轮还修正了此前的错误或复合定位：

- SourceBridge `TourStop` 改为真实声明 `38-50`；门禁职责绑定 `generate_code_tour:128-181`，不再把 imported `evaluate_evidence_gate` 冒充本地声明。
- CodeBoarding 分发切片收窄为 `run_from_args:74-80`。
- DeepWiki 服务切片收窄为 `_generate_json:46-65`、`_format_context:128-148`、`_ground_citations:201-222`。
- Python decorator / Go declaration 的审计起止行与真实 symbol range 对齐。

## 4. Golden 的防回归边界

`tests/fixtures/reference_capabilities.json` 现在为每个能力保存两类 golden digest：

1. `closure_sha256` 锁定每个切片的 `source_symbol`、role、path、range、snippet hash、精确 symbol（含自身 range）、真实 relationship（ID / kind / endpoints / path / line）、relationship status 与 claim scope。
2. `technology_claims_sha256` 锁定每个已知技术 claim 的 dimension、value、窄 claim scope、source path、evidence kind / path / range / snippet hash。

测试不是只比摘要 hash；在计算 digest 前还逐项断言：

- symbol path 一致且 symbol range 覆盖审计 range。
- relationship 两端都属于该能力的审计 symbol 集合，kind 一致。
- 无 relationship 时必须是 `location-only`，claim scope 和 explanation 必须明确缺口。
- 六仓各自运行 `validate_index`。
- 总量固定为 19 个能力、66 个切片、59 个已知技术 claim、18 条 CodeMap resolved edge。

## 5. Tutorial 与 CodeMap

普通入口的实现路径现在是：入口 symbol + 入口直接调用的一跳目标。新增 A → B → C 对抗用例，入口为 A 时 C 不会进入教程，防止恢复为 BFS。

每个 tutorial 的教学 contract 包含：

- `purpose`
- `entry`
- `main_chain`（每个切片单独给出 resolved / location-only 与 gap）
- `data_and_state`（只复述带独立证据的 store / retrieval / incremental claim）
- `dependencies`（只复述带独立证据的 parser / framework / llm / ui claim）
- `error_and_evidence_gaps`（根据切片与 evidence 中实际错误 / 重试信号区分“部分可见”和“完全未知”）
- `reuse_boundary`（直接列出可复用职责、源码位置、关系状态和必须复验项）

CodeMap 新增 `relationship_gaps` 与 `implementation_flow_status`。虚线 edge 的语义固定为 `suggested-reading-order; not implementation flow`，不会计入 resolved coverage。

## 6. 报告交互修复

- 所有 candidate 从“已确认运行边界”计数中排除。
- feature step 只有存在真实 relationship ID 时才显示 `resolved-static:<kind>`；否则显示 `location-only（未证明实现流）`。
- 本地源码链接增加 `#Lstart-Lend` fragment，保留精确行定位信息。
- 首屏不再直接铺开绝对路径；先显示项目目录，完整路径放入可展开详情，避免移动端把 `sourcebridge` 路径拆成多行后抢占主视觉。
- 把“3 个领域能力 / 5 个运行边界 / 0 个候选”改写为“核心功能 / 可触发入口 / 不可执行候选”，并在短标签中保留术语解释，减少普通用户把静态证据误解成可运行能力的风险。

## 7. 当前验证证据

已完成：

- framework / tutorial / report 专项：25 tests，全部通过。
- 分组三轮全量回归：31 + 88 + 91 = 210 tests，全部通过。
- 六仓 golden 在当前稳定代码上最终复跑：1 test / 6 个 subtest，34.920 秒，全部通过。
- 六仓独立 rebuild / `validate_index`：19/19 能力、66/66 切片、59/59 已知技术 claim，全部 valid。
- `uv run ruff check src tests`：通过。
- `PYTHONPATH=src python3 -m compileall -q src tests`：通过。

未完成且不应被静态测试替代：

- Browser runtime 当前没有可用 Chromium binding（`getForUrl` 返回 `No browser is available`）；尝试通过 Codex 面板打开最终生成报告也没有建立可控制的 browser binding。因此 1440 / 390 的真实 Chromium 首屏、展开、源码链接点击与 overflow 检查尚未完成。
- 最终报告已重新生成到 `/private/tmp/repo-teacher-round4-final/index.html`，供独立审计在有 Chromium binding 的会话中继续验证。
- SourceBridge 参考 clone 的 `LICENSE` 仍被其他并行任务删除；本轮没有越权恢复其他 Agent / 用户的工作树修改。最终 golden 已在该状态下通过，dirty-worktree 只作为来源状态警告保留。

最终独立复审仍需取得真实 1440 / 390 浏览器证据；本文只记录修复和现有证据，不自行给出 PASS。

## 8. 修改文件

- `src/repo_teacher/features.py`
- `src/repo_teacher/capability_catalog.py`
- `src/repo_teacher/artifacts.py`
- `src/repo_teacher/report.py`
- `tests/test_features.py`
- `tests/test_artifacts.py`
- `tests/test_report.py`
- `tests/test_reference_ground_truth.py`
- `tests/fixtures/reference_capabilities.json`
- `docs/audits/teaching-fix-round4.md`
