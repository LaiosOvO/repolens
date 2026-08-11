# 技术选型比较第三轮阻断修复记录

日期：2026-08-10  
对应复审：`docs/audits/technology-comparison-reaudit-round3.md`  
状态：两个阻断已实现并完成专项验证，等待父 Agent 启动新的独立复审；本文不自行宣告 PASS。

## 30 秒结论

本轮只处理第三次复审的两个阻断：场景面板现在由一条优先级足够高的 scoped hidden 规则真实隐藏；32 条路线解释不再复述选择算法，而是从场景目标、路线适配机制、首选强项、分维度信号、关键限制和备选触发条件生成。

真实 Chromium 回归覆盖了 1440px 桌面与 390px 移动端。初始状态和四次场景切换都恰好显示 **9/36** 个 pane（1 个 30 秒摘要组 + 8 个功能面板），横向溢出为 0。专项六仓不落盘重放得到 32/32 条完整结构化理由、32 个不同 `why`，每项能力的四个场景均有不同路线适配说明。

## P1-1：场景面板真实隐藏

### 实现

- 在所有 grid 声明之后增加 `[data-scenario-pane][hidden] { display: none !important; }`。规则限定在场景 pane，不会全局改变其他原生 hidden 元素。
- 场景按钮初始写入 `aria-pressed`；切换时同时更新两个位置的同场景按钮状态、`active` class 和所有 pane 的 `hidden` 属性。
- 保留现有的一个全局场景选择控制面：页面顶部和方法区的按钮互相同步，不会出现一处显示已选、另一处仍显示旧状态。

### 自动化浏览器证据

`tests/test_comparison_report.py` 新增真实 Playwright/Chromium 回归。它构造与正式报告等形的 8 功能 × 4 场景页面，而不是只查 HTML 字符串。

| viewport | DOM pane | 初始可见 | 每个场景点击后 | 页面高度 | 横向溢出 |
|---|---:|---:|---:|---:|---:|
| 1440 × 900 | 36 | 9 | 9 / 9 / 9 / 9 | 8,800px | 0px |
| 390 × 844 | 36 | 9 | 9 / 9 / 9 / 9 | 12,752px | 0px |

每次点击还断言：9 个可见 pane 的 `data-scenario-pane` 全部等于所选场景；两组同场景按钮均为 `aria-pressed=true`，其他按钮均不是 active。

浏览器不存在的普通安装环境可以跳过 Playwright 用例；同一测试文件另有不依赖浏览器的 CSS/DOM 合同回归，断言 scoped hidden 规则位于 grid 规则之后且使用 `!important`。本次开发/审计环境中 Chromium 用例实际运行并通过，没有被跳过。

## P1-2：32 条理由改为场景化决策合同

### 结构化数据

`comparison.py` 新增：

- `SCENARIO_GOALS`：四个场景各自的产品目标；
- `SCENARIO_ROUTE_RATIONALES`：4 场景 × 8 能力的路线适配说明、备选触发条件和应观察的分维度信号；
- 每条推荐的 `decision_reason`，字段为：
  - `scenario_goal`
  - `preferred_mechanism`
  - `route_fit`
  - `primary_strength`
  - `primary_signal`（dimension / label / value / source）
  - `critical_limit`
  - `alternative_trigger`
  - `alternative_mechanism`
  - `alternative_projects`

`why` 由上述字段生成，不再出现“场景先选择某技术对象，再按权重筛选”的算法模板。首选强项和关键限制直接来自已经审计的 option；信号优先读取对应 `dimension_scores`，缺失时才明确降级为 scenario 或总体 reviewer signal。若目标路线在当前输入中没有候选，理由会显式说明降级，不把替代路线伪装成预定路线。

### 六仓现有索引不落盘重放

使用 `examples/reference-selection/projects/*/index.json` 作为六仓输入重新执行 `build_technology_comparison()`，未改写正式 examples：

```text
capabilities                    8
scenario recommendations      32
complete decision_reason      32
unique why                    32
each capability unique why     4/4
each capability unique fit     4/4
```

专项测试还从 `SCENARIO_ROUTE_PRIORITIES` 自动构造所有 32 个组合，逐条验证结构字段闭包，并确认场景目标、首选强项、关键限制和切换条件确实进入最终 `why`。

## 修改范围

- `src/repo_teacher/comparison.py`
- `src/repo_teacher/comparison_report.py`
- `tests/test_comparison.py`
- `tests/test_comparison_report.py`
- `docs/audits/technology-comparison-fix-round3.md`

没有修改 Go analyzer、teaching、Skill/persistence 或正式 `examples/reference-selection` 产物；正式报告由父 Agent 在所有并行模块稳定后统一重生成。

## 验证

```text
专项 unittest：14 tests，全部通过
真实 Chromium：1440px + 390px，四场景点击均通过
Ruff（本轮文件）：All checks passed
compileall（本轮文件）：通过
六仓不落盘比较：8 能力 / 32 完整结构化理由 / 32 unique why
```

全量 `unittest discover` 本轮运行 176 tests，其中 175 通过；唯一失败为并行 teaching 改动下的 `test_version_pinned_six_repository_capability_recall`（`resolved_edges == 0`），不涉及本轮允许修改的 comparison/report 文件。该失败已留给对应 teaching 修复 lane，父 Agent 应在共享树稳定后重新执行全量测试。

## 剩余风险与复审入口

- `why` 是源码审计事实与人工场景合同的组合，不是性能 benchmark；最终选型仍需目标环境 PoC。
- 浏览器回归不把 Playwright 加入产品运行依赖；无浏览器环境依靠 CSS/DOM 合同测试，发布流水线应保留至少一个带 Chromium 的 UI job。
- 正式 HTML 尚未在本轮重生成，避免覆盖其他 Agent 正在更新的正式索引；父 Agent 统一重生成后，新的独立审计必须在正式产物上重复 36→9 pane 与 32 条理由闭包检查。

