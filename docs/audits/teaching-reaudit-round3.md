# 教学 / 功能发现第三轮独立复审

日期：2026-08-10  
范围：`features.py`、`capability_catalog.py`、`artifacts.py`、`report.py`、`indexer.py` 接入、独立 Golden fixture 与六个真实参考仓  
结论：**REQUEST CHANGES**  
架构状态：**BLOCK**

## 一句话结论

第三轮修复确实解决了上一轮最严重的仓库身份伪造问题：无 Git 文件副本不能再得到 `source-audited`，六个固定 commit 也能稳定召回 19/19 个清单能力；桌面 HTML 已经是“顶部摘要 → 能力目录 → 逐项解释 → 最后结论”的总分总结构，CodeMap 的已解析关系与建议阅读顺序也在数据和界面上分开了。

但当前仍不能通过生产验收。独立反例证明，只要把 HTTP client 或任意对象命名为 `app` / `program`，普通调用仍会被升级为 `exact-entry` / `static-entry`；所谓“每能力至少两个职责切片”又主要靠通用图遍历或随意追加另一个清单文件凑数，已经把 SourceBridge 的纯测试注入 helper 当成图存储的核心协作实现。技术标签虽有 8 维和显式 `unknown`，59 个已知值却没有逐标签证据。以上三点会直接污染用户最终要做的底层技术选型。

## 审计方法

1. 不采信 `teaching-fix-round2.md` 的完成声明，逐行检查本轮五个产品模块及测试。
2. 对六个完整本地 clone 重新运行生产 `build_index()`，独立统计能力、节点、总边、已解析边和阅读顺序边，并核对每个 resolved edge 的 ID、source 和 target 都存在。
3. 对 19 个能力逐项打印核心/协作切片、关系类型与技术标签，再回看代表性真实源码。
4. 使用未写入现有测试的变形反例重测 HTTP client、任意 `.command()`、JS 除法和仓库身份边界。
5. 重新生成 SourceBridge、OpenWiki、DeepWiki Open 的真实 HTML，用 Chrome/Playwright 在 `1440×1000` 和 `390×844` 检查可见文本、分组顺序、Mermaid 原文与横向溢出。
6. 运行教学专项测试、全量测试、Ruff 和 `compileall`。

## 整改门逐项结果

| 检查项 | 结果 | 独立证据 |
|---|---|---|
| 六仓 19 项能力召回 | **PASS（限固定清单）** | 真实生产链路得到 3+2+3+3+3+5=19/19；六仓扫描均 `complete`。这是固定 commit 的 curated recall，不是任意仓库的通用能力召回。 |
| `docs/tests/examples` 误报 0 | **PARTIAL** | Golden 列举的目录组件命中为 0；但 SourceBridge “内存图数据存储”切片进入明确写着 “purely for tests” 的 `internal/graph/testhelpers.go`，说明语义上的测试代码污染仍存在。 |
| 无 Git 副本不得 `source-audited` | **PASS** | 独立复制 SourceBridge 三个目标文件到临时无 Git 目录，结果 `is_git=False`、`commit=None`、`source_audited=[]`。身份门已要求顶层 Git root、canonical remote、完整 commit 和目标文件哈希。 |
| HTTP client / 任意 command 不得成为入口 | **FAIL** | `app = httpx.Client(); app.get("/private")` → `GET /private exact-entry`；`program = DB(); program.command("vacuum")` → `vacuum exact-entry`；JS 同类分别成为 `static-entry`。见 P0-1。 |
| 错误 Go package 不得成为入口 | **PASS** | `package helper; func main(){}` 未生成确认入口。 |
| JS 除法不能吞掉后续真实路由 | **PASS（已测反例）** | `left/right; router.get("/real", handler)` 能生成 `GET /real static-entry`。 |
| 每能力至少 2 个职责切片 | **FAIL（数量通过，语义失败）** | 19 项都至少 2 个节点，但多项只是 BFS/contains 的前几个目标或“另一个能力文件前 16 行”；SourceBridge 图存储甚至优先选中两个测试 helper。见 P0-2。 |
| 图节点/边真实且 location-only 不冒充执行流 | **PARTIAL** | 30 个 resolved edge ID 全部真实闭合；29 个阅读顺序边也单独标为 `suggested-reading-order`，界面用 `→` / `⇢` 区分。可是 resolved 只代表 calls/contains 等静态结构，不保证切片与能力相关；当前测试没有验证这种语义。 |
| 教程不是 BFS 复制 | **FAIL** | `_tutorial()` 原样复制 feature steps；自动边界来自 `_walk_symbols()` BFS，审计能力同样用 cursor 队列扩展。章节标题与三类缺口只是固定包装。见 P1-1。 |
| CodeMap 显示节点/边且不显示 Mermaid 原文 | **PASS（展示层）** | 三份真实 HTML 的可见 `body.innerText` 均不含 `flowchart LR`；节点与 `→` / `⇢` 边可见，Mermaid 只保留为嵌入数据。 |
| 技术标签逐项证据与显式 unknown | **FAIL** | 152 个维度中 93 个正确显示 unknown；59 个已知值仍只是 `CapabilitySpec.technology` 字符串，没有 `{claim, confidence, evidence_ids}`。独立 fixture 只断言其中 1 个已知值。见 P1-2。 |
| HTML 总分总、重点清楚 | **PARTIAL** | 1440px 桌面版能力优先、重点明确；390px 三份真实报告均横向溢出，文案和详情被裁切。见 P1-4。 |
| Golden 与产品清单独立 | **PARTIAL** | oracle 已移到单独 JSON，测试不再调用产品 `reference_ground_truth()`；但它仍只镜像 commit/path，几乎不校验能力语义、职责切片和技术事实。见 P1-3。 |

