# 命名功能 / 模块定位：独立复审（Round 4）

- 日期：2026-08-10
- 复审对象：`docs/audits/module-locator-reaudit-round3.md` 中两个 P1 阻断的 Round 3 修复候选
- 基线：当前工作树，以及 `/Volumes/T7/workspace/ontology/graph/repo` 下六个完整固定版本 clone
- 约束：独立只读复审；未修改产品、测试或正式 examples
- **模块范围判定：PASS**
- **仓库集成门：BLOCKED BY CORE SCANNER**（范围外、稳定复现；见“全量门”）

## 结论先行

Round 3 的两个模块级发布阻断已经真实关闭：

1. JS/TS 相对 import 只对 extensionless 和 emitted JavaScript family（`.js/.jsx/.mjs/.cjs`）执行 TypeScript source substitution。独立反例中的 `.css/.json/.svg` 全部保持 unresolved，没有把同 stem 的 `theme.ts` 放进实现 trace 或同一个 resolved-edge component；extensionless 与 `.js -> .ts` 正例继续成立。
2. feature validator 已把声明、入口证据、首步、符号、固定 manifest 和当前 Git 身份闭合。静态与 curated feature 各 10 类“篡改后重算 `integrity_sha256`”攻击均被拒绝，并都产生 `feature-claim-mismatch`。未知 feature source fail closed。

六个真实仓库的冷构建、validator、命名模块 golden 与 19 个 curated capability 全部通过；OpenWiki 的真实 `runners.ts -> server.ts` 仍为 confirmed resolved edge。390/1440 真浏览器门、52 项专项、Ruff 与 compileall 通过。

不能同时宣称“当前整个仓库测试全绿”：全量 214 项中有一个与本模块无关的 core scanner 异常，且隔离重跑稳定失败。本报告因此将模块修复判为 **PASS**，将整仓集成/发布门明确标记为 **BLOCKED BY CORE SCANNER**，不把范围外回归误算为 module/core 修复失败，也不误报整仓可发布。

## 阻断 1：JS/TS 相对 import 合同

审查位置：`src/repo_teacher/indexer.py:711-766`。

### 独立多后缀反例

在临时仓库中建立：

```text
src/acp/main.ts
  import "./theme.css"
  import data from "./theme.json"
  import icon from "./theme.svg"
  import { start } from "./server.js"
  import { view } from "./view"

src/acp/theme.css
src/acp/theme.json
src/acp/theme.svg
src/acp/theme.ts        # 与资源同 stem，但无关
src/acp/server.ts
src/acp/view.tsx
```

独立 cold build 结果：

| specifier | resolver target | 结果 |
|---|---|---|
| `./theme.css` | `None` | PASS |
| `./theme.json` | `None` | PASS |
| `./theme.svg` | `None` | PASS |
| `./server.js` | `src/acp/server.ts` | PASS |
| `./view` | `src/acp/view.tsx` | PASS |

对 `main.ts` 定位时 `implementation_trace=[]`，component 只有 `main.ts`。对整个 `acp` 目录定位时，trace 只有 `main.ts -> server.ts` 与 `main.ts -> view.tsx`；`theme.ts` 是独立 singleton component，不与 `main.ts` 合并。也就是说，真实资源文件是否被目录 surface 展示，不会被错误解释为资源 import 指向同 stem TypeScript 实现。

### 真实 OpenWiki 正例

对固定版本 OpenWiki cold build 后：

- `src/cli/runners.ts:33` 的 `../visualize/server.js` resolved target 为 `src/visualize/server.ts`；
- `validate_index()`：0 errors / 0 warnings；
- `visualize`：2 slices / 6 files / 6 trace / 1 component；
- `runners.ts -> server.ts` 存在于 `implementation_trace`；
- 两个文件位于同一个 resolved-edge component。

结论：**PASS**。负向资产扩展名与正向 emitted-JS 路径同时满足合同。

## 阻断 2：feature claim 与证据闭合

审查位置：`src/repo_teacher/validation.py:143-395`、`src/repo_teacher/validation.py:751-797`。

所有攻击都先复制有效 cold index，修改目标字段，再使用当前 `_integrity_digest()` 重算整个 index checksum，最后调用 `validate_index()`；因此不是只证明 checksum 能发现意外损坏。

### 静态 feature：10/10 拒绝

基线是同时包含 `main.py` 与 `other.py` 的真实 Python entrypoint index。逐项攻击：

| 攻击面 | 结果 |
|---|---|
| stable feature ID | rejected / `feature-claim-mismatch` |
| title | rejected / `feature-claim-mismatch` |
| entrypoint | rejected / `feature-claim-mismatch` |
| unknown source | rejected / `feature-claim-mismatch` |
| summary | rejected / `feature-claim-mismatch` |
| `entry_symbol_id` | rejected / `feature-claim-mismatch` |
| entry evidence path | rejected / `feature-claim-mismatch` |
| entry evidence line | rejected / `feature-claim-mismatch` |
| first-step path | rejected / `feature-claim-mismatch` |
| first-step order | rejected / `feature-claim-mismatch` |

证据 line 篡改还同时触发 stale/dangling/unsupported-confidence 门；核心结论不依赖这些附加错误，因为 claim closure 本身也拒绝了攻击。

### Curated feature：10/10 拒绝

