# 命名功能 / ACP → 模块实现详情：第二次独立复审

- 复审日期：2026-08-10
- 复审对象：`src/repo_teacher/module_locator.py`、`src/repo_teacher/module_report.py`、CLI `explain`、对应测试
- 对照材料：`module-locator-audit.md`、`module-locator-fix-reference.md`
- 复审方式：代码审查、专项测试、完整测试、六个完整 clone 重新索引与真实查询重放、HTML 链接安全探针
- 约束：本复审未修改产品代码

## 最终判定

**REQUEST CHANGES**

本轮已经从“目录名搜索原型”提升为可用的、证据分级清楚的候选实现面导航器。旧审计的三个 P0 均已关闭：名称精确命中不会再冒充能力已验证；功能可以由多个 directory/file/root-file slices 组成；测试的已解析静态关联与目录结构候选已拆开。

但严格的六仓 golden 仍只有 **5/6**。OpenWiki 源码中明确存在 `src/cli/runners.ts → src/visualize/server.ts` 的 import/call，当前索引却把 import 留在 unresolved，导致报告把 `runners.ts` 显示为孤立组件，也不能在“已解析实现链”中证明 CLI 如何进入可视化服务器。这个关系正是上一轮验收标准点名要求的真实链路，因此不能以“两个路径已被硬编码进 source-audited slices”为由判作完全通过。

通过率必须分开理解：

- 预期 source slices 定位：**6/6（100%）**；
- 严格 golden（包含点名关键关系）：**5/6（83.3%）**；
- `verified_capability_surface=true`：**0/6**，这是正确的保守语义，不是缺陷；
- 当前重建索引有效性：**6/6 均为 0 errors**；
- 专项测试：**20/20 通过**；
- 全量测试：**115/116 通过**，唯一失败为复审范围外的 SSH remote 清洗回归。

## 六个完整仓库的真实重放

本次没有把旧的 `examples/reference-selection/projects/*/index.json` 当作可信基线：它们当前都无法通过 `validate_index()`，分别包含重复 ID 等旧格式问题。复审直接对 `/Volumes/T7/workspace/ontology/graph/repo/*` 的六个完整 clone 调用当前 `build_index()`，验证新索引为 0 errors 后，再调用 `locate_modules()`。

| 仓库 / 查询 | 实际定位 | 关系质量 | 测试关联 | 结论 |
|---|---|---:|---:|---|
| PocketFlow / `tutorial` | `main.py + flow.py + nodes.py`；根目录能力；28 符号 | resolved ratio 18.3%；trace 18；1 component | 已解析 0 / 结构候选 0 | **PASS**：根目录功能与阶段链均进入报告；docs 未混入 |
| DeepWiki / `codemap` | service、router、schema、Ask、CodeMap、CodeViewer、WebSocket 共 7 slices；primary 为 service | 37.2%；trace 26；5 components | 0 / 0 | **PASS（有边界）**：跨层 surface 正确；前端多数仍为诚实的 isolated slices |
| SourceBridge / `knowledge` | domain store、knowledge workers、admin presentation；39 文件 | 44.2%；trace 40；11 components | 已解析 42 / 结构候选 0 | **PASS**：跨目录职责与真实测试静态关联可见 |
| OpenWiki / `visualize` | `src/visualize + src/cli/runners.ts`；6 文件 | 72.2%；trace 5；2 components | 已解析 0 / 结构候选 5 | **FAIL**：surface 正确，但 CLI→server 关键边仍未解析 |
| Understand Anything / `viewer` | viewer package；3 文件 | 50.0%；trace 0；3 isolated components | 已解析 0 / 结构候选 1 | **PASS（诚实降级）**：没有伪造 trace，测试镜像只列结构候选 |
| CodeBoarding / `static_analyzer` | 唯一产品目录；48 文件 | 65.2%；trace 40；1 component | 已解析 68 / 结构候选 4 | **PASS**：产品/测试镜像分离，LSP/graph 核心文件均在实现面内 |

六份当前重建索引均通过 `validate_index()`。六个结果的 top core symbols 全部具备通过当前文件哈希验证的 source location：PocketFlow 24/24、DeepWiki 24/24、SourceBridge 24/24、OpenWiki 24/24、Understand Anything 11/11、CodeBoarding 24/24。

## P0

**无。**

上一轮 P0 已有可重复证据证明关闭：

