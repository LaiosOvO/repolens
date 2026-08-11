# 教学 / 功能发现第二轮整改记录

日期：2026-08-10  
对应审计：`docs/audits/teaching-reaudit.md`、`docs/audits/teaching-reaudit-round2.md`  
整改状态：**第二次独立复审为 REQUEST CHANGES；所列阻塞已继续修复，等待第三次独立复审；本文不自行给出 PASS**

## 结果摘要

本轮把原来混在 `FeatureRecord` 展示层里的三类事实拆开呈现：

1. `capability-cluster`：仅在真实 Git 根、canonical remote、HEAD commit、固定路径和固定 SHA-256 全部匹配时，才采用源码审计清单并标为 `source-audited`。
2. `http-route` / `cli-command` / `entrypoint`：由 AST、词法 call 或明确可执行标记确认的运行边界。
3. `entrypoint-candidate`：符号确实存在，但没有 Python main guard、shebang、明确监听或其他执行证据，不计为已确认入口。

普通配置文件、普通模块和 URL 前缀不再被包装成产品能力。

## 逐项整改

| 审计门 | 本轮实现 | 验证证据 |
|---|---|---|
| 注释/字符串伪造 HTTP/CLI | Python 使用 `ast.Call`；JS/TS 使用保留字符串 token、丢弃注释的轻量词法 call 识别；不再使用正则回退 | `test_comments_and_string_literals_cannot_forge_routes_or_commands` |
| HTTP client / 任意 command 误报 | HTTP 与 CLI 分别使用保守 receiver 集；`requests.get`、`client.post`、`database.command` 不再升级；JS 除法与 regex 上下文分开 | `test_client_calls_unrelated_commands_and_wrong_go_package_are_not_boundaries` |
| 普通模块 fallback | 删除 `module-capability` 代表文件 fallback | `test_configuration_and_ordinary_modules_do_not_become_capabilities` |
| `main.py:main` 误报 exact | 符号置信度与运行边界置信度分开；没有 AST main guard/明确执行标记时输出 `entrypoint-candidate` + `entry-candidate` 证据 | `test_arbitrary_run_and_start_methods_are_not_public_entrypoints` |
| Go 错误 package 误报 exact | `func main` 必须同时位于 `package main`；否则只能保留候选 | `test_client_calls_unrelated_commands_and_wrong_go_package_are_not_boundaries` |
| 产品能力召回不足 | 新增 `capability_catalog.py`，对六个固定 commit 的 19 个核心实现路径建立人工源码审计清单；每个文件再以 SHA-256 锁定，内容漂移时不会沿用 `source-audited` | `test_version_pinned_six_repository_capability_recall`：19/19，100% recall |
| 复制文件伪造 source-audited | capability catalog 默认 fail-closed；无 project snapshot、非 Git、非顶层 Git root、remote/commit 不匹配均不加载审计清单 | `test_copied_reference_files_without_git_identity_are_not_source_audited` |
| Golden 与产品清单循环同源 | 期望 commit、19 路径与关键技术事实移到独立 fixture `tests/fixtures/reference_capabilities.json`，测试不再调用产品 `reference_ground_truth()` 生成 oracle | `test_version_pinned_six_repository_capability_recall` |
| 教程只是 BFS | 教程现在包含“能力边界 → 职责化源码切片 → 未证明缺口”三章；仅带 `relationship_id` 的切片称为已解析静态关系 | `test_generates_grounded_tutorial_codemap_and_coverage` |
| 审计能力只有单点 | 核心符号按能力 slug/path 评分，优先沿已解析关系扩展；分析器不足时只加入同一已验证仓的相关审计切片并明确 `location-only`，不伪造关系 | Golden 约束 19 项每项至少 2 个节点、总边数大于 0 |
| CodeMap 显示 Mermaid 原文 | artifact 增加结构化 `nodes` / `edges`；HTML 显示节点表和带语义的 → / ⇢ 边，不再展示 Mermaid 源文 | `test_report_leads_with_features_and_connects_steps_to_evidence` |
| 技术维度不足 | 每个新记录固定输出 parser/framework/store/retrieval/llm/incremental/evidence/ui 八维；未取证项显式 `unknown` | Golden test 对所有 19 个能力逐项检查八维完整性 |
| 证据分数制造质量错觉 | 状态改为 `signals-present` / `partial-signals` / `minimal-signals`，附 `quality_assessment: not-assessed`；HTML 展示原始布尔信号，不展示质量百分比 | `tests/test_artifacts.py`、`tests/test_report.py` |
| 源码不可点击 | 功能源码和证据位置输出受仓库根目录约束的本地 `file://` 链接；越界时退化为不可点击文本 | `test_report_leads_with_features_and_connects_steps_to_evidence` |

