# 报告型 Skill 交付格式调研

时间：2026-08-10

这份文档只回答一个问题：**GitHub 上真正成熟的 skill，交付物通常长什么样，怎么让“报告”更清楚，而不是把内容堆满。**

## 结论先说

1. **成熟 skill 的核心不是单个大文档，而是“轻量入口 + 按需加载的支撑文件”。**
   - `SKILL.md` 只保留触发条件、使用目标、核心流程。
   - 详细说明放进 `references/`。
   - 可执行、可复用的脚本放进 `scripts/`。
   - 最终产物需要落到人能看的交付目录里，而不是只输出一坨文字。

2. **代码仓库讲解类 skill 的高质量交付，通常是“总分总 + 目录化输出”。**
   - 先给一句话总览。
   - 再给功能地图、关键入口、数据流、约定、常见任务。
   - 最后给“我想改什么，应该看哪里”的索引表。

3. **社区里比较成熟的趋势是：报告要有结构、层次、证据下钻、可验证输出。**
   - 不只是 Markdown，也会输出 HTML、CSV、JSON、`.tour` 这类面向不同读者的产物。
   - 视觉/交互型报告越来越常见，但前提还是先把结构做好。

## 事实：GitHub / 官方 Skill 规范怎么写

### 1) Skill 本体应该是“轻量入口”

Anthropic 的官方 skill 开发文档明确把 skill 定义成模块化、自包含的包，强调 progressive disclosure，也就是分层加载，不把所有东西一次性塞进上下文。

**关键事实**
- `SKILL.md` 是必需的。
- `scripts/`、`references/`、`assets/` 是可选的，但推荐按需拆开。
- `SKILL.md` 应尽量精简，把细节移到 `references/`。
- `scripts/` 适合确定性、重复执行的任务。
- `assets/` 适合最终产物会用到的模板、字体、图标、示例文件。

**来源**
- [Anthropic skill development docs](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md?plain=1)

### 2) 官方建议的目录结构不是“一个文件包打天下”

官方示例里给出的标准结构是：

```text
skill-name/
├── SKILL.md
├── references/
├── examples/
└── scripts/
```

并且明确建议：
- `SKILL.md` 保持 1,500-2,000 词左右
- 详细内容放 `references/`
- 工作样例放 `examples/`
- 验证/自动化放 `scripts/`

**来源**
- [Anthropic skill development docs](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md?plain=1)

### 3) GitHub / 相关仓库里，代码仓库类 skill 的实际交付内容很像“项目导读”

`codebase-onboarding` 这类 skill 的输出，不是只说“这个项目是什么”，而是直接产出两个面向使用者的成果：

1. **Onboarding Guide**
   - Overview
   - Tech Stack
   - Architecture
   - Key Entry Points
   - Directory Map
   - Request Lifecycle
   - Conventions
   - Common Tasks
   - Where to Look

2. **Starter CLAUDE.md**
   - 代码风格
   - 测试方式
   - 构建与运行
   - 项目结构
   - 约定

它还明确要求：
- 导读要能在 2 分钟内扫完
- 不确定的地方要直接标未知
- 不要复制 README

