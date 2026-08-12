# RepoLens 生产 Pipeline 独立终审

- 审计日期：2026-08-12
- 审计对象：`/Volumes/T7/workspace/ontology/graph/dev/repo` 当前冻结候选
- 对照仓库：`/Volumes/T7/workspace/ontology/graph/repo/understand-anything`
- Coze 验证产物：`/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/coze-production/capability-inventory.json`
- 审计方式：重新阅读产品源码、测试、完整本机参考 clone 与冻结 Coze 产物；未沿用旧审计结论
- 最终结论：**REQUEST CHANGES**

## 一、执行摘要

这轮重构已经解决了“所有逻辑平铺在 CLI”的问题，也确实阅读并采用了 Understand Anything 的若干关键思想：先做确定性结构分析、再做有界语义分析；使用专门的 Prompt、Agent 合同、Schema 和 Provider；并发处理业务域；最后发布 JSON/HTML。`cli.py` 现在确实只负责参数和路由，包资源也能进入 wheel。这些不是文档假设，而是源码和构建结果支持的事实。

但冻结候选还不能作为生产版本发布。阻断不在样式，也不在单元测试数量，而在核心产品承诺没有形成真实闭环：

1. 代码从未执行 `capability-reviewer` 的业务语义审校，却在成功路径上直接生成 `status: passed`；冻结 Coze 产物已经证明该缺口会产生假阳性。
2. 文档宣称的阶段产物、失败记录和最小阶段恢复并未实现；当前“阶段账本”只是全流程成功后补写的一份汇总，所有阶段都硬编码为 `passed`。
3. Coze 的两个模型分片达到 893,405 和 972,378 字节，每个分片重复携带同一份全局 CodeGraph 上下文；端到端耗时约 14 分钟，已接近默认 900 秒超时，没有字节/token 上限或自适应再切分。
4. 缓存键未绑定真实 Prompt、Schema 与模型配置，修改它们后仍可能复用旧的语义结果。

因此，测试全绿只能证明当前实现按自身代码运行，不能证明“自动识别准确业务功能、审校失败即关闭、失败可恢复、在大型仓库上性能可控”这些生产目标成立。

## 二、核验结论总表

| 验收项 | 结论 | 证据摘要 |
| --- | --- | --- |
| 完整参考 clone | PASS | 非 shallow；HEAD `fe8c5bc591716aafd79b4765549328f08ef5a52e`；origin 为 Egonex-AI/Understand-Anything |
| 真实参考而非只写文档 | PARTIAL | 结构先于语义、专门角色、并发、持久 JSON、原子发布已采用；独立 review、阶段恢复与精确缓存身份未采用完整 |
| CLI 仅参数/路由 | PASS | `src/repo_teacher/cli.py` 329 行、3 个函数；无 Prompt、Schema、模型 transport、批次/合并算法 |
| Prompt/Agent/Schema/Provider/renderer 分离 | PASS | 均为独立包；wheel 含 18 个 `.md/.json` 资源 |
| 中文 Agent 合同 | PASS（静态） | 5 个中文 Agent 合同有输入、动作、输出、Good/Bad、失败语义 |
| Agent 合同参与运行时 | FAIL | 运行时只加载定位、能力分析和章节写作；能力审校与人类阅读审校从未调用 |
| Schema + Good/Bad | PARTIAL | Good 与 unknown-ID Bad 可重放；health Bad 只因缺最终元数据被 shape validator 拒绝，未测试业务语义拒绝 |
| 中间产物与失败/缓存语义 | FAIL | 阶段文件成功后补写且硬编码 `passed`；失败不落 issue/retry；缓存身份不完整 |
| Coze 自动业务功能清单 | FAIL | 结构校验通过，但至少两项支撑/兼容边界被提升，且一项真实能力缺后端因果证据 |
| 性能和自适应切分 | FAIL | 约 14 分钟；872/950 KiB 分片；无 packet byte/token gate 或超限再切分 |
| 全量测试和静态门 | PASS | 362 tests / 276.548s / OK / skipped=1；compileall、diff check、Skill quick validate、wheel 均通过 |

## 三、Understand Anything 采用是否真实

### 已真实采用

对照仓库是完整本机 clone，而非 README 摘要。上游 `understand-anything-plugin/skills/understand/SKILL.md` 明确实现了 Pre-flight、Scan、语义 batch、并发 file analyzer、确定性 assemble/review、architecture、tour、review、save；阶段产物写入 `.ua/intermediate`，fingerprint 成功后才写 `meta.json`。其 `understand-anything-plugin/src/index.ts` 仅做极薄公共导出。

