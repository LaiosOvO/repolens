# 命名功能 / 模块定位独立审计

- 审计日期：2026-08-10
- 审计范围：`module_locator.py`、`module_report.py`、CLI `explain`、对应测试
- 参考基线：SourceBridge、PocketFlow Code2Tutorial、OpenWiki、Understand Anything、CodeBoarding、DeepWiki-Open 六个完整本地仓库
- 最终结论：**REQUEST CHANGES（生产级阻断）**

## 结论先行

这版已经实现了三个有价值的基础能力：输出是摘要优先的独立 HTML；候选卡片能跳到模块详情；由 CLI 生成的本地文件 URI 做了项目根目录包含检查。`exact / ambiguous / candidate / not_found` 也有机器可读状态，合成 ACP 用例能定位到 `src/acp`。

但当前的 `exact` 只证明“目录 basename 唯一同名”，不证明“这里实现了用户所问的功能”。它仍会把文档、生成样例、测试镜像目录当成确定模块；同时数据模型只允许单个目录，不能表达一个功能横跨 router、service、schema、前端组件，或由仓库根目录多个文件共同实现的情况。六仓真实探针没有一个产生可直接作为生产技术选型依据的准确功能实现面。因此现在不能把该模块标记为生产完成，也不能向用户声称已经参考完整。

## 验证方式与证据

### 自动测试

执行：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_module_locator tests.test_module_report tests.test_cli -v
python3 -m compileall -q src/repo_teacher tests/test_module_locator.py \
  tests/test_module_report.py tests/test_cli.py
