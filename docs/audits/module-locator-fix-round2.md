# 命名功能 / 模块详情 HTML 移动端溢出修复（Round 2）

- 日期：2026-08-10
- 修复范围：`src/repo_teacher/module_report.py`、`tests/test_module_report.py`
- 复验基线：六个完整本地参考仓的当前索引与现场生成 HTML
- 状态：**修复候选已完成，等待全新独立审计；本文不自判 PASS**

## 结论先行

390px 页面级横向溢出已经从真实六仓的 5/6 降为 **0/6**。修复没有使用 `body/html { overflow-x:hidden }` 掩盖内容，而是约束会保留 intrinsic minimum width 的 grid/flex 子项：实现链右栏允许收缩，路径与符号名可断行，源码片段容器不再撑开父级，`pre` 仍保留自身的横向滚动。

文件链接、`path:line` 标签、模块详情、内部锚点和源码片段均未删除或降级。上游 validator 白名单门也已闭合：SourceBridge 为 0 errors / 1 个 dirty-worktree warning，其余五仓均为 0 errors / 0 warnings。

## 根因与最小修复

第一轮报告指出 trace 与 excerpt 的 intrinsic width 会把页面撑宽。修复后，SourceBridge 仍由超长、不可断的符号名把 `.symbol-list` 从 324px 撑到 545px，因此最终修复覆盖两层根因：

1. grid 列由固定 `1fr` 改为 `minmax(0,1fr)`，关键 grid/flex 子项统一允许收缩；
2. 路径、摘要、标题、符号名使用 `overflow-wrap:anywhere`，符号名额外允许 `word-break:break-word`；
3. `.source-excerpt` 约束在父容器内，`pre` 使用 `width:100%; max-width:100%; overflow-x:auto`；代码自身保持 `width:max-content`，因此长代码只在局部滚动；
4. 移动端的文件、符号和 slice 行改为单列，但保留全部信息与链接。

没有引入依赖、JavaScript workaround 或全页裁剪规则。

## 六仓真实 Chromium 复验

每个仓都用当前 `build_index()` 重新索引，再由当前 `locate_modules()` 与 `render_module_report()` 现场生成 HTML。浏览器为本机 Google Chrome（Playwright 驱动），视口分别为 `390×844` 和 `1440×900`。

| 仓库 / 查询 | 390px page/body | 1440px page/body | 文件链接 | 行号链接 | broken anchors | 移动端内部滚动代码块 |
|---|---:|---:|---:|---:|---:|---:|
| SourceBridge / `knowledge` | 390 / 390 | 1440 / 1440 | 450 | 314 | 0 | 100 / 104 |
| OpenWiki / `visualize` | 390 / 390 | 1440 / 1440 | 184 | 157 | 0 | 30 / 36 |
| Understand Anything / `viewer` | 390 / 390 | 1440 / 1440 | 55 | 44 | 0 | 1 / 1 |
| CodeBoarding / `static_analyzer` | 390 / 390 | 1440 / 1440 | 489 | 314 | 0 | 86 / 104 |
| DeepWiki / `codemap` | 390 / 390 | 1440 / 1440 | 262 | 232 | 0 | 63 / 80 |
| PocketFlow / `tutorial` | 390 / 390 | 1440 / 1440 | 181 | 168 | 0 | 41 / 61 |

所有页面均满足：

- `documentElement.clientWidth == documentElement.scrollWidth == body.scrollWidth`；
- 至少一个 `.module-detail`、一个本地 `file:` 链接和一个带行号标签的源码链接；
- 内部 `#module-*` 链接无断链；
- 每个 `.source-excerpt pre` 的 `overflow-x` 都是 `auto/scroll`；移动端长代码确实在块内滚动。

临时实证输出目录：

```text
/var/folders/ky/jm76nfgj4js_yjwfjn7fn88h0000gn/T/repo-teacher-module-layout-final-fx6tr0my
```

该目录是本轮验证产物，不是正式 example，也没有被写回产品目录。

## 自动回归

`tests/test_module_report.py` 新增真实浏览器回归，构造同时包含以下压力输入的报告：

- 超长文件路径；
- 不可断的生成式符号名；
- 超长实现链端点；
- 超长单行源码和 hash；
- 文件 URI 与 `:17` 行号标签。

测试分别在 390px 与 1440px 断言整页无溢出，并断言详情、链接、行号及局部代码滚动仍存在。它不是检查 CSS 字符串的替代测试。

## 质量门

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_module_locator tests.test_module_report tests.test_cli \
  tests.test_indexer.IndexerTest.test_typescript_js_import_specifier_resolves_to_repository_ts_source -v
=> 22 tests, OK

PYTHONPATH=src python3 -m unittest discover -s tests -v
=> 190 tests, OK

/Volumes/T7/programe/env/conda/bin/ruff check src tests
=> All checks passed!

python3 -m compileall -q src tests
=> exit 0
```

六仓现场 validation：SourceBridge `valid=true, 0 errors, 1 warning`；OpenWiki、Understand Anything、CodeBoarding、DeepWiki、PocketFlow 均为 `valid=true, 0 errors, 0 warnings`。OpenWiki 的 `.js` specifier → `.ts` 已解析链仍在专项与全量测试中通过。

## 变更文件与边界

- `src/repo_teacher/module_report.py`：只调整报告 CSS containment，不改定位、索引、证据或 URI 语义。
- `tests/test_module_report.py`：增加可执行的移动端/桌面端 Chromium 布局回归。
- `docs/audits/module-locator-fix-round2.md`：记录修复依据和现场复验证据。

未修改 locator、indexer、Go 分析器、teaching、Skill export 或正式 examples。

## 简化与剩余风险

本轮复用了现有单页 HTML 和 Playwright 测试方式，没有新增响应式组件或布局抽象。修复以 CSS containment 为单一机制，避免在每类仓库上增加特例。

剩余风险：真实浏览器门当前覆盖 Chrome 的 390px 与 1440px，尚未做 Safari/Firefox 差异测试；六仓页面内容规模很大，已验证布局和证据保留，但未在本轮进行读屏器/键盘可访问性专项审计。最终发布结论应由新的独立审计 Agent 给出。
