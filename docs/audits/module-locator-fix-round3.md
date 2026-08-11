# 命名功能 / 模块定位阻断修复（Round 3）

- 日期：2026-08-10
- 修复范围：TypeScript 相对 import resolver、feature claim validation、对应回归测试
- 基线：六个完整本地参考仓的 cold `build_index()` / `validate_index()` / 命名模块 golden
- 状态：**修复候选已完成，等待新的独立审计；本文不自判 PASS**

## 结论先行

Round 3 复审报告中的两个 P1 阻断均已形成可执行的修复候选：

1. JS/TS 相对 import 只有在 **无扩展名** 或显式使用 `.js/.jsx/.mjs/.cjs` 时才允许尝试 TypeScript 源码替换；`.css/.json/.svg/.node` 等非 JS 资源不再按 stem 错连到同名 `.ts/.tsx`。
2. validator 不再只检查“feature 引用了某种 evidence”。静态 feature 的 stable ID、title、summary、source、confidence、entry evidence、entry symbol 与首步源码现在必须组成同一个闭合声明；六仓 curated feature 还必须匹配固定 manifest、真实 Git 身份与首个审计 slice。未知 source 一律 fail closed。

修复没有添加 MAC、签名或新的认证宣称。`integrity_sha256` 仍只是不防恶意写入的 checksum；新增门是确定性的结构与当前源码/固定 manifest 交叉验证。

## 修复 1：限制 JS/TS source substitution

位置：`src/repo_teacher/indexer.py:711-766`。

候选集合现在按 specifier 类型拆分：

- extensionless：允许同路径、`.ts/.tsx/.js/.jsx/.mjs/.cjs` 与对应 `index.*`；
- emitted JS family（`.js/.jsx/.mjs/.cjs`）：先尝试原路径，再尝试同 stem 的 `.ts/.tsx`；
- 其他显式扩展名：只尝试原始路径，不进行跨类型替换。

解析仍要求目标是同仓已索引文件，且语言必须是 JavaScript/TypeScript。不存在专用 asset resolver 时，资源 import 保持 unresolved；它不会进入 locator 的 `implementation_trace`，也不会把无关 TS 文件合并进 component。

新增负向门：

```text
src/acp/main.ts  -> import "./theme.css"
src/acp/theme.css
src/acp/theme.ts -> unrelated implementation
```

验证结果：relationship 的 `target_id=None`；`implementation_trace=[]`；`main.ts` 与 `theme.ts` 不属于同一 component。现有 OpenWiki 风格 `server.js -> server.ts` 正向测试继续通过。

## 修复 2：feature claim 与证据闭合

位置：`src/repo_teacher/validation.py:20-399`、`src/repo_teacher/validation.py:751-797`。

### 静态 feature 合同

只接受生成器已知 source `evidence-bounded-static-feature-discovery` 及四种已知 kind：CLI、HTTP、entrypoint、entrypoint candidate。validator 会独立重建并比较：

- `stable_id("feature", kind, entrypoint, entry_evidence.path, entry_evidence.line_start)`；
- entry evidence 的自身 stable ID、kind、confidence、analyzer、path、line 与标准范围；
- exact/static/candidate confidence 与 entry evidence 的一致性；
- `entry_symbol_id == first_step.symbol_id`，且 symbol、step、entry evidence 同文件闭合；
- 按 kind/entrypoint/path/symbol 重建的 title；
- 按 confirmed/candidate、path/line、step 数量和已解析 relationship 数量重建的 summary。

因此只修改 `id/title/entrypoint/source/summary/entry_symbol_id` 中任一字段并重算整个 index checksum，都会得到 `feature-claim-mismatch`。

### Curated source-audited 合同

`source-audited-reference-manifest:<project>@<commit12>` 只有在以下条件同时满足时才接受：

