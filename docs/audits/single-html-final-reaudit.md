# Repo Teacher 单一 HTML 最终独立复验

- 审计对象：`/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-teacher.html`
- 审计日期：2026-08-10（Asia/Shanghai）
- 审计方式：只读静态闭包检查、正式 JSON 复验、Google Chrome 151 真实渲染与物理交互
- 总结论：**PASS**

六仓身份、正式产物、决策/能力锚点、claim proof、Waku 兼容性报告、本地链接闭包、双 viewport 渲染、物理交互、基础可访问性和正式 JSON 校验均通过。首次复验发现的 390px 页面级横向溢出已由父任务修复，并在新产物上独立复验关闭。

## 复验中发现并关闭的问题

### [CLOSED] 390×844 下决策表长路径曾把整页撑宽 61px

真实 Google Chrome 151 以 `390×844` viewport 打开主 HTML 后得到：

- `window.innerWidth = 390`
- `document.documentElement.clientWidth = 375`
- `document.documentElement.scrollWidth = 436`
- `document.body.clientWidth = 375`
- `document.body.scrollWidth = 436`

因此旧产物可水平滚动 61px。定位结果：

- `#decisions`：`clientWidth=345`，`scrollWidth=421`
- `.decision-wrap`：`clientWidth=345`，`scrollWidth=421`
- 第 7 个决策行的模块链接 `understand-anything-plugin/packages/dashboard/src/components/DomainGraphView.tsx` 不换行；其右边界到 `436.3px`
- `.filterbar` 自身的横向滚动是受控局部滚动，不是页面级溢出的根因

修复后生成器为 `.decision-wrap a` 增加 `overflow-wrap:anywhere; word-break:break-word`，并新增单页回归测试。重新生成主 HTML 后，真实 Chrome 151 的 `390×844` 复验得到：

- `window.innerWidth = 390`
- `document.documentElement.clientWidth = 375`
- `document.documentElement.scrollWidth = 375`
- `document.body.clientWidth = 375`
- `document.body.scrollWidth = 375`
- `#decisions clientWidth/scrollWidth = 345/345`
- `.decision-wrap clientWidth/scrollWidth = 345/345`
- 原问题链接右边界 `343.97px`，未越过 375px 页面内容宽度

该问题已关闭。

## 分项验收

### 1. 单一主入口与当前状态：PASS

- 主 HTML 顶栏明确显示：`生产验收 PASS · 单页为唯一阅读入口`。
- `biz/docs/html/index.html` 将本页标为“打开唯一主报告”。
- 当前主结论中没有 `生产验收收口中`、`待重生`、`当前 BLOCK` 或 `REQUEST CHANGES` 残留。
- 历史审计附件仍可点击，但没有把历史状态冒充当前状态。

移动端阻断修复并经本报告第二轮独立复验关闭后，当前 HTML 的“生产验收 PASS”与实际状态一致。

### 2. 六参考仓身份与正式快照：PASS

六个正式 `projects/<project>/index.json` 经 `reference_identity_status` 实测均为 `verified`，HTML 中恰有 6 个 `identity verified`、0 个 `unverified`：

| 项目 | 正式 HEAD | identity | dirty |
|---|---|---:|---:|
| SourceBridge | `2a128bf0c8461fae91d2b424d9168ddf205bb11b` | verified | 是，仅既有 `D LICENSE` |
| CodeBoarding | `8c3f2218c3ecab1294902db5914f5e526f78524d` | verified | 否 |
| Understand Anything | `fe8c5bc591716aafd79b4765549328f08ef5a52e` | verified | 否 |
| OpenWiki | `7531d615216e8cbccf464f66cfbbae3668871c84` | verified | 否 |
| DeepWiki Open | `4181daa5ebde79a1baf8e92a09dd874f8b74411b` | verified | 否 |
| PocketFlow Code2Tutorial | `05b24cbbb0fe409c5e23c9791f0342f07524ffdc` | verified | 否 |

六个正式产物只有一个完整 `analysis_fingerprint`：