```

- 模块定位和 HTML 专项测试：7/7 通过。
- CLI 中 `explain` 的 2 个测试通过。
- 同一轮完整 `tests.test_cli` 有 1 个与本模块无关的并发中 Skill Export symlink 回归失败；这不用于否定 `explain`，但也说明本轮不能宣称整个 CLI 套件全绿。

现有专项测试只覆盖合成的 Python 仓库、唯一 `src/acp`、同名 `examples/acp`、文件名模糊匹配、Unicode 目录和 HTML escaping。没有任何六仓 golden case，也没有根目录多文件功能、跨层功能、生产/测试镜像、生成目录、真实 Go/TypeScript monorepo、行级跳转或候选排序测试。

### 六仓真实只读探针

每个仓库均用当前 `build_index()` 在内存重建索引，再调用 `locate_modules()`；没有向参考仓库写文件。

| 仓库 | 查询 | 当前结果 | 与真实实现的偏差 |
|---|---|---|---|
| SourceBridge | `knowledge` | `ambiguous`，5 个 exact basename | 把管理页、Go/Python 生成代码、`internal/knowledge` 和 `workers/knowledge` 平铺为同名候选，不能表达它们是同一能力的 UI / contract / domain / worker 分层；`workers/knowledge` 还绑定了错误测试集合。 |
| PocketFlow Code2Tutorial | `tutorial` | `not_found` | 教程流水线实际由根目录 `main.py`、`flow.py`、`nodes.py` 实现；目录模型完全漏报。相反查询 `FastAPI` 会把纯 Markdown 的 `docs/FastAPI` 标成 `exact / 已确定`。 |
| OpenWiki | `visualize` | `ambiguous` | `src/visualize` 与镜像测试目录 `test/visualize` 被视为两个同等 exact 名称，生产模块无法确认；报告显示生产目录 inbound=0，但 `src/cli/runners.ts` 明确导入 `runVisualizeServer`。 |
| Understand Anything | `viewer` | `ambiguous` | 产品包 `packages/viewer` 与 `tests/skill/viewer` 同名即歧义；测试镜像没有被折叠为产品模块的测试证据。 |
| CodeBoarding | `static_analyzer` | `ambiguous` | 产品 `static_analyzer` 与 `tests/static_analyzer` 同名即歧义；没有利用其 LSP symbol/call graph 与 cluster→component 机制确定真实组件边界。 |
| DeepWiki-Open | `codemap` | `candidate`，首位 `api/schemas` | 真正能力横跨 `api/routers/codemap.py`、`api/services/codemap.py`、`api/schemas/codemap.py`、`src/components/CodeMap.tsx` 和 WebSocket 客户端；当前把 schema 目录排第一，并把整个 `api`、`src` 等祖先目录混入候选。 |

额外真实性反例：PocketFlow 中查询 `docs` 会得到唯一 `docs` 目录并显示“已定位到唯一模块 / 已确定”，该目录包含 187 个文档或配置文件，却不是教程生成器的实现模块。

## P0 — 阻断生产发布

### P0-1 `exact` 是名称精确，不是功能实现精确，HTML 把它提升成事实

`module_locator.py:489-491` 声明 exact 的条件只是唯一目录 basename；`module_locator.py:521-526` 仅凭唯一同名目录选择 `exact`；`module_report.py:43-44` 将其渲染为“已确定”，`module_report.py:219-220` 再渲染为“已定位到唯一模块”。这里没有源码内容、入口关系、产品/测试分类、功能行为或人工选择证据。

真实反例已经复现：PocketFlow 的 `docs/FastAPI` 和整个 `docs` 都会被标成 exact。低价值目录扣分也无法保护 exact 分支，而且 `_LOW_VALUE_DIRECTORY_PARTS` 根本没有 `docs`、`generated`、`gen`。

必须修复：

1. 将现有状态改名为 `exact_name_match`，不得显示“已确定功能模块”。
2. 新增独立的 capability certainty；只有产品源码证据、明确入口/处理链和排除测试/文档/生成目录后，才能称为 `verified_capability_surface`。
3. 文档、测试、fixture、example、generated/gen、vendor、build 只能作为证据或低优先候选，不能仅凭 basename 自动成为确定实现。
4. 测试镜像目录应关联到生产模块；只有多个真实生产模块同名时才产生功能歧义。

### P0-2 单目录模型无法表达真实功能，实现面在六仓上系统性漏报或错排

`_files_by_directory()` 把每个文件加入所有祖先目录（`module_locator.py:84-95`）；`locate_modules()` 只遍历这些目录（`module_locator.py:506-518`）；`_build_module()` 又把选中目录全部后代文件视为模块（`module_locator.py:347-351`）。因此：

- 根目录单文件/多文件功能无法成为候选，导致 PocketFlow `tutorial` 为 `not_found`；
- 跨目录功能不能组成一个实现面，导致 DeepWiki Codemap 被拆成 schema/router/service/UI 多个目录；
- 子文件命中会向所有祖先传播，`api`、`src` 等大目录也被当作“模块”，边界越来越宽；
- 排序偏爱命中符号数量和目录深度，不理解 router→service→schema→frontend 的职责链。

这与用户要求的“功能对应到确定模块，并说明功能怎么实现”不相符。真实功能不总等于一个文件夹。

必须修复：引入 `CapabilitySurface`，允许一个能力包含多个 `source slices`（directory/file/symbol/line range），并明确 `entry / orchestration / model / persistence / presentation / test` 角色。候选生成应同时支持目录锚点、文件/符号锚点和关系图扩展，再用最小覆盖边界而不是祖先目录聚合。ACP 恰好是单目录时可退化成一个 surface，但不能把单目录假设写死到领域模型。

### P0-3 “测试证据”会误绑测试，也会漏掉真正测试

`module_locator.py:428-441` 在关系关联失败后，只要测试路径包含模块 basename 就加入 `name-match`。HTML 不展示 `association`，也不区分关系证据与名字猜测，却统一放在“测试证据”下；`module_report.py:200-201` 还断言测试决定能否安全复用。

SourceBridge 探针中，`workers/knowledge` 被附上 `internal/api/graphql/knowledge_*_test.go` 等 Go API 测试，仅因为路径含 `knowledge`；真正直接导入 `workers.knowledge.learning_path` / `code_tour` 的 `workers/tests/test_learning_path.py` 与 `workers/tests/test_code_tour.py` 没进入前列，暴露当前跨目录 import resolution 不足。名称相同不能证明测试覆盖某个模块，更不能作为“安全复用行为边界”。

必须修复：删除 `name-match` 的证据资格，最多显示为“可能相关测试（未验证）”；生产级测试关联必须来自已解析 import/call、语言测试配置、同 package 规则或显式用户映射，并在 JSON/HTML 展示 association、confidence 和目标符号。没有可靠关联时应明确显示“未发现已验证测试证据”。

## P1 — 重要准确性缺口

### P1-1 “底层怎么实现”实际只是按文件名角色硬编码的阅读顺序

`_file_role()` 依据文件名包含 `manager/service/model/client/view` 等词分配角色（`module_locator.py:196-221`）；`_implementation_steps()` 再按固定的 entrypoint→boundary→orchestration→core→model→persistence→adapter→presentation→test 顺序输出通用文案（`module_locator.py:292-334`）。它没有从调用边、数据流或入口路径推导步骤。

HTML 在 `module_report.py:187-188` 虽承认这是“静态阅读顺序”，标题、卡片 CTA 和每步文案仍使用“底层怎么实现”“执行核心编排”“读写持久状态”等行为性表达。一个叫 `models.py` 的文件可被猜为数据契约，但当前没有证据证明每个文件实际承担文案所述行为。

必须修复：把现有内容明确降级为 `heuristic reading order`；另建基于已解析边的 `implementation trace`，每一步携带 source/target symbol、关系类型、行范围与证据。无法形成 trace 时，不生成行为性说明。

### P1-2 模块依赖数字包含大量未解析关系，真实边也会漏掉

`module_locator.py:366-385` 把模块内所有 target 未解析的关系都记作 outbound；报告 `module_report.py:193-198` 将三组统一称为“模块依赖关系”。SourceBridge `internal/knowledge` 18 个文件出现 372 internal、520 inbound、1011 outbound；这个量级更像语法级引用噪声，而不是可供技术选型的模块依赖。反方向，OpenWiki `src/visualize` 显示 inbound=0，但 `src/cli/runners.ts:33,70` 明确导入并调用 `runVisualizeServer`。

必须修复：分开 `resolved internal calls/imports`、`resolved external dependencies`、`unresolved references`，不要把 unresolved 计入模块依赖结论；加入语言级 resolver 精度指标与 unsupported diagnostics；组件边界优先使用已解析跨模块边，并用真实六仓建立 precision/recall golden assertions。

### P1-3 显示 `path:line`，点击却只打开文件顶端

`module_report.py:95-104` 的链接标签包含 `path:line`，但 `module_locator.py:400-413` 生成的 `source_uri` 只有文件 URI，没有行范围或片段。DeepWiki-Open 的基准实现会用真实 snippet 重新定位 citation 行号（`api/services/codemap.py:178-222,305-309`）；SourceBridge 的 Code Tour 也以 `file_path + line_start + line_end` 为 stop 合同，并对不存在路径做过滤（`workers/knowledge/code_tour.py:37-49,128-180`）。当前点击行为不能带用户到“这个模块怎么实现”的具体代码。

必须修复：为 symbol/relationship/step 保存 `line_start/line_end` 和内容 hash；提供受控本地 code viewer URL 或平台可识别的 line fragment。链接标签和实际落点必须一致，并在源码变化时通过 hash/freshness gate 拒绝陈旧详情。

### P1-4 六个参考项目只停留在文档声明，没有落实到该模块的关键机制

`IMPLEMENTATION-REFERENCE-AUDIT.md` 声称该功能参考 CodeBoarding component/cluster、SourceBridge graph/Code Tour、Understand Anything tour/graph、DeepWiki Codemap/CodeViewer；但 `module_locator.py` 和 `module_report.py` 中没有 component clustering、topological tour、citation grounding、question-focused retrieval 或 composite codemap 数据结构。

机制对照：

| 参考项目 | 应参考的具体机制 | 当前落实情况 |
|---|---|---|
| SourceBridge | Code Tour 的文件+行范围合同、真实路径过滤、evidence gate（`workers/knowledge/code_tour.py:37-49,128-180`） | 只有文件 URI；无行级 grounding、内容证据门或 hallucination path gate。 |
| PocketFlow | `FetchRepo → IdentifyAbstractions → AnalyzeRelationships → OrderChapters → WriteChapters → CombineTutorial`（`flow.py:12-32`；`nodes.py:84,240,410,537,753`） | 没有“能力抽象→相关文件→关系→阅读顺序”；根目录 tutorial 甚至 not_found。 |
| OpenWiki | 确定性页面节点、links/backlinks 和安全树遍历（`src/visualize/graph.ts:37-129,245-330`） | 有粗粒度三桶关系，但 resolver 漏真实 inbound；没有稳定的功能节点与 backlinks 视图。 |
| Understand Anything | 对知识图做拓扑排序、处理 cycle/isolated node、按 layer 组成 tour（`tour-generator.ts:122-299`） | 没有图拓扑阅读路径或 layer；步骤是固定角色顺序。 |
| CodeBoarding | LSP document symbols/references、definition/reference 两种建边、class hierarchy、cluster/component（`static_analyzer/engine/call_graph_builder.py:24-134`；`hierarchy_builder.py:20-111`） | 继续依赖自身轻量 analyzer；没有 LSP adapter、cluster 或组件边界置信度。 |
| DeepWiki-Open | 问题驱动 RAG、skeleton→enrich、router/service/schema/UI 的结构化 Codemap、snippet 反查真实行号（`api/services/codemap.py:201-311`） | 仅按字符串给目录打分；不能形成跨目录功能面，也无 snippet grounding。 |

因此本模块的六仓参考完整度应判为：**低，行为模式仅有少量“本地链接 + 关系分组”相似，核心机制 6/6 均未完整落地**。

## P2 — 次要但应补齐

### P2-1 file URI 校验只检查字符串前缀

`module_report.py:30-37` 只接受 `startswith("file://")`，因此手工构造的 `file://remote-host/...` 也会成为链接。CLI 正常路径由 `_source_uri()` 生成且有根目录包含检查，所以当前默认链路风险较低；但 `render_module_report()` 是公开函数并接受任意 result。