- source 精确匹配六仓已知固定 manifest；
- index 的 `is_git/git_root/commit/remote` 与 manifest 一致；
- 从当前目录重新读取的真实 Git root、origin、HEAD 与源码 bundle 身份为 verified；
- feature ID 可由 `project + capability slug + manifest entry path` 重建；
- kind/confidence/source/entrypoint/title/summary 与对应 manifest spec 完全一致；
- 首个 `capability-source-audited` evidence 精确匹配 contract 的 path/range/analyzer，并与 first step / entry symbol 闭合。

对真实 Understand Anything curated feature 逐项修改上述六个身份/声明字段并重算 checksum，全部被拒绝。真实六仓仍召回并验证 **19/19** curated capabilities。

## 两项阻断探针

定向命令覆盖 asset 负例、emitted JS 正例、静态 feature 篡改和 curated feature 篡改：

```text
4 tests, OK
```

随后运行 locator/indexer/validator 专项：

```text
46 tests, OK
```

其中 asset 负例同时断言 resolver、trace 与 component 三层行为，避免只修 relationship 展示而让错误边继续污染模块边界。

## 六仓 cold build / validate / golden

每个仓都从 `/Volumes/T7/workspace/ontology/graph/repo` 的完整 clone 调用当前 `build_index()`，没有复用正式 example index。

| 仓库 / 查询 | validate | curated | slices | files | trace | components |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge / `knowledge` | 0 errors / 1 dirty warning | 3 | 3 | 39 | 40 | 10 |
| OpenWiki / `visualize` | 0 / 0 | 3 | 2 | 6 | 6 | 1 |
| Understand Anything / `viewer` | 0 / 0 | 3 | 1 | 3 | 0 | 3 |
| CodeBoarding / `static_analyzer` | 0 / 0 | 3 | 1 | 48 | 40 | 1 |
| DeepWiki-Open / `codemap` | 0 / 0 | 5 | 7 | 7 | 28 | 3 |
| PocketFlow / `tutorial` | 0 / 0 | 2 | 3 | 3 | 18 | 1 |

结果：六仓 **6/6** validator 有效；命名模块 slices/files 与 Round 3 复审 golden 一致；curated 合计 **19/19**。OpenWiki 的真实 `src/cli/runners.ts -> src/visualize/server.ts` 仍进入 resolved implementation trace，六个产品文件仍组成一个 component。

另外运行 `tests.test_reference_ground_truth`，六仓固定能力的 66 个职责切片、technology claims 与 closure digest 均保持通过。

## 全量质量门

```text
python -m unittest discover -s tests -v
=> 214 tests, OK (skipped=3), 133.047s

ruff check src tests
=> All checks passed!

python -m compileall -q src tests
=> exit 0
```

三个 skip 是原有、环境可选的真实浏览器用例；本轮未修改 HTML/CSS。Round 3 独立复审已经对六仓 390px/1440px 页面做过真实 Chrome 检查，本修复没有触及报告渲染文件。

## 变更文件

- `src/repo_teacher/indexer.py`：收紧相对 JS/TS import 的扩展名替换合同。
- `src/repo_teacher/validation.py`：加入静态与 curated feature claim 闭合验证；保留 checksum-only 信任边界。
- `tests/test_indexer.py`：新增 asset import 错连反例，并检查 locator trace/component；保留 emitted JS 正例。
- `tests/test_validation.py`：新增静态与 curated rehashed mutation 回归；将 analyzer 测试改为从真实 exact-entry 基线出发。
- `docs/audits/module-locator-fix-round3.md`：记录候选实现与复验证据。

未修改 Go、teaching、Skill export、persistence、comparison、module report、CLI 或正式 examples，也未覆盖并行 Agent 的变更。

## 保留边界与独立复审要求

- 当前验证提高的是本地结构一致性和固定源码交叉验证，不是对任意外部 index 的密码学认证；文案继续明确 checksum-only。
- curated 验证依赖六仓固定 manifest 与真实 Git worktree，未知仓库不会被提升为 source-audited。
- 解析器对 asset 仍是诚实的 unresolved，不声称实现 CSS/JSON/native module 依赖图。
- 本文只证明修复候选与回归结果；是否达到发布 PASS 必须由未参与实现的 Agent 重新执行两项攻击探针与六仓门禁后裁定。