## 六仓真实重放结果

以下数字来自本次重新执行当前生产代码，不是引用整改记录：

| 仓库 | 能力召回 | 节点 | 总边 | 已解析静态边 | 建议阅读边 |
|---|---:|---:|---:|---:|---:|
| SourceBridge | 3/3 | 12 | 15 | 9 | 6 |
| PocketFlow Code2Tutorial | 2/2 | 8 | 10 | 6 | 4 |
| OpenWiki | 3/3 | 6 | 3 | 0 | 3 |
| Understand Anything | 3/3 | 6 | 3 | 0 | 3 |
| CodeBoarding | 3/3 | 11 | 12 | 6 | 6 |
| DeepWiki Open | 5/5 | 16 | 16 | 9 | 7 |
| **合计** | **19/19** | **59** | **59** | **30** | **29** |

30 个已解析边全部能在索引关系表中找到，且 source/target 都在对应 CodeMap 节点集合内，闭合错误为 0。`teaching-fix-round2.md` 写的“59 节点 / 55 边 / 24 resolved”已经不是当前代码的事实；Golden 只断言数量大于 0，没有锁定或解释这些变化。

## P0 — 阻塞发布

### P0-1：边界发现仍用变量名冒充对象身份，HTTP client 和任意 command 会被标成确认入口

- 位置：`src/repo_teacher/features.py:47-49,56-90,188-217`
- 原因：Python AST 只提取 attribute receiver 的最后一个名字，JS/TS 只读取词法 receiver；两者都没有验证对象构造、import 来源、decorator context 或框架注册关系。`app` / `program` 在白名单里就被当成服务/CLI。
- 独立反例输出：

```text
app = httpx.Client(); app.get("/private")
  -> http-route GET /private exact-entry

program = DB(); program.command("vacuum")
  -> cli-command vacuum exact-entry

const app = axios.create(); app.post("/upload")
  -> http-route POST /upload static-entry

const program = database; program.command("compact")
  -> cli-command compact static-entry
```

- 现有测试为什么没挡住：`test_client_calls_unrelated_commands...` 只用了 receiver 名 `requests/client/database`，恰好不在白名单；它验证的是名字过滤，不是 client/command 语义。
- 用户影响：30 秒重点、功能数、技术标签和 HTML 目录都会把客户端请求或任意对象方法当作产品入口，且 Python 给出最高的 `exact-entry` 文案。
- 修复门：只在 AST decorator / 明确 router registration、已解析框架实例构造或真实 CLI builder 数据流成立时升级为确认边界；仅凭 receiver 名最多是 candidate。必须把 alias client 和 alias command 反例加入产品测试。

### P0-2：职责切片只验证“关系存在”，不验证“与能力相关”，已产生错误的核心实现讲解

- 位置：`src/repo_teacher/capability_catalog.py:224-345,436-474`
- 原因：
  - `_capability_steps()` 从一个启发式 primary 出发，用 cursor 队列取前几个 outgoing 关系；它不检查目标是否是产品源码、是否符合能力角色，也把 `contains` 与 `calls` 一起当作“协作切片”。
  - 解析不到关系时，为了凑到两个切片，直接取同一 manifest 的另一个能力文件前 16 行，明确没有关系仍命名为“关联能力边界”。
- 真实错误：SourceBridge “内存图数据存储”的四个节点为 `Store`、`Store.InjectSymbolForTest`、`Store.InjectCallEdgesForTest`、`Store.CreateRepository`。前两个协作节点位于 `internal/graph/testhelpers.go:6-32`，源码明确写着“exists purely to keep ... unit tests small”和“production code must use StoreIndexResult / ReplaceIndexResult”。与此同时真正的 `NewStore` 和 `StoreIndexResult` 没进入前四个切片。
- 其他语义缺口：
  - PocketFlow `nodes.py` 的摘要声称覆盖抽象提取、关系分析、章节排序和内容生成，实际只选 `CombineTutorial` 及其 `prep/exec/post`。
  - OpenWiki 三项、Understand Anything 多项和 DeepWiki 两个 UI 能力没有解析符号，只显示目标文件前 16 行，再追加另一个能力文件前 16 行；数量为 2 不等于两个职责。
