# 单个项目的功能章节输出契约调研

时间：2026-08-10

这份文档只回答一个问题：**当一个 skill 在讲“一个代码仓库/一个功能/一个流程”时，它到底应该输出什么，章节里必须包含哪些字段，叙事顺序是什么。**

我把结果分成两层：

- **事实**：我能在公开的 `SKILL.md`、仓库 README、官方目录页里直接看到的内容
- **建议**：我基于这些事实，对你后续“代码索引 / 仓库教学 / 技术选型”报告格式给出的可执行建议

---

## 一句话结论

成熟的“仓库教学 / 功能讲解” skill，几乎都不是平铺直叙的长文，而是下面几种形态之一：

1. **Onboarding Guide**
   - 面向新加入项目的人
   - 重点是 `Overview -> Tech Stack -> Architecture -> Key Entry Points -> Directory Map -> Request Lifecycle -> Conventions -> Common Tasks`

2. **Code Tour / Walkthrough**
   - 面向想沿着真实代码路径理解一个功能的人
   - 重点是 `step 0 概览 + 有顺序的步骤 + 真实文件/行号锚点 + 解释为什么`

3. **Architecture Report / Blueprint**
   - 面向做技术选型或架构优化的人
   - 重点是 `问题 -> 影响 -> 方案 -> 证据 -> 图 -> 推荐强度`

4. **File-by-file Tutorial Site**
   - 面向系统学习一个仓库的人
   - 重点是 `每个文件一章 + 模块关系 + 搜索/索引/导学路径`

---

## 事实总览

| Skill / 项目 | 真实输入 | 真实输出 | 是否强调行号 / 代码锚点 | 是否强调数据流 / 调用链 | 是否强调例子 | 是否强调差异 / before-after | 是否强调风险 / unknown | 是否强调验证 |
|---|---|---|---|---|---|---|---|---|
| `affaan-m/everything-claude-code` / `codebase-onboarding` | 新仓库、首次 onboarding、生成 `CLAUDE.md` | Onboarding Guide + Starter `CLAUDE.md` | 是，`Key Entry Points` | 是，`Request Lifecycle` | 轻度，举例说明目录与命令 | 否 | 是，明确要标 unknown | 是，要求先做 reconnaissance、不要乱猜 |
| `github/awesome-copilot` / `code-tour` | onboarding tour、architecture walkthrough、PR tour、RCA tour、explain how X works | `.tour` JSON | 是，必须验证 file + line | 是，tour 跟着实际执行路径 | 是，SMIG 里要求 concrete examples | 不是 before-after，而是 step-to-step story | 是，要求验证 anchors、ref、sub-highlights | 是，必须先 verify anchors |
| `mattpocock/skills` / `improve-codebase-architecture` | 扫描代码库中的架构摩擦 / 深化机会 | 临时 HTML 报告 | 不是逐行代码，而是文件/模块级证据 | 是，面向耦合、局部性、深层模块 | 是，报告卡片里写 solution / benefits | 是，要求 before/after diagram | 是，ADR conflict 要标出来 | 是，先 explore 再 report，再 grilling |
| `kitlangton/skills` / `code-walkthrough` | 可见、可验证的 Neovim walk-through，配合 Terminal Control / Navi | 一份不可变的 Navi tour JSON + 终端/可选 OBS 证据 | 是，`file + pattern/line + end_pattern/end_line` | 是，tour 从行为/调用点到实现 | 是，要求展示 verified code and output | 否，不走对比式报告 | 是，要求先跑窄验证命令，再看实际输出 | 是，核心就是 verified tour |
| `TKONIY/tutorial-any-repo` / `tutorial-any-repo` | 任意代码库，可指定语言/目标目录 | MkDocs 静态教程站 + GitHub Pages | 是，所有源文件都要覆盖 | 是，文件间关系要写清楚 | 是，文件级解释里有 code snippet | 否 | 是，TODO tracker + self-review | 是，分 6 阶段，自审 + 部署 |
| `nilbuild/diffity` / `diffity-tour` | 主题、概念、功能、PR URL | 浏览器里的 guided tour | 是，`file/line` + `focus` 子高亮 | 是，强调 flow / journey / actual execution path | 是，具体示例、比喻、表格、代码块 | 否 | 是，PR 模式会给 flags list | 是，先验证路径和输出，再写 tour |

---