1. `locate_modules()` 将唯一同名生产目录标为 `exact_name_match`，同时把 `is_exact` 和 `verified_capability_surface` 固定为 false；摘要也明确要求人工结合源码链确认（`module_locator.py:993-999,1040-1049,1107-1115`）。
2. `_REFERENCE_SURFACES` 和 generic slices 都能构成 directory/file/root-file 的组合实现面；实际 PocketFlow 与 DeepWiki 分别证明根目录和跨前后端 surface（`module_locator.py:81-158,236-284,908-990`）。
3. 产品文件入口统一经过 `_is_product_source()`；docs/tests/examples/generated/build 等辅助区域不会成为产品 slice（`module_locator.py:206-228,926-948`）。
4. 测试只在 resolved inbound 时进入 `tests`；嵌套或镜像规则进入 `possible_tests`，并带 `structural-association-only`，不再使用纯名称作为测试证据（`module_locator.py:785-824`）。

## P1

### P1-1 OpenWiki 点名关键关系仍未进入 confirmed implementation trace

真实源码证据：

- `repo/openwiki/src/cli/runners.ts:33` 导入 `runVisualizeServer`；
- `repo/openwiki/src/cli/runners.ts:70` 调用 `runVisualizeServer(...)`；
- `repo/openwiki/src/visualize/server.ts:66` 定义该函数。

当前重建索引把 `../visualize/server.js` 记录为 unresolved。`locate_modules()` 因此只在 source-audited slices 中同时列出两个路径，`component_boundaries` 仍为两个组件，`implementation_trace` 也没有 `runners.ts → server.ts`。实际报告一边显示参考机制包含 “CLI caller”，另一边没有 confirmed edge 支撑这条箭头。

这是 TypeScript/ESM 常见的源码扩展名映射问题：源码 import 使用 `.js`，仓库实现文件是 `.ts`。修复应在解析/关系解析层支持 `.js → .ts/.tsx` 的受控候选解析，并新增真实仓 assertion：

```text
source.path == "src/cli/runners.ts"
target.path == "src/visualize/server.ts"
kind in {import, calls}
resolved == true
```

模块定位器不应伪造该边；但在上游 resolver 修复并由本模块真实 golden 验证前，“六仓关键实现链全部通过”不能成立。

## P2

### P2-1 CLI 的 `--limit` 合同与真实行为不一致

CLI 把 `--limit` 描述成“Maximum candidate modules”，但 `locate_modules()` 当前总是返回 0 或 1 个 capability surface，`limit` 实际用于截断 `slices[:max(limit * 12, 12)]`（`cli.py:75-80`；`module_locator.py:1074-1097`）。这不会破坏当前报告，但机器接口语义不准确；应改名为 slice budget，或者真正实现多个候选 surface 的 ranking/limit。

### P2-2 `not_found` 与文件名碰撞仍缺少稳定机器合同

`explain` 对 `not_found/candidate/exact_name_match` 都返回 0，自动化调用只能再读取 JSON；不同查询经 `_report_slug()` 截断/归一化后仍可能覆盖同一文件（`cli.py:235-240,267-301`）。建议增加 `--require-match` 或明确 status exit contract，并在文件名加入短 query hash。

### P2-3 freshness 是“生成时”校验，不是静态 HTML 查看时校验

`_source_excerpt()` 会在生成结果时重新计算完整文件哈希，只有与索引一致才写入 snippet、line range 和 `fresh=true`（`module_locator.py:314-386`）。这是有效的生成时 gate。HTML 本身是静态文件；报告生成后源码再变化时，页面不能自动把旧 snippet 改为 stale。页面文案“源码变化时拒绝展示陈旧片段”应限定为“生成报告时”，或由本地 viewer 在打开时再验证 hash。

### P2-4 详情页仍偏密集

HTML 已经具备“hero → 结论 → 候选卡片 → 8 个分节 → 使用约束”的总分总结构，卡片与详情锚点也可点击；关系组和全部文件默认折叠。真实 CodeBoarding 页面仍会直接展开约 40 条 trace 和大量片段。为了满足“先看重点”的产品目标，建议默认只展开 5–8 条代表 trace，其余放入 `<details>`，并在首屏显示“入口→核心→外部依赖”的三段摘要。

## 已通过的语义与安全检查

### exact name 不冒充 capability verified

- JSON 同时保留 `is_exact_name_match=true` 与 `verified_capability_surface=false`；
- HTML 标题为“唯一产品目录名称精确命中（功能未验证）”；
- 卡片置信度表述为“源码候选”，不是“功能已确认”；
- 参考仓库身份和 capability verification 是两件事：即使 remote/commit/source bundle 身份通过，surface 仍为 candidate。

### confirmed relationships 与 heuristic reading order 分离

