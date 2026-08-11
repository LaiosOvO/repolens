# 命名功能 / 模块定位：独立复审（Round 3）

- 日期：2026-08-10
- 范围：命名功能定位、模块详情 HTML、`explain` CLI、TypeScript import resolver、索引验证及对应测试
- 基线：SourceBridge、OpenWiki、Understand Anything、CodeBoarding、DeepWiki-Open、PocketFlow Code2Tutorial 六个完整本地 clone
- 约束：只读复审；未修改产品代码或正式 examples
- 最终判定：**REQUEST CHANGES**
- Architecture gate：**BLOCKED**（专用 architect Agent 因固定模型不可用未返回证据；此外已有可复现的错误解析边）

## 结论先行

Round 2 点名的两个发布阻断已真实关闭：六仓冷重建的严格 surface golden 为 **6/6**，六仓 validator 均为 0 errors（SourceBridge 仅保留允许的 dirty-worktree warning）；OpenWiki `runners.ts → visualize/server.ts` 确实进入 resolved trace 并合并为一个 component。六份现场 HTML 在真实 Chrome 的 `390×844` 与 `1440×900` 下均无页面级横向溢出，且没有通过 `html/body overflow:hidden` 或 `clip` 掩盖问题。

但本轮独立复审发现一个会直接污染模块定位结果的 P1：TypeScript 相对 import resolver 会把 `.css/.json/.node` 等非 JavaScript specifier 错误改写为同名 `.ts` 文件。错误边能够通过当前 validator，并进入 `implementation_trace` 和 `component_boundaries`。因此“受控 `.js → .ts/.tsx`”合同尚未成立，不能判生产 PASS。

同时发现上游 validator 没有把 feature evidence 绑定到 feature 自身的 entrypoint/symbol/source。该问题不改变本轮六仓 locator 结果，但使“validator 通过即可证明功能声明有证据”这一发布门不可信，也应在下一轮一并关闭。

## P1 — 发布阻断

### P1-1 TypeScript resolver 会把非 JS import 错连到同名 TypeScript 文件

位置：`src/repo_teacher/indexer.py:716-749`。

当前逻辑对任意显式后缀先取 stem，再尝试 `.ts/.tsx/.js/.jsx/index.*`。这不只处理源码常见的 emitted `.js` specifier。

独立最小复现：

```text
src/acp/main.ts   -> import "./theme.css"
src/acp/theme.css -> real stylesheet
src/acp/theme.ts  -> unrelated TypeScript module
```

现场结果：

```text
relationship.target_name = ./theme.css
relationship.target_path = src/acp/theme.ts
validate_index            = valid=true, errors=0
locator trace             = src/acp/main.ts -> src/acp/theme.ts
```

同类 `.json`、`.node` 和资源扩展名也会发生错误替换。由于 locator 只把 resolved internal edge 放入实现链，这个错误会把无关文件合并到同一 component，属于功能解释错误而非单纯诊断噪声。

修复门：

1. 只有 extensionless 或明确允许的 JS-family suffix 才能参与 TypeScript source substitution；
2. `.css/.json/.node`、图片、字体等 specifier 必须保持 unresolved，除非存在该资源类型的专用 resolver；
3. 增加负向 resolver 测试，并断言错误边不能进入 locator trace/component；
4. 保持真实 OpenWiki `.js → .ts` positive golden。

### P1-2 feature evidence 没有绑定 claimed feature

位置：`src/repo_teacher/validation.py:66-98`、`src/repo_teacher/validation.py:454-464`。

`_confidence_supported()` 只要求 feature 引用的某条 evidence 具有允许的 kind/analyzer；它没有验证该 evidence 是否对应 feature 的 `entry_symbol_id`、entrypoint、source path 或声明位置。

独立重放中，修改已有 feature 的 title、entrypoint、source，清空 `entry_symbol_id`，保留原 evidence 并重算完整性 checksum 后，`validate_index()` 仍返回 `valid=true, errors=0`。这说明 checksum 能检测意外损坏，但当前语义门不能拒绝重新签入的伪功能声明。

该缺陷不影响本轮 locator 使用的 files/symbols/relationships，因此不否定下面的六仓定位数据；但它否定了“完整 index validator 已证明 feature 声明受证据约束”的发布结论。

修复门：把允许的 exact/static evidence 与 feature 的 symbol/path/range 做结构绑定；需要 symbol 的 confidence 合同不得接受空 `entry_symbol_id`；加入 rehashed mutation regression。

## P2 — 自动化与持久化缺口

1. `tests/test_module_locator.py:167-291` 的六仓 golden 是合成目录，不是六个完整 clone 的 CI gate。OpenWiki fixture 还是 extensionless import；`tests/test_indexer.py:694-715` 只断言 resolver target，没有断言真实 `.js → .ts` 边进入 locator trace 并把 component 合并为一个。
2. `tests/test_module_report.py:98-101` 在 Playwright/Chrome 缺失时会 skip；`tests/test_module_report.py:263-286` 虽检查页面宽度，但没有禁止 `html/body overflow-x:hidden|clip`。当前产品 CSS 与本轮真实浏览器检查均通过，但 CI 合同仍允许将来用裁剪伪通过。
3. `src/repo_teacher/cli.py:237-243` 的 `_report_slug()` 会让不同查询覆盖同一 HTML/JSON，例如 `a+b` 与 `a b`、`ACP protocol` 与 `ACP-protocol`，以及前 80 个归一化字符相同的长查询。建议 slug 追加完整 query 的短哈希并增加碰撞回归。

## 六仓完整冷重建结果

