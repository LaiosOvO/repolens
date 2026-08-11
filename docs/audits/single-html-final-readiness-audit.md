# Repo Teacher 单一主 HTML 最终就绪度独立审计

> 审计日期：2026-08-10  
> 审计对象：`tools/build_single_report.py` 与 `biz/docs/html/repo-teacher.html`  
> 审计方式：只读静态检查；未修改产品、HTML、测试或参考仓  
> 唯一写入：本审计报告

## 一句话结论

**BLOCK — 阅读结构已经达到“一个 HTML 看清六个参考仓 + Waku 兼容样本”的形态，但当前不能签发为生产版。**

阻塞发布的不是“页面不够好看”，而是四个准确性/新鲜度问题：

1. Waku 区块仍在展示已经被后续独立复审关闭的旧缺陷，且链接的仍是修复前审计。
2. 页面宣称“每个判断回到文件、行号、符号和关系”，实际只渲染了文件路径，并绕过了仓库已有的 audited-claim / commit identity 证据门。
3. “功能选型”表没有给出真正的主参考、辅参考、不采用边界和可点击模块，无法从用户最常用的“按功能选型”入口直达对应代码。
4. 六个“完整索引”链接虽然都能打开，但指向 03:08–03:09 的旧生成物，没有包含后续 teaching/core 修复。

## 验收看板

| 用户要求 | 结果 | 审计证据 |
|---|---:|---|
| 只有一个主 HTML 作为阅读入口 | **PASS** | `repo-teacher.html` 为 128,204 bytes，CSS/JS 全部内联，无外部运行时 |
| 六个不同参考项目都出现 | **PASS** | 6 个 `article.project`：SourceBridge、CodeBoarding、Understand Anything、OpenWiki、DeepWiki Open、PocketFlow Code2Tutorial |
| 先说结论，再分项目，最后交付 | **PASS** | 30 SECOND MAP → 四层结论 → 功能选型 → 六项目下钻 → Waku → 使用方式 |
| 每个项目说清“提供什么” | **PASS** | 每仓有独立 role/focus/verdict，摘要卡不是同质项目列表 |
| 每个项目说清“怎么实现” | **PASS with gaps** | 6 仓 × 8 功能 = 48 张机制卡；每张有 summary、实现流、technology tags、strengths、limitations、reuse verdict。但未渲染 catalog 中的 `approach`，也没有关键 symbol/行级证据 |
| 说清“复用哪个模块” | **PASS with gaps** | 每张卡有源码文件列表，但没有把“主复用模块”与“背景阅读文件”分开 |
| 源码可点击 | **PASS** | 183 个 `.source` 链接（178 个六仓链接 + 5 个 Waku 链接），目标缺失 0 |
| 页内链接闭包 | **PASS** | 总 href 197；file href 190；fragment href 7；缺失文件 0；缺失锚点 0；12 个 id 全部唯一 |
| Waku 只是兼容测试，不参加六仓排名 | **PASS** | 摘要卡、四层结论、独立 Waku section 三处明确说明 |
| Waku 结论是当前真实状态 | **FAIL / BLOCK** | 主 HTML 仍展示旧 REQUEST CHANGES；后续 `core-index-reaudit-round3.md` 已给出 PASS |
| 证据声称与实际证据级别一致 | **FAIL / BLOCK** | 主 HTML 将 file-context 统一称为证据，未使用 `AUDITED_CLAIMS` 和 `REFERENCE_IDENTITIES` |
| 选型结论能直达主/辅模块 | **FAIL / BLOCK** | 表格只有“A + B”和一句理由，没有模块链接或 capability anchor |
| 移动端基础布局 | **PASS with risks** | 900px/520px 有断点，网格能降为单列；但表格强制 860px 宽、部分点击目标不足 48px，过滤状态缺 ARIA |

## 阻塞问题

### B1 · Waku 展示的是旧缺陷，不是当前复验结论

**位置：** `tools/build_single_report.py:102-109, 195, 252`

页面展示：

- `current/index.json` 校验语义不一致；
- 未生成产物也创建 compatibility link；
- 多级 receiver 被错连成自调用，“已进入核心修复门”。

但 `docs/audits/core-index-reaudit-round3.md` 的独立复审结论是 **PASS**：

- root/current/immutable 三入口都由 verified reader 校验；
- 正常发布后 root convenience links 闭包，hard-kill 后下一 writer 会自修复；
- Waku `self.model.transcribe()` 错连 `Ears.transcribe` 的边数为 0；
- Waku 新 fingerprint cold rebuild 与 disk-warm 都验证通过。

主 HTML 还链接到修复前的 `waku-agent-index-compatibility.md`，该报告内仍有 REQUEST CHANGES。这会让用户误以为产品仍有已关闭的 P0/P1。

**最小修复：**