RepoLens 的以下采用是真实的：

- `src/repo_teacher/cli.py:1-25` 只导入 command handlers；`_parser()` 与 `main()` 只定义参数和命令路由。
- `src/repo_teacher/pipeline/codegraph.py`、`evidence_packets.py`、`inventory_contracts.py`、`grouping.py`、`report_contracts.py`、`synthesis.py` 已按阶段责任拆开。
- `src/repo_teacher/pipeline/synthesis.py:189-306` 以最多 4 个线程并行业务域，完成后再做全局 grouping。
- `src/repo_teacher/pipeline/inventory.py:38-103` 提供了单阶段 provider 端口、缓存复验和原子写入。
- Agent、Prompt、Schema、Provider、renderer 分别位于独立包；`pyproject.toml:24-25` 把 Prompt、Agent 和 Schema 声明为 package data。
- `docs/references/understand-anything-reading.md` 对固定提交和上游实际阶段的记录与源码一致。

### 采用仍不完整

RepoLens 文档称“specialized roles produce and review persistent artifacts”，但运行时并未形成上游那种“阶段产物先落盘、独立 reviewer 读取、失败时保留并精确退回”的机制：

- `src/repo_teacher/pipeline/prompt_contracts.py:33-83` 只加载 `business-capability-analyst`、`project-context-analyzer`、`chapter-writer`。
- 全仓运行时代码没有加载或调用 `capability-reviewer`、`human-report-reviewer`；它们目前只是可打包 Markdown。
- `docs/architecture/production-pipeline.md:96` 声称阶段产物能让失败回到最小阶段，但实现只在整个报告已成功合成后构造汇总文件。

结论：**参考采用真实，但只完成了“结构/并发/包边界”部分；“独立审校/阶段恢复/精确新鲜度”这三个生产关键点仍是文档态。**

## 四、发布阻断问题

### P0 — 语义审校未执行，却把 Coze 目录标成通过

`src/repo_teacher/agents/capability-reviewer.md` 要求第六项检查 `business_semantics`，并明确禁止把 health、静态页、单路由、测试 helper 等工程表面提升为功能。但实际执行路径没有调用该 reviewer：

- `src/repo_teacher/commands/inventory.py:109-128` 在结构校验返回后直接构造 validation JSON，`status` 与五项 check 全部硬编码为 `passed`。
- 该 validation 甚至没有 Agent 合同要求的 `business_semantics` 与 `issues` 字段。
- `src/repo_teacher/pipeline/grouping.py:135-287` 由同一个模型 grouping pass 决定分组/排除；后续确定性代码只检查 ID、路径、模块和 evidence scope，不会独立判断它是不是业务功能。
- 冻结 `capability-inventory.validation.json:3-13` 仍报告 `passed`，所以它是结构闭包报告，不是语义审校报告。

冻结 Coze 产物给出了实际假阳性：

1. `group-05-local-bridge-and-shell-data`（inventory 第 706 行起）把会话/目录/模板/settings/marketplace CRUD、bridge 白名单、WebSocket transport 和配置边界合并成一个 `differentiator`。它没有一个统一用户业务状态机；更关键的是引用的 `backend/internal/service/bridge.go:133-189` 明确显示多项 Agent 操作只返回 provider unavailable 或 safe-local mock，`backend/internal/ws/handler.go` 的 Frontier v2 只是握手/诊断/二进制回显。这应该是支撑边界或多个已证实业务流程的实现模块，不是一个产品差异化能力。
2. `group-07-invite-and-callback-intake`（inventory 第 940 行起）把真实“邀请申请”与 Deep Link/callback 兼容入口合成同一功能。`frontend/flow-ipc.cjs:35-79` 明确返回 `externalEffect: false`，只记录参数并声明外部导航/provider 副作用不支持。邀请申请可在有后端状态链证据时单列；Deep Link/callback 记录应降为 supporting/unsupported，不能凭页面/IPC/路由成为 dependent capability。
3. `group-06-plan-job-operations` 是真实用户可见能力，但 6 条 source refs 全来自前端 renderer/preload/main/IPC；仓库中实际存在 `backend/internal/httpapi/automation.go`、`backend/internal/service/automation.go`、`backend/internal/store/automation.go` 以及作业状态迁移/事件实现。当前报告声称“本地作业队列管理”，却没有引用持久化、状态转换和事件事实源，无法支持技术选型级机制结论。