本轮没有复用正式 examples 或上一轮 JSON；直接对六个完整 clone 调用当前 `build_index()`，随后执行 `validate_index()`、`locate_modules()` 和 `render_module_report()`。

| 仓库 / 查询 | validate | slices | files | trace / components | tests（resolved / structural） | golden |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge / `knowledge` | 0 errors / 1 dirty warning | 3 | 39 | 40 / 10 | 42 / 0 | PASS |
| OpenWiki / `visualize` | 0 / 0 | 2 | 6 | 6 / 1 | 5 / 1 | PASS |
| Understand Anything / `viewer` | 0 / 0 | 1 | 3 | 0 / 3 isolated | 0 / 1 | PASS（诚实降级） |
| CodeBoarding / `static_analyzer` | 0 / 0 | 1 | 48 | 40 / 1 | 68 / 4 | PASS |
| DeepWiki-Open / `codemap` | 0 / 0 | 7 | 7 | 28 / 3 | 0 / 0 | PASS |
| PocketFlow / `tutorial` | 0 / 0 | 3 | 3 | 18 / 1 | 0 / 0 | PASS |

六仓均继续输出 `verified_capability_surface=false`。参考仓身份验证成功时才出现 `reference_alignment`；同名或只有部分路径形状的未验证仓库不会被提升为 source-audited alignment。

### OpenWiki 点名链

- 真实 import：`src/cli/runners.ts` 的 `../visualize/server.js`；
- resolved target：`src/visualize/server.ts`；
- locator trace：`runners.ts → server.ts`，ordering 为 `resolved-graph-topology`；
- 六个产品文件组成一个 `resolved-edge-component`。

## Fail-safe、源码与 URI/anchor 复验

- 真实 PocketFlow 上的 `docs`、`FastAPI`、`.` 和不存在名称均为 `not_found`，没有产品 module；
- 重复产品 basename、辅助目录排除、模糊文件候选和目录同名不升格由专项测试继续覆盖；
- 六仓所有抽样/递归收集的 `source_uri` 均为无 authority 的 `file:` URI，位于对应 project root 内且目标存在；
- 所有展示 snippet 都通过当前文件 SHA-256 freshness gate，非 fresh 位置不展示旧片段；
- 六仓内部 `#module-*`/回链均有真实目标，broken anchor 为 0；
- 源码链接打开文件，报告中的 `path:line` 由 fresh snippet 与 snippet/file SHA-256 锚定，不伪装成编辑器行跳转；
- resolved internal/inbound/outbound 与 unresolved 分桶仍然独立，unresolved 不进入依赖结论。

## 真实 Chrome 页面检查

现场 HTML：

```text
/var/folders/ky/jm76nfgj4js_yjwfjn7fn88h0000gn/T/repo-teacher-module-reaudit-r3-fmtgwc4j
```

| 仓库 | 390px document/body | 1440px document/body | file links | line links | mobile long pre / local scroll | broken anchors |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge | 390 / 390 | 1440 / 1440 | 450 | 314 | 100 / 100 | 0 |
| OpenWiki | 390 / 390 | 1440 / 1440 | 184 | 157 | 30 / 30 | 0 |
| Understand Anything | 390 / 390 | 1440 / 1440 | 55 | 44 | 1 / 1 | 0 |
| CodeBoarding | 390 / 390 | 1440 / 1440 | 489 | 314 | 86 / 86 | 0 |
| DeepWiki-Open | 390 / 390 | 1440 / 1440 | 262 | 232 | 63 / 63 | 0 |
| PocketFlow | 390 / 390 | 1440 / 1440 | 181 | 168 | 41 / 41 | 0 |

逐页 computed style 均满足 `html/body overflow-x=visible`，CSS 中不存在针对 `html/body` 的 `overflow:hidden|clip`。`.source-excerpt` 的 `overflow:hidden` 只裁切圆角容器边界；每个 `<pre>` 都保持 `overflow-x:auto`，所有超长代码的 `scrollWidth > clientWidth` 且滚动发生在 `<pre>` 内，因此没有依靠父级隐藏来伪造页面宽度。

## 测试与工具证据

```text
专项：module locator + module report + CLI + TS resolver
=> 22 tests, OK

全仓：python3 -m unittest discover -s tests -v
=> 202 tests, OK（97.939s）

ruff check src tests
=> All checks passed!

python3 -m compileall -q src tests
=> exit 0
```

全绿测试不能覆盖上面的负向 import 和语义绑定反例，因此不能覆盖 P1。

## 独立审查说明

专用 `code-reviewer` 与 `architect` 角色因当前账户不支持其固定模型而未能启动。随后启动的独立通用 code-review lane 完成了完整复核并返回 **REQUEST CHANGES**；architect lane 因共享线程槽已满未能补跑。按照代码审查门，缺失 architect 证据本身不允许给出 APPROVE；本报告同时已有两个可复现的 HIGH finding，因此最终判定不依赖该基础设施降级。

## 下一轮 PASS 条件

1. 限定 TypeScript source substitution 的后缀合同，并让 CSS/JSON/native/assets 负例保持 unresolved；
2. 负例不得进入 locator trace 或 component，真实 OpenWiki `.js → .ts` 正例必须继续通过；
3. feature evidence 与 claimed feature 做结构绑定，rehashed mutation 被 validator 拒绝；
4. 将六完整仓 cold build/validate/surface/OpenWiki chain/URI/anchors 变成可执行 integration gate；
5. 浏览器 gate 明确禁止 `html/body overflow:hidden|clip`，且 release profile 不得静默 skip；
6. 修复 query slug 碰撞，防止不同 explain 查询静默覆盖。

在上述 P1 关闭前，本模块的六仓正向行为和移动端展示可以使用，但不能标记为“生产级完成”。