```text
de199e70445183052c6d2ec78451918363a26008091e385f0af8b1d72e25874d
```

当前入口解析到 generation：

```text
examples/reference-selection/current
→ .repo-teacher-generations/e161ddb60106cfc8e741a78f3cb6d6b7
```

HTML 中六个项目均展示了对应 HEAD 和 fingerprint 前 12 位，和当前正式 JSON 一致。

### 3. 决策与能力锚点：PASS

- 决策：恰有 8 行。
- capability IDs：恰有 48 个，48 个唯一。
- 决策区有 16 个 capability 跳转（每行主参考 + 辅助参考），16 个目标均唯一且都存在。
- 每一行均有“主参考 / 辅助参考 / 复用模块 / 采用 / 不采用”信息。
- 复用模块均为可存在性验证的本地文件链接。

### 4. Audited claim proof 与上下文链接：PASS

- `claim-proof`：恰有 15 个。
- 每个 proof 都包含本地文件、`Lstart-Lend` 行范围和完整 range SHA-256。
- 重新读取实际行范围并计算 SHA-256：15/15 匹配，0 个错误。
- 六仓项目的“相关模块 / 继续阅读”上下文链接：178 个。
- Waku 正式报告/源码上下文链接：10 个。
- 共 188 个 `.source` 上下文链接；15 个 claim 链接与上下文集合交集为 0，语义和 DOM 分栏均闭合。

### 5. Waku compatibility / candidate 边界：PASS

- 主 HTML 明确写明 Waku 不参加六仓技术排名，只作为第七个 compatibility corpus。
- Waku 正式索引：212 文件、1,557 符号、9,879 关系、13 模块；HEAD `75b0a6d27a19009b0482c877def3eb124181f121`，工作树 clean。
- Waku index fingerprint 与六仓正式分析 fingerprint 相同：`de199e704451…`。
- 五个正式报告均存在，并经真实 Chrome 打开到正确标题：
  - 完整索引：`waku-agent · Repository Index`
  - Memory：`memory · 功能实现面定位`
  - Graph：`graph · 功能实现面定位`
  - Loop：`loop · 功能实现面定位`
  - Gateway：`gateway · 功能实现面定位`
- 四个功能定位 JSON 均为 `resolution.status = composite_candidate`、`verified_capability_surface = false`；切片数分别为 memory 9、graph 6、loop 4、gateway 2，没有被夸大为已验证功能面。
- Waku root/current `index.json` 均 `validate PASS (0 errors, 0 warnings)`。

### 6. 本地链接、fragment、ID 与 runtime：PASS

静态解析数字：

- HTML 大小：163,184 bytes
- ID：60 个，重复 0
- href：252 个
- `file://` href：229 个，缺失 0
- fragment href：23 个，缺失目标 0
- 外部 `http(s)` anchor：0
- 外部 script：0
- 外部 stylesheet：0
- 仅 1 段内联脚本；页面不依赖网络 runtime

### 7. 真实 Chrome 视觉、交互、可访问性：PASS

浏览器：真实 `/Applications/Google Chrome.app`，HeadlessChrome/151.0.0.0。

桌面 `1440×900`：

- `documentElement clientWidth=1425, scrollWidth=1425`
- `body clientWidth=1425, scrollWidth=1425`
- 无页面横向溢出
- 初始 6 个项目、48 个机制卡、18 个默认展开 details

移动 `390×844`：

- 决策表已切换为 8 张 block 卡片
- `documentElement clientWidth=375, scrollWidth=375`
- `body clientWidth=375, scrollWidth=375`
- `#decisions clientWidth=345, scrollWidth=345`
- `.decision-wrap clientWidth=345, scrollWidth=345`
- 无页面横向溢出；首次发现的 61px 溢出已关闭

物理交互（非 JS 直接改状态）实测：