- 用户影响：这是用户最关心的“每个功能底层怎么实现”。当前页面会用 `source-audited` 和“核心实现/协作切片”强化一个错误阅读路线，直接误导复用和技术选型。
- 修复门：Golden 必须为每项能力独立声明核心符号、允许的协作职责、禁止的测试/文档符号和关键关系；生产代码按这些审计 claims 或语义角色打分，不能用前 N 个 outgoing 边或任意相邻清单文件满足数量门。

## P1 — 生产级缺口

### P1-1：教程仍是 feature graph walk 的展示包装，不是独立教学产物

- 位置：`src/repo_teacher/features.py:369-408`、`capability_catalog.py:274-298`、`artifacts.py:64-149`
- `_walk_symbols()` 是标准队列 BFS；审计能力也用相同 cursor 队列取 outgoing target。
- `_tutorial()` 在第 68 行直接把 `_ordered_steps(feature)` 赋给 `steps`，然后把同一批 step 再映射为 `source_slices`。三类 gaps 对每个能力都是固定句式。
- 已改善之处：文案清楚说明“静态关系不等于运行时”，章节也按“边界—切片—缺口”组织，因此不再冒充执行轨迹。
- 未满足之处：没有从用户问题出发的教学目标、先修概念、职责分组、数据对象、输入输出、失败路径或验证任务；“不是 BFS”的声明与生成机制不一致。

### P1-2：八维标签有 unknown，但没有逐项可追溯证据

- 位置：`src/repo_teacher/capability_catalog.py:32-40,63-166,183-185,485-504`、`report.py:281-307`
- 六仓 19 项共 152 个维度：59 个已知、93 个 unknown。unknown 的处理是正确且诚实的。
- 59 个已知值仍是 manifest 上的字符串，例如 `retrieval:graph-query`、`incremental:ingestion-window`、`evidence:citations`。模型里没有 tag-level claim/evidence/confidence，HTML 也只能笼统地说“来自固定版本源码审计清单”。
- 独立 fixture 仅对 SourceBridge 的 `store:in-memory` 做了一个已知事实断言；其余 58 个已知值没有 Golden oracle。DeepWiki 的 `store:unknown` 只是 unknown 断言。
- 修复门：技术维度改为结构化 claim，并逐项绑定路径、行范围、源码哈希、证据 ID 和审计置信度；无法绑定的必须回退 unknown。Golden 要覆盖每个已知 claim，而不是只检查八个 key 存在。

### P1-3：Golden 已物理独立，但仍是浅层路径镜像，不能证明教学正确

- 位置：`tests/fixtures/reference_capabilities.json`、`tests/test_reference_ground_truth.py:28-152`
- 正面：fixture 是独立文件，测试不再从产品 `REFERENCE_MANIFESTS` 生成期望；真实 clone、commit、工作树 target hash、完整 build、HTML 和无 Git 复制攻击都进入了测试。
- 缺口：fixture 只有 commit、19 个 path 和两个极少量 technology 断言，没有 capability slug/title/summary、核心符号、辅助符号、允许/禁止关系、测试源码排除规则、已知技术证据或预期降级。
- 图只检查 `nodes >= 38`、`edges > 0`、`resolved > 0`，所以 55/24 变成 59/30 仍然绿，测试无法判断新增边是否更好还是更差。
- 修复门：把语义 oracle 放在 fixture：每项能力至少包含核心职责、协作职责、禁止切片、关系语义和逐项技术事实；测试对实际路径和关系做集合级比较，而不是只测全局大于 0。

### P1-4：桌面总分总已改善，但 390px 页面存在严重横向溢出

- 位置：`src/repo_teacher/report.py:570-584`
- 1440px 人工检查：顶部先显示 30 秒重点和能力目录，能力组排在边界/候选前，最后有结论，信息层级明显优于上一版。
- 390px Playwright 实测：

```text
SourceBridge    clientWidth=390, scrollWidth=756
OpenWiki        clientWidth=390, scrollWidth=568
DeepWiki Open   clientWidth=390, scrollWidth=645
```

- 最宽元素是 `.capability-detail-group` / `.feature-card`。内部 grid 子项和长 token 的 min-content 宽度把容器撑开，导致标题、路径、卡片和右侧内容被裁切。
- 修复门：所有 grid/flex 子项设置 `min-width:0`，长 token 使用安全断行，390px 下要求 `documentElement.scrollWidth == clientWidth`；加入浏览器级回归，而不是只检查 HTML 字符串。