同时要明确：冻结目录没有把 `health` 或“登录”单独列成功能，这是正确的；问题集中在普通壳数据/bridge/WS 与 Deep Link/callback 仍被提升，以及真实 plan/job 能力的后端因果证据漏收。核心 1–4（项目装配、Agent 任务链、受控运行时/物化、部署发布）有较完整的跨层证据，可以保留为重审输入。

**影响**：产品的主要价值就是自动生成可用于技术选型的业务功能清单；当前 validation 会给语义错误的清单出具 PASS，属于发布级假阳性。

**最小修复门**：

1. 增加真实 `CapabilityReviewStage`，必须在 grouping 后、落盘前执行，输出合同中的 `business_semantics`、稳定 issue code、JSON pointer 和 `retry_stage`；禁止由 command handler构造全 PASS。
2. reviewer 必须与产生 grouping 的模型调用独立；至少通过不同 prompt/role 做逐项反证，并用确定性规则验证结果结构。
3. 把 health-route Bad 改为结构上完整、仅业务语义错误的 persisted inventory；证明它是因 `business-outcome-missing` 被拒绝，而不是因缺 `schema_version/cache_key` 被拒绝。
4. 由 CLI 重新生成 Coze，不得手改 JSON；重跑结果必须：降级/拆分 #5，分离邀请与无副作用 callback/deep-link，给 plan/job 补齐后端状态证据，并明确 `agent.create/delete/...` 的 safe-local mock/unsupported 边界。

### P1 — 阶段账本、失败记录与恢复语义是事后汇总，不是真实 Pipeline 状态

- `src/repo_teacher/pipeline/stage_artifacts.py:8-26` 的 `_stage()` 无条件写 `status: passed`。
- 同文件 `29-162` 只根据最终 canonical/pack/inventory/narrative 拼出 01–06 与 run manifest；没有开始/完成时间、输入/输出 digest、失败 issue、重跑阶段或 attempt。
- `src/repo_teacher/commands/report.py:153-195` 在所有模型/验证都成功后才一次性构建这些记录并发布。
- `src/repo_teacher/commands/inventory.py:154-159` 和 `commands/report.py:196-201` 失败时只向 stderr 输出并返回 1，不持久化 failed stage、错误码、最后成功 checkpoint 或重跑指针。
- `skills/repository-report/references/pipeline-contract.md:7-15` 承诺的 `source-manifest.json`、`approval.json`、`chapters/*.json`、`chapter-validation/*.json`、`human-readability-review.json` 等并未作为 production output 发布。

这意味着缓存文件虽然存在，但用户无法可靠区分“上次成功缓存”“当前失败留下的半成品”和“可从哪个阶段恢复”。文档中的最小阶段恢复承诺目前不可兑现。

**最小修复门**：为每阶段建立持久 journal/state machine（`started/passed/failed`），记录输入 digest、Prompt/Schema/model identity、started/completed time、attempt、output digest、issue 与 retry stage；在阶段开始、成功和异常分支分别原子更新。实际发布文档承诺的阶段产物，或删除未实现承诺；基于用户要求，本次应实现而不是删文档。新增“中段 provider 失败后保留前序 PASS、当前 FAIL，二次运行只重跑当前及下游”的集成测试。

### P1 — 分片按目录根而非输入大小，自适应切分未达到生产要求

冻结 Coze cache 给出可复现实测：

| 分片 | module 数 | packet bytes | hints | excerpts | CodeGraph context |
| --- | ---: | ---: | ---: | ---: | --- |
| domain-00 | 8 | 893,405 | 132 | 68 | 128 paths / 320 nodes / 640 edges / 184,462 JSON chars |
| domain-01 | 3 | 972,378 | 122 | 96 | 128 paths / 320 nodes / 640 edges / 184,462 JSON chars |

时间戳显示：04:37:16 写两个分析包；domain-01 在 04:44:30 完成；domain-00 在 04:48:14 完成；grouping 在 04:51:14 完成；总耗时约 13 分 59 秒，距离默认 `--model-timeout 900` 只剩约一分钟。

源码原因明确：