## 1) `affaan-m/everything-claude-code` / `codebase-onboarding`

### 事实

**来源**
- [`SKILL.md`](https://github.com/affaan-m/everything-claude-code/blob/main/skills/codebase-onboarding/SKILL.md)

这个 skill 的目标很清楚：**分析一个陌生代码库，生成结构化 onboarding guide，并补一个 starter `CLAUDE.md`。**

### 输入

- 第一次打开项目
- 加入新仓库/新团队
- 用户说“帮我理解这个代码库”
- 用户要生成或更新 `CLAUDE.md`

### 分析步骤

它不是直接读完所有文件，而是按四阶段做：

1. **Reconnaissance**
   - 包管理文件
   - 框架特征
   - 入口文件
   - 顶层目录快照
   - 配置与工具
   - 测试结构

2. **Architecture Mapping**
   - 技术栈
   - 架构模式
   - 关键目录映射
   - 请求从入口到响应的数据流

3. **Convention Detection**
   - 命名规则
   - 代码模式
   - Git 约定

4. **Generate Onboarding Artifacts**
   - Onboarding Guide
   - Starter `CLAUDE.md`

### 最终文件

- 输出 1：`Onboarding Guide`
- 输出 2：`CLAUDE.md`

### Onboarding Guide 的实际章节标题

- `Overview`
- `Tech Stack`
- `Architecture`
- `Key Entry Points`
- `Directory Map`
- `Request Lifecycle`
- `Conventions`
- `Common Tasks`
- `Where to Look`

### 单章节必须写什么

对这个 skill 来说，一个“功能章节”最少要回答：

- 这个项目是什么
- 它用什么技术
- 入口在哪里
- 目录怎么分
- 请求怎么流
- 常见改动该看哪里

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**有数据流 trace**
- 数据流：**有**
- 例子：**有，主要是目录、命令、路径例子**
- 差异 / before-after：**没有**
- 风险 / unknown：**有，明确要求不确定就写 unknown**
- 验证：**有，要求先 reconnaissance，避免乱猜**

### 适合你的借鉴点

- 适合做“代码仓库教学”的**入口层总览**
- 非常适合把你未来的报告写成“人类 2 分钟扫完”的目录化导读

---

## 2) `github/awesome-copilot` / `code-tour`

### 事实

**来源**
- [`SKILL.md`](https://github.com/github/awesome-copilot/blob/main/skills/code-tour/SKILL.md)

这个 skill 的核心定义是：**输出 CodeTour `.tour` 文件，讲一个特定读者能走完的故事。**

### 输入

- onboarding tour
- architecture walkthrough
- PR tour
- RCA tour
- “explain how X works”
- contributor guide
- security review tour

### 分析步骤

1. **Discover the repo**
2. **Infer the reader**
3. **Read and verify anchors**
4. **Write the `.tour`**
5. **Validate**

### 最终文件

- `.tours/<persona>-<focus>.tour`

### 实际模板标题和字段

Skill 里明确要求的 tour 结构是：

- `title`
- `description`
- `ref`
- `steps[]`

每个 step 可以是：

- `directory`
- `file + line`
- `selection`
- `pattern`
- `uri`
- `content`

### 单 step 必须写什么

每个 step 的叙述必须按 **SMIG**：

- **Situation**：你现在看到什么
- **Mechanism**：它怎么工作
- **Implication**：为什么这对这个读者重要
- **Gotcha**：容易漏掉什么

### 叙事顺序

默认故事弧：

1. orientation
2. module map
3. core execution path
4. edge case / gotcha
5. closing / next move

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**有**
- 数据流：**有**
- 例子：**有**
- 差异 / before-after：**没有明确 before-after 卡片，但有 flow story**
- 风险 / unknown：**有，要求验证 file、line、ref**
- 验证：**非常强，必须逐个 anchor 校验**

### 适合你的借鉴点

- 适合做“**功能章节**”而不是“模块清单”
- 适合你未来的报告跳转到真实源码锚点
- 适合做“你从哪里开始读”的导览

---

## 3) `mattpocock/skills` / `improve-codebase-architecture`

### 事实

**来源**
- [`SKILL.md`](https://github.com/mattpocock/skills/blob/main/skills/engineering/improve-codebase-architecture/SKILL.md)
- [skills.sh 页面](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture)

这个 skill 不直接写实现代码，而是：

1. 扫描代码库中的架构摩擦
2. 把候选项做成 HTML 报告
3. 再进入 grilling loop 讨论一个候选项

### 输入

- 想找架构投资点
- 想对比多个架构候选
- 想诊断耦合、shotgun change、testability、AI-navigability 问题

### 分析步骤

1. **Explore**
   - 先 scope，再 scan
   - 结合最近 commit history 找热点
   - 看 `CONTEXT.md` 和相关 ADR
   - 观察耦合、浅层模块、局部性差、接口泄漏、测试困难

2. **Present candidates as an HTML report**

3. **Grilling loop**
   - 用户选一个候选项后，再深入讨论约束和测试

### 最终文件

- 一个临时 HTML 文件，写到系统 temp dir
- 路径示例：`<tmpdir>/architecture-review-<timestamp>.html`

### HTML 报告的实际卡片字段

每个 candidate card 要包含：

- `Files`
- `Problem`
- `Solution`
- `Benefits`
- `Before / After diagram`
- `Recommendation strength`

最后还有：

- `Top recommendation`

### 单章节必须写什么

这一类章节的核心不是“解释全部代码”，而是：

- 这个候选项到底卡在哪里
- 影响是什么
- 为什么值得改
- 改完会怎样
- 证据在哪

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**间接有，更多是 architecture relationship**
- 数据流：**有，作为图和分析对象**
- 例子：**有**
- 差异 / before-after：**强**
- 风险 / unknown：**有，ADR 冲突必须标明**
- 验证：**有，先探索再出报告，不允许直接上结论**

### 适合你的借鉴点

- 这是你未来“技术选型”报告最接近的格式
- 适合把“候选功能 -> 对应仓库 -> 建议程度”变成可读卡片

---

## 4) `kitlangton/skills` / `code-walkthrough`

### 事实

**来源**
- [`SKILL.md`](https://github.com/kitlangton/skills/blob/main/skills/code-walkthrough/SKILL.md)
- [kitlangton/skills README](https://github.com/kitlangton/skills)
- [navi.nvim README](https://github.com/kitlangton/navi.nvim)

这个 skill 的目标不是写 prose 文档，而是：**在可见的 Neovim 会话里，做一条 verified 的 immutable tour。**

### 输入

- 想要 agent-led code walkthrough
- 想做 code-along / live explanation / recorded walkthrough
- 想让用户在终端里跟着一起看

### 分析步骤

1. **Prepare the session**
   - 确认 `termctrl`、Neovim、`navi.nvim`
   - 打开共享可见的终端会话

2. **Establish the journey**
   - 先读代码
   - 跑最窄的验证命令
   - 观察真实输出
   - 选一条连续的 conceptual journey

3. **Author one immutable tour**
   - tour 文件写在 source tree 外
   - 用 `:NaviLoad` 载入

4. **Present the tour**
   - 让 viewer 自己控制节奏

5. **Record with OBS / retain terminal evidence**

### 最终文件

- 一份 **Navi tour JSON**
- 可选 OBS 录制
- 可选终端 evidence

### 真实 tour 结构

从公开资料可以确认 tour stop 的字段包括：

- `file`
- `pattern`
- `end_pattern`
- `line`
- `end_line`
- `message`

### 单步骤必须写什么

每个 stop 要按“先 public behavior，再 mechanism，再 result”的顺序组织。

这个 skill 里，步骤不是百科式说明，而是：

- 先看行为或调用点
- 再进入实现
- 再用 verified output 收尾

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**有**
- 数据流：**有**
- 例子：**有**
- 差异 / before-after：**没有**
- 风险 / unknown：**有，写明不要依赖记忆，要看实际输出**
- 验证：**非常强，是这个 skill 的核心**

### 适合你的借鉴点

- 它适合“**边看边讲**”的讲解形式
- 但它不是最适合做大体技术选型总报告的格式
- 更适合作为你将来报告里的“播放层”

---

## 5) `TKONIY/tutorial-any-repo` / `tutorial-any-repo`

### 事实

**来源**
- [仓库 README](https://github.com/TKONIY/tutorial-any-repo)

这个 skill 是最接近你“每个项目都给我一个可读 HTML / 可导航教程站”的方案之一。

### 输入

- 任意代码库
- 可指定目标目录
- 可指定语言

### 分析步骤

一共 6 阶段：

1. **Explore & Plan**
   - 扫描整个仓库
   - 建目录结构
   - 建 TODO tracker

2. **Foundation Documents**
   - 背景知识
   - 阅读指南

3. **Parallel Module Documentation**
   - 一模块一批 agent
   - 并行写详细解释

4. **Self-Review**
   - 完整性检查
   - 质量 spot-check

5. **Build Website**
   - MkDocs Material
   - 搜索
   - LaTeX
   - 自动导航

6. **Deploy**
   - GitHub Pages

### 最终文件

- 一个可搜索的静态网站
- 站内每个源文件都有对应 explanation 文档

### 文档页的实际标题结构

每个 tutorial doc 采用：

- `# filename.py — Short description`
- `## File Overview`
- `## Key Code Walkthrough`
- `## Core Classes & Functions`
- `## Relationship to Other Modules`
- `## Summary`

### 单章节必须写什么

这一类最重要的是：

- 这个文件做什么
- 关键类 / 函数是什么
- 和别的模块怎么连
- 这段代码在整个项目里扮演什么角色

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**有，靠模块关系和 walkthrough**
- 数据流：**有，但不是最强项**
- 例子：**有，关键 snippet + architecture diagrams**
- 差异 / before-after：**没有**
- 风险 / unknown：**有 self-review，但不是 ADR 机制**
- 验证：**有，self-review + quality spot-check**

### 适合你的借鉴点

- 它最适合做你想要的“**每个仓库一个人类可读站点**”
- 但如果你只想先看一个功能模块，粒度会偏大

---

## 6) `nilbuild/diffity` / `diffity-tour`

### 事实

**来源**
- [Diffity 主仓库 README](https://github.com/nilbuild/diffity)
- [diffity-tour skill mirror](https://claudeskills.info/ko/skills/nilbuild/diffity/diffity-tour/)

这个 skill 的输出是 **浏览器里的 guided code tour**，是最接近“功能讲解要既结构化又有叙事”的形态。

### 输入

- `question`：概念、主题、功能、PR URL

### 分析步骤

1. **Pick a mode first**
   - feature / concept / review 先分流
   - PR URL 会锁到 Review mode

2. **Phase 1: Research**
   - 选真实代码实例
   - 选择足够覆盖不同 facets 的样本

3. **Phase 2: Create the tour**
   - `tour-start` 创建 step 0
   - `tour-step` 逐步追加
   - `tour-done` 收尾

4. **Phase 3: Open in browser**

### 最终文件 / 产物

- browser tour
- `tour-start`
- `tour-step`
- `tour-done`
- 以及浏览器中的可点击高亮

### Step 0 / step body 的实际结构

**Intro / step 0**
- 不是目录
- 是一个完整的 architectural overview
- 里面要放：
  - moving-parts table
  - high-level flow diagram
  - config-context block

**每个 step body**
- Transition
- Explanation
- Takeaway

### 单步骤必须写什么

对于 feature tours，它要求：

- 先用一句过渡把前后步骤串起来
- 再解释机制
- 最后给一个 takeaway / gotcha

还要求：

- `goto:` 真实锚点
- `focus:` 子高亮
- 可用 Mermaid
- 不能只写 bullet list

### 是否有调用链 / 数据流 / 例子 / 风险 / 验证

- 调用链：**有**
- 数据流：**强**
- 例子：**强**
- 差异 / before-after：**不是主要形式**
- 风险 / unknown：**有，路径和 line 必须验证**
- 验证：**非常强，tour 生成前必须验证 file/line/ref**

### 适合你的借鉴点

- 如果你想把“功能章节”写得**更像给人看的故事**，这个格式最值得借
- 它比纯 Markdown 更能解决你说的“我看着累，不知道重点是什么”

---

## 7) `skills.sh` / 技能目录生态的格式观察

### 事实

**来源**
- [skills.sh 首页](https://www.skills.sh/)
- [skills.sh 文档](https://www.skills.sh/docs)

skills.sh 不是单个 skill 的源代码仓库，而是技能生态目录和安装入口。

它展示出来的高质量 skill，通常都带这些块：

- `Summary`
- `Installation`
- `SKILL.md`
- `Prompt`
- `Related skills`

这说明在生态层面，用户实际会先看到：

1. 这技能干什么
2. 怎么装
3. SKILL.md 怎么分层
4. 相关技能是什么

---

## 统一归纳：单个项目的功能章节，最该包含什么

这是我基于上面 6 类 skill 归纳出来的**最稳妥输出契约**。

### 功能章节推荐字段

每个功能章节都尽量按这个顺序：

1. **一句话结论**
   - 这个功能是什么
   - 为什么值得看

2. **它解决的问题**
   - 谁在用
   - 痛点是什么

3. **它怎么工作**
   - 主路径
   - 核心模块
   - 关键调用链 / 数据流

4. **代码锚点**
   - 文件
   - 行号
   - 入口
   - 关键类 / 函数

5. **为什么这么实现**
   - 设计选择
   - trade-off
   - 替代方案

6. **可复用什么**
   - 能借的模块
   - 能复用的模式
   - 不建议直接抄的部分

7. **风险 / unknown**
   - 不确定项
   - 限制
   - ADR / license / 依赖风险

8. **下一步看哪里**
   - 下一章
   - 相关文件
   - 相关仓库

### 最适合你的章节标题模板

如果你最终要的是“每个项目一个 html，而且人类能看懂”，建议每个项目采用：

- `TL;DR`
- `功能地图`
- `关键实现`
- `源码锚点`
- `可复用性`
- `风险与未知`
- `下一步`

如果你要做“某个功能模块”章节，建议再细化成：

- `这个功能是什么`
- `用户路径`
- `内部机制`
- `关键代码`
- `为什么这样设计`
- `可以直接复用的部分`
- `不该直接复用的部分`

---

## 事实与建议分开

### 事实

- `codebase-onboarding` 偏**入口导读**
- `code-tour` 偏**真实代码路径 walkthrough**
- `improve-codebase-architecture` 偏**架构卡片 + HTML 报告**
- `code-walkthrough` 偏**可见可证的终端 tour**
- `tutorial-any-repo` 偏**全仓库教程站**
- `diffity-tour` 偏**故事化、可点击、强锚点的 browser tour**

### 建议

如果你要做的是你前面反复说的那种：

> “让我快速看懂一个仓库有哪些功能、每个功能怎么实现、哪些能复用、然后我做技术选型”

那么你自己的最终格式最好不是单页长文，而是：

```text
repo-report/
├── index.html                 # 总入口，给人先看
├── report.json                # 机器可读索引
├── evidence.json              # 文件/行号/哈希证据
├── modules.json               # 功能 -> 模块映射
├── manifest.json              # 生成与校验信息
├── sections/
│   ├── 00-overview.html
│   ├── 10-feature-map.html
│   ├── 20-feature-<name>.html
│   ├── 30-reuse-matrix.html
│   └── 40-risks-and-unknowns.html
└── source-links/
    └── ...
```

每个功能章节都用：

- 结论先行
- 再讲机制
- 再给源码锚点
- 再讲可复用性
- 最后讲风险和下一步

这样会比“从头讲到尾”清楚很多。

---

## 参考来源

### GitHub / 官方

- [`affaan-m/everything-claude-code` / `codebase-onboarding`](https://github.com/affaan-m/everything-claude-code/blob/main/skills/codebase-onboarding/SKILL.md)
- [`github/awesome-copilot` / `code-tour`](https://github.com/github/awesome-copilot/blob/main/skills/code-tour/SKILL.md)
- [`github/awesome-copilot` / `architecture-blueprint-generator`](https://github.com/github/awesome-copilot/blob/main/skills/architecture-blueprint-generator/SKILL.md)
- [`mattpocock/skills` / `improve-codebase-architecture`](https://github.com/mattpocock/skills/blob/main/skills/engineering/improve-codebase-architecture/SKILL.md)
- [`kitlangton/skills` / `code-walkthrough`](https://github.com/kitlangton/skills/blob/main/skills/code-walkthrough/SKILL.md)
- [`kitlangton/skills` README](https://github.com/kitlangton/skills)
- [`kitlangton/navi.nvim` README](https://github.com/kitlangton/navi.nvim)
- [`TKONIY/tutorial-any-repo` README](https://github.com/TKONIY/tutorial-any-repo)
- [`nilbuild/diffity` README](https://github.com/nilbuild/diffity)

### Skills / marketplace

- [skills.sh 首页](https://www.skills.sh/)
- [skills.sh 文档](https://www.skills.sh/docs)
- [skills.sh 上的 `improve-codebase-architecture`](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture)
- [skills.sh 上的 `code-walkthrough` 相关可见实现](https://www.skills.sh/)