### P1-5：target 文件虽已锁哈希，但扩展出来的协作切片没有同等审计绑定

- 位置：`capability_catalog.py:423-425,274-345`
- 每项 capability 只校验 `spec.path` 的固定 SHA-256；随后图遍历可进入任意目标文件，并把新 evidence 的 analyzer 标成 reference-manifest symbol。
- 例如 SourceBridge code tour 会扩到 `workers/knowledge/prompts/code_tour.py` 和 `workers/common/llm/provider.py`，这两个文件不在该 capability 的 hash bundle 中。
- 当前六仓重放时这些关系来自同一 HEAD，且索引稳定性检查有效；残余风险是 dirty worktree 中非 target 协作者可变化，而能力仍保留 `source-audited` 总标签。
- 修复门：能力审计 claim 的所有核心/协作文件都要进 hash-bound closure；dirty 且命中 closure 时降级或拒绝 source-audited。

## P2 — 需要收紧

### P2-1：非产品路径判定只看固定目录/文件模式，漏掉显式测试 helper

- `features.py:41-45,229-240` 不识别 `testhelpers.go`；capability traversal 也没有调用 `_is_product_source()`。
- 当前 Golden 的目录组件检查得到 0，但更严格的语义检查得到一项：`内存图数据存储 -> internal/graph/testhelpers.go`。
- 建议不靠文件名无限扩表，而是结合源码注释、调用方、`IsTest`/测试引用和 curated 禁止列表；至少审计能力不得自动把明显 test-only API 当核心职责。

### P2-2：整改记录中的真实统计已漂移

- `teaching-fix-round2.md` 声称 59 节点 / 55 边 / 24 resolved；本次真实结果是 59 / 59 / 30。
- 这不单是文档数字过期，也说明 Golden 没有对“为什么这些边存在”建立稳定 contract。修复后应由测试产物生成审计统计，避免手写数字。

### P2-3：所有功能详情默认平铺展开，长仓库仍会产生很长页面

- 顶部目录和能力优先级已经解决“首屏找不到重点”的主要问题。
- 但 25 个 feature 的 DeepWiki 报告仍把全部详情一次展开，“最后结论”在所有卡片之后。建议默认只展开推荐能力，其余按能力组折叠；这属于可读性改进，不是本轮架构阻塞项。

## 已确认通过的修复

以下内容本轮没有再打回：

- `source-audited` 的 Git root、canonical remote、完整 commit 和目标文件哈希门有效；无 Git 文件副本攻击失败关闭。
- 错误 Go package 不再成为确认入口；给定 JS 除法反例不再吞掉真实路由。
- 固定清单的 19/19 路径召回稳定，六仓扫描均完成。
- CodeMap 的 resolved/static 与 suggested-reading-order 数据分离，30 个 resolved edge 都闭合；HTML 用不同箭头和说明文字区分。
- 可见页面不显示 Mermaid 原文。
- 八维技术字段完整，未取证项显式显示 unknown。
- 桌面 HTML 已采用摘要优先、能力优先和最后结论的结构。

## 验证结果

教学专项：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_features tests.test_artifacts tests.test_report \
  tests.test_reference_ground_truth -v

Ran 21 tests in 18.432s
OK
```

全量回归：

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v

Ran 159 tests in 73.993s
OK
```

静态检查：

```text
ruff check <教学源码与对应测试>
All checks passed!

python3 -m compileall -q src/repo_teacher tests
```

全绿测试说明当前实现与当前测试一致；P0-1 的 alias 反例、P0-2 的职责语义和移动端 scrollWidth 都不在现有测试 contract 内，所以不能把 159/159 当作生产验收。

## 残余边界

- `capability-cluster` 仍只服务六个固定 commit；其他仓库不会自动获得同等领域能力讲解。
- 静态关系只能说明源码结构，不证明运行时分支、并发、异常或数据生命周期。
- OpenWiki、Understand Anything 和部分 DeepWiki TS/TSX 能力仍因分析器解析不足而只有 location-only 切片。
- SourceBridge 当前工作树有用户保留的未提交变更，页面已正确显示 dirty；目标能力文件本轮仍与固定哈希一致，但 P1-5 的协作闭包风险仍存在。

## 最终裁决

**REQUEST CHANGES / Architecture BLOCK**。

第三轮不是“没有进展”：身份信任边界、固定清单召回、图边类型分离、桌面信息架构和 Mermaid 展示问题都已实质修复。阻塞点已经收敛为三件最核心的事：入口必须验证对象语义而不是变量名，能力切片必须验证职责相关性而不是凑节点数，技术标签必须逐项绑定证据。完成这三项并补上移动端回归和独立语义 Golden 后，才适合再次申请生产级教学/功能发现审计。