基线是 SourceBridge 固定版本中拥有真实 entry symbol 的 source-audited capability。逐项攻击：

| 攻击面 | 结果 |
|---|---|
| manifest-derived stable ID | rejected / `feature-claim-mismatch` |
| indexed Git commit | rejected / `feature-claim-mismatch` + `commit-drift` |
| indexed Git remote | rejected / `feature-claim-mismatch` |
| indexed Git root | rejected / `feature-claim-mismatch` |
| first audit evidence path | rejected / `feature-claim-mismatch` |
| first audit evidence line | rejected / `feature-claim-mismatch` |
| first direct evidence reference | rejected / `feature-claim-mismatch` |
| feature entry symbol | rejected / `feature-claim-mismatch` |
| first-step symbol | rejected / `feature-claim-mismatch` |
| entry evidence symbol | rejected / `feature-claim-mismatch` |

SourceBridge 当前 worktree 的一个 `dirty-worktree` warning 是可见且允许的非错误状态；所有攻击仍从 `valid=true, errors=0` 的基线出发，并被变为 invalid。

结论：**PASS**。重新签 checksum 不能绕过静态 claim 或固定 manifest/Git/evidence/symbol 合同，未知 producer 也不能进入 feature source 白名单。

## 六仓真实 cold golden

每个仓库均直接调用当前 `build_index()`，没有读取正式 examples 或上一轮持久化 index；随后执行 `validate_index()` 与 `locate_modules()`。

| 仓库 / 查询 | validate | curated | slices | files | trace | components |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge / `knowledge` | 0 errors / 1 dirty warning | 3 | 3 | 39 | 40 | 10 |
| OpenWiki / `visualize` | 0 / 0 | 3 | 2 | 6 | 6 | 1 |
| Understand Anything / `viewer` | 0 / 0 | 3 | 1 | 3 | 0 | 3 |
| CodeBoarding / `static_analyzer` | 0 / 0 | 3 | 1 | 48 | 40 | 1 |
| DeepWiki-Open / `codemap` | 0 / 0 | 5 | 7 | 7 | 28 | 3 |
| PocketFlow Code2Tutorial / `tutorial` | 0 / 0 | 2 | 3 | 3 | 18 | 1 |

结果：validator **6/6 valid**，命名模块 strict golden **6/6**，curated capability **19/19**。`tests.test_reference_ground_truth` 还重新验证了六仓固定 commit、能力职责切片、technology claim 与 closure digest。

## 390 / 1440 可用性门

真实 Playwright + 本机 Chrome 执行：

```text
tests.test_module_report.ModuleReportBrowserTest.
test_long_trace_and_source_excerpt_stay_inside_mobile_and_desktop_viewports
=> PASS
```

两个 viewport 均满足：

- document/body 宽度分别严格等于 390 / 1440；
- module detail 与本地 `file:` source link 存在；
- `path:line` 标签存在；
- 超长源码在 `<pre>` 内局部横向滚动；
- 当前模块报告 CSS 没有给 `html/body` 设置 `overflow-x:hidden|clip`。

## 测试与工具证据

### 目标专项

```text
PYTHONPATH=src python -m unittest -v \
  tests.test_module_locator \
  tests.test_module_report \
  tests.test_indexer \
  tests.test_validation \
  tests.test_reference_ground_truth

=> Ran 52 tests in 110.209s
=> OK
```

上述 52 项包含真实 Chrome 双视口、六仓 fixed-commit ground truth、asset 负例、emitted-JS 正例及两类 feature mutation 回归；本轮另行执行的独立攻击脚本不计入这 52 项。

### 静态质量门

```text
ruff check src tests
=> All checks passed!

python -m compileall -q src tests
=> exit 0
```

### 全量门：范围外稳定阻断

```text
PYTHONPATH=src python -m unittest discover -s tests -v
=> Ran 214 tests in 187.661s
=> FAILED (errors=1)
```

唯一错误：

```text
tests.test_scanner.ScannerTest.test_scan_deadline_and_stat_errors_are_observable
PermissionError: denied
  tests/test_scanner.py:185 failing_stat
  src/repo_teacher/scanner.py:301 source.is_symlink()
```

隔离重跑该单测得到相同错误。测试用 `Path.stat` 模拟文件 stat 失败，而 `source.is_symlink()` 内部通过 `lstat() -> stat(follow_symlinks=False)` 先触发该异常，尚未进入下一行包住 `source.stat()` 的 `try/except`。这不是本轮审查的 resolver、feature validator、locator 或 report 代码，但它使“整仓测试全绿”声明不成立。core fixer 已被通知接管。

## 最终裁决

### 模块范围：PASS

Round 3 点名的两个 P1 均通过独立最小反例、真实 OpenWiki 正例、重新签 checksum 的结构攻击、六仓 cold golden 和专项回归。没有发现新的 module/core 阻断。

### 整仓集成：BLOCKED BY CORE SCANNER

在 scanner 异常修复并重新跑绿全量 214 项之前，不得把当前共享树标记为“整体可发布”。该范围外门禁不反转本报告对 module/core 修复的 PASS，但必须保留为发布集成阻断。

## 未修改范围

本轮只新增本审计报告。未修改：

- `src/repo_teacher/**` 产品代码；
- `tests/**`；
- `examples/**` 与任何正式 SourceBridge 产物；
- 六个参考 clone。