- `implementation_trace` 只消费 resolved internal 的 calls/import/references/inherits/implements，并标注 `resolved-graph-topology` 或 `cycle-fallback`（`module_locator.py:544-609`）；
- `reading_order` 明确使用 `kind=heuristic_reading_order`、`confidence=heuristic`，文案说明不是运行时或数据流顺序（`module_locator.py:496-541`）；
- unresolved 单列诊断，不计入 dependency conclusion（`module_locator.py:716-741,890-904`）；
- HTML 将 trace、heuristic reading 和四类关系分成独立章节（`module_report.py:331-356`）。

### 测试 evidence 置信度

- `tests` 展示 `association=resolved-relationship`、原 relationship confidence、target 与 `resolved-static-link`；
- `possible_tests` 展示 `explicit-subpath/mirrored-test-path`、medium、`structural-association-only`；
- HTML 标题明确“测试关联，不等于测试覆盖”，两组分栏展示 association/confidence/evidence status。

### line / snippet / hash / URI

- symbol 和 relationship 两端都保存 `path/line_start/line_end/snippet/snippet_sha256/file_sha256/fresh`；
- file URI 生成时限制在 project root，renderer 再解析 scheme/authority、解码并验证 root containment（`module_locator.py:167-187,314-386`；`module_report.py:43-76`）；
- 六仓渲染探针共检查数百个链接，没有发现非 `file:`、remote authority 或越过 project root 的 href；
- 卡片 `href="#module-001"` 与详情 `id="module-001"` 成对存在，source links 可点击；
- 链接只打开文件顶部，页面明确说明行号由报告内 snippet/hash 锚定，没有假装支持编辑器行跳转。

## 六仓参考机制的实际采用程度

| 参考仓 | 本地已采用 | 仍未采用 / 未证明 | 评价 |
|---|---|---|---|
| SourceBridge | 文件+行范围、真实路径限制、hash freshness gate | 没有其完整 Code Tour 质量门与模型生成层 | **核心证据合同已采用** |
| PocketFlow | slices → relations → topological trace → render 的阶段化管线 | 不生成抽象章节和 LLM 教程 | **结构流程已采用** |
| OpenWiki | stable IDs、internal/inbound/outbound、root-safe file URI | 真实 CLI→server 边未解析；无交互 graph | **部分采用，关键 golden 未闭环** |
| Understand Anything | Kahn-style topology、cycle fallback、isolated nodes | 未采用 ontology layer/tour 产品模型 | **算法思想已采用** |
| CodeBoarding | symbol relationship graph、connected components | 未嵌入 LSP lifecycle、hierarchy、Leiden clustering | **轻量替代，不是完整复用** |
| DeepWiki | 多切片 Codemap surface、真实 snippet grounding | 无问题驱动 RAG、skeleton→enrich；跨前后端边多为孤立 | **数据合同部分采用** |

整体参考程度可评为：**六个项目均有明确、可定位的机制映射，但只有证据合同、拓扑排序和轻量 component 三类进入了本地执行路径；LSP、RAG/LLM enrichment、交互图和完整 Code Tour 没有被实现。** 这与 `module-locator-fix-reference.md` 声明的差异基本一致，没有发现把未采用机制伪装成已完整复用的代码字段；OpenWiki 的点名链路是当前唯一阻塞严格 PASS 的真实 golden。

## 测试与命令证据

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_module_locator tests.test_module_report tests.test_cli -v
=> 20 tests, OK

PYTHONPATH=src python3 -m unittest discover -s tests -v
=> 116 tests; 115 passed; 1 failed
=> 失败：test_models.ModelsTest.test_remote_credentials_and_query_are_never_persisted
=> 原因：_sanitize_remote("git@github.com:...") 错误去掉 git@；与本模块无关，但全仓尚非绿灯

repo_teacher explain <openwiki> visualize --output <temp>
=> composite_candidate
repo_teacher validate <temp>/index.json
=> PASS (0 errors, 0 warnings)
```

## 下一轮 PASS 条件

1. 当前索引器能解析 OpenWiki `runners.ts → visualize/server.ts` 的真实 import，模块报告出现 confirmed edge，两个文件不再因解析器缺口被拆成孤立 component。
2. 增加一条直接对完整固定 commit 或最小忠实 `.js specifier → .ts implementation` fixture 的回归测试；断言 target path、relationship kind、resolved 状态与 trace，而不是只断言 slices。
3. 重新生成持久化的六仓 reference-selection 索引，使 `validate_index()` 六份全部通过；不要继续把旧的重复-ID产物作为审计证据。
4. 全仓测试恢复 100% 通过。SSH remote 清洗失败不属于本模块，但“生产级整体完成”不能在测试红灯下声明。

完成以上第 1–2 项后，本模块可以进行第三次独立复审；第 3–4 项属于发布/全仓完成门。