**来源**
- [codebase-onboarding skill](https://github.com/affaan-m/everything-claude-code/blob/main/skills/codebase-onboarding/SKILL.md)

### 4) “讲代码怎么跑”的 skill 会把输出做成可验证的 walkthrough

`code-tour` 这类 skill 的交付不是长文，而是：
- `.tour` 文件
- 每个步骤都锚定到真实文件和行号
- 每步描述都回答 `Situation / Mechanism / Implication / Gotcha`
- 还有校验脚本，写完就验

它的输出重点非常清楚：
- `file+line` / `directory` / `pattern` / `selection`
- 首尾要有叙事闭环
- 不能只讲概念，必须能直接跳到代码

**来源**
- [code-tour skill](https://github.com/github/awesome-copilot/blob/main/skills/code-tour/SKILL.md)

### 5) 任务型 skill 往往会输出“目录 + 中间产物 + 最终报告”

`event-prospecting` 这类多阶段 skill 的流程很典型：
- 先创建输出目录
- 再生成中间文件，比如 `people.jsonl`、`seed_companies.txt`
- 最后编译成 **HTML + CSV** 报告

这说明成熟 skill 的交付不是单一文档，而是：
- 中间可验证产物
- 最终人类可读产物
- 每一步都有固定位置

**来源**
- [event-prospecting skill](https://github.com/browserbase/skills/blob/main/skills/event-prospecting/SKILL.md)

## 社区观点：X / Twitter 上大家在怎么说

下面这些更偏社区经验，不是官方规范，但方向很一致：

### 共识 1：Progressive disclosure 是 skill 能做大的关键

社区反复强调，skill 之所以有效，是因为只加载相关部分，不把所有说明一次塞进上下文。

**来源**
- [Alex Albert on X](https://x.com/alexalbert__/status/1978877546969354519)
- [Tadas Petra on X](https://x.com/tadaspetra/status/2019045368797806602)
- [pedram.md on X](https://x.com/pdrmnvd/status/2020967757706297797)

### 共识 2：一个 skill 不是只有说明文，而是“说明 + 引用 + 脚本”

社区也普遍把 skill 看成一个目录结构，而不是单个 Markdown。

**来源**
- [Claude Code Community on X](https://x.com/claude_code)
- [Stephen Bonifacio on X](https://x.com/stepanogil)
- [Kloss on X](https://x.com/kloss_xyz/status/2044169678961234282)

### 共识 3：更好的“报告 skill”会输出更像作品集，而不是长篇流水账

X 上也能看到两类趋势：
- 视觉/交互化报告
- 面向读者的结构化 explainer

比如有人提到生成 **MDX + visual / interactive components**，也有人做 `Visual Explainer` 这种 skill，目标就是减少认知负担。

**来源**
- [Andrej Karpathy on X](https://x.com/karpathy)
- [Claude Code Community on X](https://x.com/claude_code/with_replies)

## 事实 vs 推断

### 事实

- Skill 的标准形态是 `SKILL.md` + 可选的 `references/`、`examples/`、`scripts/`、`assets/`。
- 高质量 skill 强调 progressive disclosure。
- 代码仓库导读类输出通常包含：概览、架构、关键入口、目录图、约定、常见任务、去哪里改。
- walk-through 类 skill 倾向于把代码路径、行号、步骤和叙事串起来。
- 多阶段任务型 skill 会有中间产物目录，最后再编译成 HTML / CSV / `.tour` 等终态文件。

### 推断

- 你要做的“仓库教学 / 报告 skill”，最适合的交付方式不是单个 HTML，而是：
  - 一个总入口 HTML
  - 一组按项目拆分的子报告
  - 一份机器可读索引 JSON
  - 一份证据文件
  - 一份可复用的模块索引
- 这种结构比平铺叙述更适合技术选型，因为可以直接从“功能 -> 模块 -> 证据”下钻。

## 对你这个项目的直接建议

如果目标是“让我快速看懂一个仓库有什么功能、怎么实现、能不能复用”，建议最终交付物长这样：

```text
repo-report/
├── index.html
├── report.json
├── evidence.json
├── modules.json
├── manifest.json
├── README.md
└── sections/
    ├── 00-overview.html
    ├── 10-features.html
    ├── 20-architecture.html
    ├── 30-evidence.html
    └── 40-reuse-and-risks.html
```

推荐叙事顺序：
1. 先一句话结论
2. 再列功能地图
3. 再列实现路径
4. 再给可复用模块
5. 最后给风险、缺口、未知项

推荐页面结构：
- Hero：这个项目是干什么的
- 功能地图：有哪些能力
- 关键实现：每个能力怎么实现
- 代码入口：从哪里开始读
- 证据锚点：文件 / 行号 / 配置 / 测试
- 可复用性：能借什么、不能直接抄什么

## 参考来源

### GitHub / 官方

- [Anthropic skill development docs](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md?plain=1)
- [codebase-onboarding skill](https://github.com/affaan-m/everything-claude-code/blob/main/skills/codebase-onboarding/SKILL.md)
- [code-tour skill](https://github.com/github/awesome-copilot/blob/main/skills/code-tour/SKILL.md)
- [event-prospecting skill](https://github.com/browserbase/skills/blob/main/skills/event-prospecting/SKILL.md)

### X / Twitter

- [Alex Albert on X](https://x.com/alexalbert__/status/1978877546969354519)
- [Tadas Petra on X](https://x.com/tadaspetra/status/2019045368797806602)
- [pedram.md on X](https://x.com/pdrmnvd/status/2020967757706297797)
- [tpierrain on X](https://x.com/tpierrain/status/2020758356789535026)
- [Akshay on X](https://x.com/akshay_pachaar/status/2029534926828385377)
- [xiyu on X](https://x.com/ohxiyu/status/2044233943466291419)
- [Steve8708 on X](https://x.com/Steve8708/status/2066906454704218337)
- [Nico Bailon on X](https://x.com/nicopreme)