## 六仓 Golden set

| 仓库 | 固定 commit | 核心路径数 | 当前 source-audited 召回 |
|---|---|---:|---:|
| SourceBridge | `2a128bf0c846` | 3 | 3/3 |
| PocketFlow Code2Tutorial | `05b24cbbb0fe` | 2 | 2/2 |
| OpenWiki | `7531d615216e` | 3 | 3/3 |
| Understand Anything | `fe8c5bc59171` | 3 | 3/3 |
| CodeBoarding | `8c3f2218c3ec` | 3 | 3/3 |
| DeepWiki Open | `4181daa5ebde` | 5 | 5/5 |
| **合计** | — | **19** | **19/19（100%）** |

Golden probe 的 oracle 来自独立 JSON fixture，并直接对六个完整本地 clone 执行生产 `build_index()` 链路，校验 Git commit、工作树文件与 HEAD 一致、扫描完整性、19 个能力进入最终索引、source-audited 来源、八类技术维度、每项至少两个职责切片，并通过 step 与直接 evidence 的真实路径约束 `docs/tests/examples/__tests__/e2e` 误报为 0。它还会渲染六份真实 HTML，确认 CodeMap 含可读节点/边且没有可见 Mermaid 源码；另有无 Git 文件副本攻击测试。默认参考根目录为 `/Volumes/T7/workspace/ontology/graph/repo`，也可通过 `REPO_TEACHER_REFERENCE_ROOT` 指定。

## 教学产物边界

- `source-audited` 只表示该固定版本文件已被人工归入某项能力，不证明所有运行时分支。
- 自动发现的路由、CLI 和入口只叫“运行边界”，不再叫“产品能力”。
- 教程明确列出 data flow、state、error path 缺口；没有动态跟踪或行为测试时不会补写推断。
- CodeMap 的实义边只来自已解析关系；阅读顺序继续独立建模。
- 技术维度的 `unknown` 是产品输出的一部分，不使用关键词命中冒充已证实技术选型。

## 本轮验证

已完成：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth -v

Ran 21 tests ... OK
```

```text
ruff check <本轮源码与测试>
All checks passed!

python3 -m compileall -q <本轮源码与测试>
```

六个真实 clone 的端到端 Golden probe：

```text
SourceBridge               3/3，扫描 1575 文件
PocketFlow Code2Tutorial   2/2，扫描 197 文件
OpenWiki                   3/3，扫描 321 文件
Understand Anything        3/3，扫描 457 文件
CodeBoarding               3/3，扫描 383 文件
DeepWiki Open              5/5，扫描 149 文件
合计                       19/19（100%）

全部扫描 complete；docs/tests/examples 等非产品目录误报 0；
六份 HTML 均含可读 CodeMap 节点/边，可见 Mermaid 源码 0；
19 项能力合计 59 节点 / 55 边，其中 24 条为已解析静态关系。
```

全部 owner 稳定后的全量回归由主 Agent 执行：

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 157 tests ... OK
```

真实 Golden test 已从“只调用能力匹配函数”升级为完整 `build_index()` + `validate_index()` + `render_report()` 生产链路。最终结论仍交由主 Agent 新启动的独立审计 Agent 给出；本整改记录不复用此前已打回的结论。

## 待独立复审重点

1. 在六个完整仓库上运行完整 `build_index`，确认扫描器哈希与 manifest 哈希一致，19 个能力实际进入最终 HTML。
2. 人工打开至少 SourceBridge、OpenWiki、DeepWiki 三份 HTML，检查首屏是否先展示领域能力，边界/候选是否清楚降级。
3. 验证 CodeMap 节点/边在桌面与窄屏都可读，页面不显示 Mermaid 源文本。
4. 检查 source-audited manifest 的维护流程：上游 commit 变化必须重新审计并更新文件哈希，不能只改 commit 字符串。