1. 把三条文案改成“原始发现 → 修复方式 → 独立复验 PASS”的时间线，不再用“已发现”表示当前未闭合状态。
2. 主链接指向 `core-index-reaudit-round3.md`，原始 Waku 审计只作“修复前证据”次链接。
3. Waku 指标显示快照 HEAD、审计时间和 fingerprint；`5.13s` 是旧运行样本，后续复审记录为 `6.70s`，不应把环境相关 wall time 当作无条件常量。

### B2 · 主页绕过了仓库已有证据门，将“继续阅读”写成“证据”

**位置：** `tools/build_single_report.py:24, 112-140, 145-163, 245`

生成器只导入 `REFERENCE_CATALOG`，`source_link()` 只检查路径是否存在，然后将链接统一标记为“源码”。它没有检查：

- 当前 clone 是否仍是审计的 remote / commit / source bundle；
- 该文件是 claim proof，还是只供继续阅读的 file-context；
- 结论对应的精确行范围和 range hash。

`src/repo_teacher/reference_catalog.py:642-647` 的合同已明确规定：没有 `AUDITED_CLAIMS` 的 `source_paths` 只能标为 `file-context` / `symbol-context`，**不得冒充支持文案结论的证据**。

当前数量对比：

- 六仓 capability：48；
- 六仓 source path 展示：178；
- `AUDITED_CLAIMS` 精确 claim anchors：15，仅分布在 SourceBridge / OpenWiki / DeepWiki Open；
- 主 HTML 显示的 commit / bundle identity：0；
- 主 HTML 显示的 audited line ranges / hashes：0。

因此“每个判断回到文件、行号、符号和关系”是超出页面实际证据的声称。

**最小修复：**

1. 生成器使用 `REFERENCE_IDENTITIES` 展示每仓 audited HEAD，构建时校验当前 clone；身份不符则整仓降级为“未验证上下文”。
2. 渲染 `AUDITED_CLAIMS`：显示 claim、path、line range 和 range hash，并与普通 `source_paths` 分栏。
3. 普通 source path 的标签改成“相关模块 / 继续阅读”，不再称为 claim proof。
4. 在未补齐所有 claim anchors 前，把四层结论中的强声称改成真实口径：“已审计 claim 回到行级证据；其余链接是模块上下文”。

### B3 · 选型表不能从“功能”直达“要复用的模块”

**位置：** `tools/build_single_report.py:91-100, 119-142, 181-184, 248`

页面声称“每一行都保留主参考、辅助参考与不能越过的证据边界”，实际表格只有：

1. 目标功能；
2. `A + B` 的无序项目组合；
3. 一句采用理由。

它没有指明 A/B 谁是主参考，没有显示功能级“不采用”边界，也没有连到后文对应 capability 卡。`details` 只有 `data-capability`，没有唯一 id，因此不能从表格精确跳到“CodeBoarding 的 code-graph”或“SourceBridge 的 evidence-grounding”。

**最小修复：**

1. `DECISIONS` 改为结构化数据：`primary`、`secondary`、`adopt`、`do_not_adopt`、`module_links`。
2. 每张 capability card 增加唯一 id，如 `project-codeboarding--code-graph`。
3. 选型表直接展示“主参考 / 辅参考 / 复用模块 / 不复用什么”，项目名和模块名均可点击。
4. 默认摘要只展示每仓 3 个 featured capability；不要为补表格而重新变成大段平铺文字。

### B4 · 六个“完整索引”链接存在，但语义上已旧

**位置：** `tools/build_single_report.py:150, 159`

六个链接目标的生成时间都在 03:08–03:09，而 teaching/core 后续修复和审计持续到 07:13 之后。链接“文件存在”是 PASS，但它们并不是当前冻结代码重生成的最终产物。

这是语义新鲜度问题，不是 broken-link 问题。用户点击“打开该仓完整索引”后可能看到修复前的 teaching/codemap 结论。

**最小修复：**

1. 等 teaching 最终独立复审 PASS 和源码冻结后，重新运行六仓 compare/report 生成。
2. 重生成后校验每个 project report 的 generation/fingerprint 与当前产品一致，再将主页状态改为 PASS。
3. 主页展示产物的“生成时间 + analysis fingerprint”，不只显示主页自己的 footer timestamp。

## 非阻塞但应在签发前收口的质量问题

### M1 · 移动端选型表仍需大幅横向滚动

`tools/build_single_report.py:213` 将表格 `min-width` 固定为 860px。外层能滚动，所以不会裁剪，但在 375px 屏幕上无法同时对比一行的三列。

**建议：** 520px 以下将每个 decision row 转为卡片，而不是只依靠横向滚动。

### M2 · 小字号橙色文字对比度不达 WCAG AA