建议：用 URL parser 要求 scheme=file、authority 为空/localhost，并在 renderer 端再次确认规范化路径位于 result project root。对无效链接渲染为纯文本。

### P2-2 CLI 对 `candidate/not_found` 仍返回成功且查询 slug 可碰撞

`cli.py:282-296` 无论 resolution 是 exact、candidate 还是 not_found 都返回 0；自动化调用方无法仅靠退出码区分“生成了报告”和“找到了功能”。`_report_slug()` 又会让不同查询折叠到相同 80 字符 slug，后一次静默覆盖前一次。

建议：保持“报告生成成功”退出 0 也可以，但必须提供 `--require-verified` 或稳定 machine status；输出文件名追加 query hash，manifest 记录原始 query，避免覆盖。

### P2-3 缺少六仓回归基线与质量指标

没有定位 precision@k、生产目录优先率、测试关联 precision、resolved edge ratio、line-link validity 或真实功能 surface recall。当前“测试通过”不能说明技术选型报告可靠。

至少新增以下 golden cases：

1. SourceBridge `knowledge`：返回一个分层 capability surface，并正确区分 `internal/knowledge` 与 `workers/knowledge` 职责及各自测试。
2. PocketFlow `tutorial`：命中根目录 `main.py/flow.py/nodes.py`；`docs/FastAPI` 不得被称为实现模块。
3. OpenWiki `visualize`：生产模块优先、测试目录折叠为证据、识别 `src/cli/runners.ts → src/visualize/server.ts`。
4. Understand Anything `viewer`：产品 package 与测试关联，不得因测试镜像产生功能歧义。
5. CodeBoarding `static_analyzer`：产品模块唯一，测试目录作为 evidence，并验证真实 LSP/graph 核心文件进入实现链。
6. DeepWiki `codemap`：一个跨层 surface 包含 router/service/schema/frontend/WebSocket，service 是主要实现，不是 schema 排第一。