- `src/repo_teacher/pipeline/inventory_contracts.py:422-484` 只按顶层 product root 分域，最多 6 个；没有 packet 字节、估算 token、source excerpt 或 graph edge 阈值。
- `src/repo_teacher/pipeline/synthesis.py:359-374` 先对所有 product modules 构建一份全局 CodeGraph context，再原样传给每个 shard。
- `src/repo_teacher/pipeline/evidence_packets.py:621-625` 虽计算了本 shard 的 `codegraph_paths`，但 `700-750` 返回时仍在第 745 行写入未过滤的整个 `codegraph_context`。因此 backend 与 frontend shard 重复携带同样 128 paths/320 nodes/640 edges。
- `_attach_source_excerpts()` 只约束 excerpt 字符为 240,000；完整 packet 还包括 hints、graph、global context 与 explore 输出，没有总大小上限。
- 现有测试只验证 shard 数和调用形态，没有大型 packet 的 byte/token gate、超限再切分或运行时间预算。

**最小修复门**：

1. `_build_inventory_shard_pack` 必须按 shard module paths 同时过滤 `source_paths/nodes/edges/module_paths`，并验证每条边端点闭包。
2. materialize 前计算序列化字节和估算 token；超过明确上限就按 CodeGraph 社区/模块权重自适应拆分，直到全部满足上限或 fail-closed。
3. 上限与截断原因写入 stage metrics/run manifest；禁止只加超时。
4. 添加近似 Coze 规模的 fixture/benchmark，断言每个 packet 在预算内、没有跨 shard 全局 context 重复，并给出冷缓存 p95 目标。当前约 14 分钟不能作为达标基线。

### P1 — 缓存键未绑定 Prompt、Schema 和模型配置

`skills/repository-report/references/pipeline-contract.md:24` 明确规定 cache 同时绑定 source manifest、analysis fingerprint、Prompt version、Schema version 和模型配置。但 `src/repo_teacher/pipeline/synthesis.py:840-872` 的 cache identity 只有 source 路径、commit、analysis fingerprint、文件 hash、provider、inventory digest 与手工常量 `REPORT_SYNTHESIS_CONTRACT_VERSION`：

- 没有实际 Prompt 文件 digest；
- 没有实际 Schema digest/version；
- 没有 `REPO_TEACHER_CODEX_MODEL`、reasoning effort、OpenCode model 或 DeepSeek model；
- `CapabilityInventoryStage._read_valid_cache()` 只对当前 packet 做 scope 复验，无法发现“Prompt/模型变了但旧语义仍符合结构”的陈旧结果。

**最小修复门**：建立可序列化 `RunIdentity`，纳入 source manifest digest、analysis fingerprint、每个实际 Agent/Prompt/Schema digest、provider 名、model、reasoning/temperature 等影响输出的配置和工具版本；每阶段缓存使用自己的 input identity，并把 identity 写进 stage artifact。添加 Prompt、Schema、model 任一变化必 cache miss 的测试。

## 五、非阻断架构问题

### P2 — orchestration 仍有过大的混合模块和依赖倒置

- `pipeline/synthesis.py` 872 行，同时编排 inventory shard、global grouping、project overview、chapter batch、cache workspace 与报告导航；虽然不再污染 CLI，也没有检测到 import cycle，但仍超出“stage ordering only”的文档描述。
- `pipeline/evidence_packets.py` 1,050 行，并从 `prompt_contracts` 导入 `_json_artifact`。证据构建层不应依赖 Agent/Prompt 合同层；JSON 序列化应放到无语义的 persistence/serialization 模块。
- `commands/entrypoints.py` 686 行，聚合了很多与主 production report 无关的 legacy command 适配。

**建议修复**：按 inventory orchestration、report orchestration、cache identity、serialization 四个边界拆开；保持 command 只组合 application ports。此项本身不阻断，但应在生产冻结前建立维护性债务单。

### P2 — Bad Case 资产还不能证明语义 gate

- `capability-inventory-bad-unknown-disposition-id.json` 是 mutation descriptor，不是可直接送进 validator 的 standalone inventory；本次必须先把 mutation 应用到 Good case 才能重放。
- `capability-inventory-bad-health-route.json` 缺 7 个最终必填字段，validator 首先报 shape 缺失，无法证明 health route 会被业务语义 gate 拒绝。
- `scripts/export_inventory_schema.py` 能导出静态 Schema，但没有 `--check` 模式；目前只能在外部脚本里 export + cmp。

**建议修复**：提供两个完整 persisted Bad fixtures（semantic false positive、unknown final ID），统一测试 runner 输出稳定 issue code；给 Schema 导出脚本增加 `--check`，放入 CI。