`--accent: #e45d31` 在 `#f4f0e7` 上对比度约 **3.12:1**，在 `#fffdf7` 上约 **3.49:1**。它被用于 11–12px 的 kicker / eyebrow / section label，普通文字 AA 需要 4.5:1。

**建议：** 将文字色与装饰色拆开；保留亮橙色做边框/圆点，文字使用更深的 `--accent-text`。

### M3 · 过滤器的键盘焦点可见，但状态语义不完整

- 只有“只看重点”按钮有 `aria-pressed`；项目过滤按钮只切换 `.active`，读屏无法获知当前选中项。
- 7 个项目过滤按钮没有显式 `type="button"`；当前不在 form 内，不会误提交，但组件移入 form 后会改变行为。
- `.project-filter` 的静态高度约 38–40px，低于移动端建议的 48px 点击目标。
- 页面很长，但没有 skip link。

**建议：** 同步 `aria-pressed`，显式设置 button type，移动端提高点击高度，添加“跳到主结论 / 选型 / 项目”跳转。

### M4 · 标题层级跳过 h4

项目为 h3，机制标题是 `summary > span`，内部直接使用 h5。视觉层级清楚，但语义 heading outline 不完整。

**建议：** 将机制标题包装为 h4，内部分组再用 h5。

## 已证明成立的部分

### 1. 页面不再是平铺叙述

页面有清楚的总分总路径：

- 顶部英雄区直接回答“这个页面帮你做什么判断”；
- 7 张摘要卡在一屏内区分六仓角色和 Waku；
- 四层结论将 fact / boundary / teaching / proof 分开；
- 六仓各有一句话采用边界，默认只展开 3 个重点机制；
- “只看重点”能隐藏 30 张次要机制卡，不必连续阅读 48 张卡。

这部分正面回应了用户先前“找不到重点”的问题，不应在修复证据时退回长文堆叠。

### 2. 六仓的角色确实不同

| 项目 | 页面给出的主贡献 | 默认展开的三项机制 |
|---|---|---|
| SourceBridge | 生产索引与证据基准 | evidence grounding / incremental update / code parsing |
| CodeBoarding | 调用图与组件发现 | code graph / component discovery / incremental update |
| Understand Anything | 新鲜度与交互图 | incremental update / codemap visualization / agent workflow |
| OpenWiki | Wiki 规划与独立评审 | component discovery / evidence grounding / tutorial generation |
| DeepWiki Open | Codemap 与源码跳转 | codemap visualization / tutorial generation / agent workflow |
| PocketFlow Code2Tutorial | 六阶段教程叙事 | tutorial generation / component discovery / agent workflow |

这不是为六个仓复制六份同样的模板；每仓的默认展开内容和采用边界确实不同。

### 3. 链接闭包和单文件完整性成立

静态解析结果：

```text
HTML bytes                 128,204
project articles                 6
capability details              48
featured/open details           18
secondary/closed details        30
all hrefs                      197
file hrefs                     190
source buttons                 183
missing file targets             0
fragment hrefs                   7
missing fragment targets         0
ids / unique ids             12 / 12
external script/style runtime    0
```

当前 HTML 与当前生成器输出一致（忽略 footer 的当前时间后逐字符相等）。因此修复应发生在生成器，然后重生成 HTML，不应手工只改产物。

## 最小发布修复顺序

1. **先冻结 teaching/core 源码并取得最终独立 PASS。**
2. **重生成六仓正式产物，使“打开该仓完整索引”不再指向 03:09 的旧输出。**
3. **修正 Waku 时间线和主审计链接，显示修复后 PASS 而非旧 REQUEST CHANGES。**
4. **把 commit identity、audited claims 和 file-context 分层渲染进主 HTML，消除过度证据声称。**
5. **将选型表改为主参考 / 辅参考 / 复用模块 / 不采用边界，并与 capability card 精确互链。**
6. 重生成 `repo-teacher.html`，重放链接闭包、唯一 id、六仓×8功能、Waku 隔离、移动端静态检查。
7. 最后处理对比度、ARIA、tap target 和移动端 decision cards；这些不应阻塞前面的事实正确性修复。

## 签发门

只有以下条件全部满足，才应将顶部“生产验收收口中”改为“生产验收 PASS”：

- [ ] teaching/core 最终独立复审 PASS；
- [ ] 六仓完整索引已从冻结代码重生成；
- [ ] Waku 区块显示修复后结论和最终复审链接；
- [ ] 主页能区分 audited claim proof 与 file-context；
- [ ] 每个选型行可直达主/辅 capability 和复用模块；
- [ ] 本地链接 0 缺失、锚点 0 缺失、id 0 重复；
- [ ] 对比度、ARIA 状态和移动端点击目标达到发布门。

当前状态：**4 个内容/新鲜度阻塞项，4 个非阻塞质量项，结论 BLOCK。**