## 已通过的部分

- `locate_modules()` 对空 query、非法 limit、非 dict index 会 fail closed。
- 合成仓库中唯一 `src/acp` 能输出目录、文件、符号、关系和测试字段。
- 多个同名目录不会错误标为唯一 exact；问题是当前把测试镜像也当成同级功能模块。
- HTML 对文本做 escaping；`javascript:` 不会成为 href。
- 卡片到详情的 `#module-NNN` 导航、搜索过滤、响应式 CSS 和本地文件 URI 基础链路可用。
- CLI 每次调用会重建或兼容性复用当前 source index，`build_index()` 的源码稳定性检查为该模块提供了基本新鲜度保障。

## 复审通过标准

下一轮不能只补 synthetic test；必须同时满足：

1. 上述 6 个真实仓库 golden case 全部通过，报告保存探针 JSON 摘要。
2. `exact` 不再等同于名称唯一；文档/测试/生成目录不会被称为已确定实现。
3. 支持 directory、file、symbol 和跨目录 composite capability surface。
4. 测试证据没有纯名称推断；关系来源和 confidence 在 HTML 可见。
5. 实现步骤来自可追溯关系图，或明确降级为“启发式阅读建议”；所有行为性文字都有源码证据。
6. 核心符号、依赖和测试均可点击到真实文件与行范围，且有 freshness/hash 验证。
7. 六仓参考矩阵更新为具体“已采用机制 + 本地文件 + 测试”；本模块的独立复审结果为 PASS。

在这些条件满足前，本模块可作为**探索性目录导航原型**使用，不应作为生产技术选型、复用安全判断或“功能底层实现已确定”的依据。