- 点击 CodeBoarding 筛选后，只显示 CodeBoarding；active/`aria-pressed` 同步正确
- 点击“只看重点”后，CodeBoarding 从 8 个机制缩为 3 个 featured 机制；按钮文案变“显示全部”，`aria-pressed=true`
- 再次点击恢复全部机制
- 物理点击 `summary` 后，目标 `details.open` 从 false 变 true
- 物理点击源码链接后，Chrome 实际导航到 `file:///Volumes/T7/workspace/ontology/graph/repo/codeboarding/static_analyzer/engine/language_adapter.py`
- Console / page errors：0

基础可访问性与触摸目标：

- `lang=zh-CN`，1 个 `main`、1 个 `nav`、1 个 H1
- 8/8 button 有文字、`type=button` 和合法 `aria-pressed`
- 48/48 details 有非空 summary；252/252 link 有非空文字
- 移动端 8 个筛选按钮高 48px，48 个 summary 高 62.4px
- `.source` 链接高度范围 36.1–72.4px：全部超过 WCAG 2.5.8 的 24px 最小目标，但部分未达到更舒适的 44px 推荐值；作为非阻断可用性风险记录
- 代表性文字对比度均通过 AA：正文 15.49:1、muted intro 5.06:1、project muted 5.65:1、source 14.84:1、source label 7.43:1、verified badge 7.03:1、status 5.18:1、移动决策标签 7.63:1

### 8. 六仓正式 JSON validate：PASS

命令：

```bash
PYTHONPATH=src python3 -m repo_teacher.cli validate examples/reference-selection/projects/<project>/index.json
```

结果：

- SourceBridge：PASS，0 errors，1 warning；warning 仅为既有 dirty worktree `D LICENSE`
- CodeBoarding：PASS，0 errors，0 warnings
- Understand Anything：PASS，0 errors，0 warnings
- OpenWiki：PASS，0 errors，0 warnings
- DeepWiki Open：PASS，0 errors，0 warnings
- PocketFlow Code2Tutorial：PASS，0 errors，0 warnings

参考仓工作树复查：除 SourceBridge 的既有 `D LICENSE` 外，其他五仓和 Waku 均 clean。

### 9. 未夸大的边界

以下边界在主 HTML 或正式产物中被正确保留，本次审计也不把它们升级成更强结论：

1. Waku 的 memory / graph / loop / gateway 是 `composite_candidate`，不是已验证产品功能面。
2. 静态调用边证明源码关系，不证明每次运行时都会执行；reading-order 边不是 implementation/runtime flow。
3. 只有 15 个行级 audited claim 可用 range hash 闭合；其余 178 个六仓文件链接只是继续阅读上下文。
4. PocketFlow 的抽象/关系是 LLM 候选，不能替代确定性调用图。
5. OpenWiki 的 critic 次数是 prompt-enforced，不是 runtime-enforced。
6. DeepWiki Codemap 的 citation grounding 不等于全 Wiki 逐 claim 校验。
7. SourceBridge 的 `D LICENSE` 是既有非审计工作树变化，本轮没有恢复或修改它。
8. Source link 的 36.1px 最小高度达到 24px 可访问性下限，但没有全部达到 44px 舒适触控目标。

## 运行过的关键命令

```bash
PYTHONPATH=src python3 -m unittest tests.test_single_report -v
PYTHONPATH=src python3 -m repo_teacher.cli validate examples/reference-selection/projects/<project>/index.json
PYTHONPATH=src python3 -m repo_teacher.cli validate examples/compatibility/waku-agent/index/index.json
PYTHONPATH=src python3 -m repo_teacher.cli validate examples/compatibility/waku-agent/index/current/index.json
agent-browser --session single-html-audit set viewport 1440 900
agent-browser --session single-html-audit set viewport 390 844
agent-browser --session single-html-audit open file:///Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-teacher.html
```

单页专项测试：9/9 PASS，其中新增 `test_long_decision_module_links_can_wrap_on_mobile`。CSS 回归测试与真实 Chrome 的 `scrollWidth == clientWidth` 探针共同覆盖本次修复。

## 最终判定

**PASS**：主 HTML 满足本轮九项验收条件。首次复验发现的移动端长路径溢出已修复、测试并在 1440×900 与 390×844 真实 Chrome 上复验关闭；未发现新的阻断问题。
