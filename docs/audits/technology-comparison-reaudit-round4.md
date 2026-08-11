# 六仓技术选型比较第四次独立复审

**结论：REQUEST CHANGES**  
**源码实现：PASS**  
**正式产物：BLOCK（尚未用当前实现重生成）**  
**日期：2026-08-10**  
**范围：** `comparison.py`、`comparison_report.py`、对应专项测试、`technology-comparison-fix-round3.md`，以及 `examples/reference-selection` 下当前正式 HTML/JSON。  
**约束：** 本轮只读复审产品实现；除本报告外没有修改产品代码或正式 examples。

## 一句话结论

第三轮的两个代码修复都是真实有效的，不是靠单测字符串蒙混过关：用六仓正式 index 在临时目录重新构建报告后，真实 Chromium 在 1440px 与 390px 下初始及四次点击均只显示所选场景的 **9/36** 个 pane，横向溢出为 0；32 条理由全部包含场景目标、路线适配机制、首选强项、分维度信号、关键限制和备选切换条件，而且每项能力的四个场景均有不同的路线解释。

但当前用户可打开的正式 `examples/reference-selection/technology-selection.html` 和 `.json` 仍是第三轮修复前的旧快照。正式 HTML 在 Chromium 中仍显示 **36/36** 个 pane；正式 JSON 的 32 条 `why` 仍全部是旧算法模板，且 0 条带 `decision_reason`。因此不能把实现级 PASS 当成交付级 PASS；只需在并行模块稳定后用当前代码重生成正式产物，再做一次产物复验。

## 30 秒验收表

| 验收项 | 当前源码临时重放 | 当前正式 examples | 结论 |
|---|---:|---:|---|
| 36 个 pane 初始可见数 | 9 | 36 | 正式产物 FAIL |
| 点击四个场景后的可见数 | 9 / 9 / 9 / 9 | 36 / 36 / 36 / 36 | 正式产物 FAIL |
| 可见 pane 是否只属于所选场景 | 9/9 | 否 | 正式产物 FAIL |
| 双位置按钮 `aria-pressed` 同步 | 2/2 | 0/2 | 正式产物 FAIL |
| 1440px 横向溢出 | 0px | 0px | PASS |
| 390px 横向溢出 | 0px | 0px | PASS |
| 1440px 页面高度 | 13,337px | 21,834px | 新实现显著收敛 |
| 390px 页面高度 | 21,018px | 39,387px | 新实现显著收敛 |
| 32 条 `decision_reason` | 32 | 0 | 正式产物 FAIL |
| 32 条旧算法模板 | 0 | 32 | 正式产物 FAIL |
| `why` 唯一文本 | 32/32 | 22/32 | 新实现 PASS |
| 六仓真实 Git 身份 | 6/6 verified | 6/6 verified | PASS |
| curated 方案 | 48/48 | 48/48 | PASS |
| source refs / claim / context | 185 / 15 / 170 | 185 / 15 / 170 | PASS |
| claim snippet / hash / range | 0 error | 0 error | PASS |
| 四场景选择签名 | 4/4 不同 | 4/4 不同 | PASS |
| 正式 7 份 HTML 本地链接 | 不适用 | 995 个 href，0 缺失/越界/外链 | PASS |
| 专项测试 | 23 tests 全通过，Chromium 未跳过 | 不证明旧产物已更新 | PASS，但不足以放行 |

## P0

本轮未发现 P0。

## P1

### P1-1：正式 HTML 仍是旧渲染器产物，场景选择对用户不可用

当前源码已经具备正确实现：

- `comparison_report.py` 在 grid 规则之后输出 `[data-scenario-pane][hidden]{display:none!important}`；
- 两组场景按钮初始带 `aria-pressed`；
- 点击时同步按钮 active/`aria-pressed` 与所有 pane 的 `hidden`；
- 用六仓正式 index 临时生成的等形页面中，真实 computed style 证明隐藏 pane 为 `display:none`，可见 pane 始终只有所选场景的 9 个。

但正式 `examples/reference-selection/technology-selection.html`：

- 不包含 scoped hidden 规则；
- 不包含 `aria-pressed` 初始状态与更新逻辑；
- 脚本仍只改 `pane.hidden`，被正式页面自己的 `display:grid` 覆盖；
- Chromium 初始和点击后的 visible pane 均为 36。

独立浏览器记录：

```text
current renderer -> temporary six-repo HTML
1440×900: initial 9; four clicks 9/9/9/9; overflow 0
390×844:  initial 9; four clicks 9/9/9/9; overflow 0

formal examples/reference-selection/technology-selection.html
1440×900: initial 36; four clicks 36/36/36/36; overflow 0
390×844:  initial 36; four clicks 36/36/36/36; overflow 0
```