## 六、Coze 七项功能逐项裁决

| # | 当前标题 | 裁决 | 原因 |
| --- | --- | --- | --- |
| 1 | 多 Agent 协作项目与运行时工作区装配 | 保留，重审边界 | 创建项目、成员装配、runtime bootstrap 和工作区进入有跨前后端证据；需要明确 Agent 创建本身哪些只是本地已存目录、哪些不支持远端创建 |
| 2 | Agent 任务提交、排队执行与结果回传 | 保留，建议在章节内显式分支 | 任务状态机、Worker claim/renew、runtime action、本地 ACP 与服务端 Agent 有实证；技术选型报告必须把三条 executor 分支分别讲清，不要只写在一个长 mechanism 中 |
| 3 | 受控运行时命令执行与文件物化 | 保留 | preflight/allowlist、execution、文件写入、materialize/rollback/version 是同一工作区交付链，可形成完整技术选型章节 |
| 4 | 项目版本发布与本地可访问端点管理 | 保留 | sandbox provider、部署状态机、日志、endpoint、cancel/stop 形成独立用户结果；需强调仅本地 sandbox/disabled provider，不是云端一键部署 |
| 5 | 本地应用壳数据面与安全桥接边界 | 拒绝当前分组 | 普通 CRUD、transport、安全边界、marketplace、session 和 safe-local mock 被打成一个 differentiator；无统一用户结果/状态机 |
| 6 | 长期计划查看与本地作业队列管理 | 保留但证据不闭合 | 后端确有 plan/job/service/store 状态实现，但 inventory 只引用前端，当前机制说明不足以做技术选型 |
| 7 | 邀请申请、Deep Link 与回调参数落地 | 拆分/降级 | 邀请申请可能是业务流；Deep Link/callback 只本地记录且 `externalEffect:false`，应 supporting/unsupported，不应与邀请合并成 dependent capability |

## 七、验证证据

本次终审独立执行的验证如下：

```text
PYTHONPATH=src python3 -m unittest discover -s tests -q
Ran 362 tests in 276.548s
OK (skipped=1)
```

其他门：

- `PYTHONPATH=src python3 -m compileall -q src/repo_teacher`：PASS
- `git diff --check`：PASS
- Skill official `quick_validate.py skills/repository-report`：`Skill is valid!`
- `python3 -m pip wheel . --no-deps`：PASS，wheel 411,047 bytes
- wheel 资源核对：18 个 Agent/Prompt/Schema `.md/.json` 资源
- 静态公开 Schema 重新导出并 `cmp`：PASS
- 包内 Python import graph AST 检查：0 cycle
- Good case：`require_persisted_inventory` 接受
- health Bad：拒绝，但理由是缺 `cache_key/generator/grouping_complete/project/schema_version/source_manifest_sha256/validation_artifact`，没有进入语义 gate
- unknown disposition ID Bad：应用 mutation 后拒绝，错误为 `module disposition references an unknown capability id`
- 冻结 Coze inventory：严格 persisted validator 接受；79 条 source ref 的路径/行号有效。这证明结构闭包成立，但不能消除上文的业务语义假阳性。

## 八、重新申请终审的最小门

只有同时满足以下条件，才应重新申请 PASS：

1. 真实 capability semantic reviewer 进入 CLI pipeline，不能由 command handler伪造 PASS；validation 包含 `business_semantics`、issues、retry stage。
2. CLI 冷缓存重跑 Coze，不手工修改；#5/#7 的支撑边界被正确降级/拆分，#6 有后端状态证据，#1/#2 明确 safe-local mock、本地 ACP 与服务端 Agent 的真实支持范围。
3. 每阶段真实落盘 `started/passed/failed` 状态、输入输出 digest 和重跑指针；一次注入失败测试证明可从最小阶段恢复。
4. shard context 按域过滤并有总 packet byte/token 上限；超限会自适应再切分。Coze 冷缓存运行需有可接受且留有余量的性能门，不能再贴着 900 秒超时。
5. cache identity 绑定真实 Prompt、Schema、Agent 合同、provider model/config 和 source manifest；变化必 miss。
6. 全量测试、Schema Good/semantic Bad/unknown-ID Bad、wheel 资源、Skill validator、Coze strict validation 全部通过，并补充对 semantic issue code、failure journal、adaptive split 和 cache invalidation 的回归测试。

在这些门关闭前，本冻结候选不应标记为“生产级完成”。