这不是新的 renderer 缺陷，而是正式产物没有执行第三轮修复后的生成步骤；但对用户可见结果而言仍然是阻断。

### P1-2：正式 JSON/HTML 仍携带旧模板理由

当前实现的六仓不落盘重放结果：

```text
scenario recommendations       32
complete decision_reason       32
unique why                     32
old algorithm template          0
每项能力 unique why             4/4
每项能力 unique route_fit       4/4
每项能力 unique switch_when     4/4
```

每条 `why` 都逐字包含：

- 对应场景目标；
- 对应该场景/能力的路线适配机制；
- 首选项目已有的源码审计 strength；
- 对应分维度 reviewer signal；
- 首选方案关键 limitation；
- 改选备选路线的具体条件、备选机制与备选项目。

程序化复核发现 32 个 `route_fit` 全部不同，32 个 `alternative_trigger` 全部不同；逐条人工抽查也确认差异来自任务目标和机制，不是只替换项目名。外层按四类场景使用稳定句式，但决策性内容不是模板变量替换。

正式 `technology-selection.json` 则仍是：

```text
scenario recommendations       32
decision_reason                 0
old “场景先选择…” template       32
unique why                     22
```

正式 HTML 由该旧 JSON 渲染，因此用户仍看不到本轮已实现的因果理由。

## 已通过的回归项

### 六仓身份与 curated 闭包：PASS

使用当前 `build_technology_comparison()` 重新读取六份正式 project index，并由真实工作树复核 identity：

- 6/6 项目的 `identity_status.status == verified`；
- 48/48 option 来自 `curated-source-audit`；
- 仍为 8 个能力、48 个方案；
- SourceBridge 的 dirty 状态被如实保留，本轮没有修改或恢复其工作树文件。

### claim 与 context：PASS

当前实现与正式 JSON 均为 185 个引用：15 个 claim、170 个 context。对 15 个 claim 重新读取真实源码并按 `line_start`/`line_end` 截取，得到：

```text
line range out of bounds  0
snippet mismatch          0
sha256 mismatch           0
```

### 四场景实际选择差异：PASS

签名材料包含每个能力的 primary option、alternative option 与 module plan；四个场景得到 4/4 不同签名。第三轮修复没有把可见解释改进建立在相同选型数据上。

### 链接闭包：PASS

审计时点 `examples/reference-selection` 下 7 份 HTML 共解析 995 个 href：

- 缺失目标 0；
- 相对路径逃出正式报告根 0；
- 非 file 外部 scheme 0。

链接总数可能随并行 project report 重生成变化，放行条件是闭包保持为 0 错误，不应把 995 当固定产品常量。

## 真实视觉结论

新 renderer 的首屏与正文密度达到本轮目标：

- 1440px 首屏展示标题、报告范围，并在 527px 位置进入 30 秒摘要；
- 390px 首屏完整展示标题与产品说明，30 秒摘要在 689px 位置开始；
- 首个能力在 desktop 约 1,563px、mobile 约 3,138px 出现，较旧正式页的 2,784px / 6,987px 明显收敛；
- 两种 viewport 都没有横向溢出；
- 场景点击后摘要卡、能力推荐 pane 和两组按钮状态一致。

完整报告仍然较长（8 个能力且保留 48 个可展开方案），但长内容被 `<details>` 收起，首屏和 30 秒摘要可用。未发现需要新增 P1 的视觉问题。

## 独立验证记录

专项测试实际运行：

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_reference_catalog \
  tests.test_comparison \
  tests.test_comparison_report \
  tests.test_cli.CliTest.test_compare_command_writes_feature_first_report -v

Ran 23 tests in 6.059s
OK
```

其中真实 Chromium 用例实际运行并通过，没有 skip。审计另行执行了独立 Playwright 脚本，而不是复述单测输出，覆盖：

- 当前 renderer 临时生成的六仓等形 HTML；
- 当前正式 HTML；
- 1440×900 与 390×844；
- 初始状态与四个场景按钮；
- computed `display`、visible scenario、`aria-pressed`、页面高度和横向溢出；
- desktop/mobile 首屏截图人工检查。

## 放行所需最小动作

1. 等 Go analyzer、teaching 与 persistence 的并行修改稳定后，用当前代码重生成正式 `technology-selection.json` 与 `.html`；不要手工补 CSS 或文案。
2. 对重生成后的正式文件重复本报告的 Chromium 验收：初始与四次点击始终 9/36 可见，两个 viewport overflow 为 0。
3. 对正式 JSON 重复理由合同：32/32 `decision_reason`、32 unique `why`、0 条旧算法模板。
4. 再跑 6/6 identity、48 curated、185/15/170 证据闭包、四场景签名和正式链接闭包，确认生成过程中没有回归。

满足以上四项后，本报告唯一阻断即可关闭；当前不要求修改第三轮的 renderer 或 decision-reason 实现。
