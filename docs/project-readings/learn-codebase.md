# learn-codebase profile

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/learn-codebase`
- origin：`https://github.com/ktaletsk/learn-codebase.git`
- HEAD：`cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad`
- 工作树：clean

## 一句话定位
learn-codebase 是一个反“vibe coding”的学习型 skill：它不急着给答案，而是用苏格拉底式提问、预测和复盘把代码库理解真正留在用户脑子里。

## 产品形态与许可证
- 形态：Claude Code Skill。
- 版本身份：仓库未提供独立版本号；它更像可安装的技能包。
- 许可证：MIT，见 [LICENSE](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/LICENSE:1)。

## 主要功能
1. 用苏格拉底式提问代替直接讲答案：用户启动 `/learn-codebase` 后，skill 会先问目标、背景和当前困惑，再根据回答推进；触发→接管→输出→消费：`SKILL.md` 接管对话节奏，调用 `AskUserQuestion` 做结构化选择，把输出变成连续提问、纠错和追问，消费端是正在学习代码库的人；底层机制/关键技术：预测先于揭示、澄清问题、证据问题、观点问题、归纳问题；关键源码：[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:13) 的核心哲学，[learn-codebase/QUESTION-PATTERNS.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/QUESTION-PATTERNS.md:6) 的提问分类，[learn-codebase/README.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/README.md:37) 的 session 示例；复用价值：非常适合做 onboarding、代码评审准备和 legacy code 学习；局限：比“直接给补丁”慢，且需要用户愿意配合回答。
2. 维护跨会话的学习日志：触发→接管→输出→消费：首次会话会检查或创建 `.claude/learning-journal.md`，之后持续更新 Focus & Goals、Mastery Map、Open Questions、Spaced Review Queue、Aha Moments 和 Session Log，输出是持久化的学习轨迹，消费端是后续会话；底层机制/关键技术：Markdown journal 模板、会话结束写回、概念掌握分级；关键源码：[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:56) 的 journal 启动协议，[learn-codebase/JOURNAL-TEMPLATE.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/JOURNAL-TEMPLATE.md:1) 的字段结构，[learn-codebase/README.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/README.md:244) 的 journal 说明；复用价值：这是一个很轻量但有效的“长期记忆”实现模板；局限：完全依赖项目本地文件，迁移和同步需要自己处理。
3. 通过预测、追踪和渐进提示控制理解深度：触发→接管→输出→消费：当用户猜错或卡住时，skill 会依序给概念提示、窄化选项、填空式提示，直到再解释；输出是分层的反馈而不是一次性答案，消费端是学习中的用户；底层机制/关键技术：ZPD 校准、三层提示、错误预测、比较问题；关键源码：[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:207) 的 Feedback Levels，[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:230) 的 ZPD calibration，[learn-codebase/QUESTION-PATTERNS.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/QUESTION-PATTERNS.md:171) 的 graduated hints；复用价值：适合作为“教学型 agent”的对话策略样板；局限：在赶工或只想要 patch 的场景里会显得阻力较大。
4. 强调 read-only 探索和主动回忆，而不是修改代码：触发→接管→输出→消费：学习会话只允许 Glob/Grep/Read 等只读操作，并明确说“Never modify files”，同时建议关闭 Claude Code 的 prompt suggestions，避免提前泄露答案；底层机制/关键技术：只读探索、主动回忆、间隔复习、概念层级；关键源码：[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:308) 的 read-only mode，[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:74) 的 prompt-suggestion 提示，[learn-codebase/JOURNAL-TEMPLATE.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/JOURNAL-TEMPLATE.md:69) 的复习节奏；复用价值：很适合把“读代码”训练成可重复的习惯；局限：它不是修 bug 工具本身，而是理解前的准备器。
5. 用结构化问题让用户自己发现盲点：触发→接管→输出→消费：`QUESTION-PATTERNS.md` 里把问题分成 clarification、assumption-probing、evidence、viewpoint、implication、meta 六类，输出是更有针对性的追问，消费端是学习者；底层机制/关键技术：问题模板库、层层追问、历史推理、错误边界；关键源码：[learn-codebase/QUESTION-PATTERNS.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/QUESTION-PATTERNS.md:1)，[learn-codebase/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:144) 的 questioning patterns，[learn-codebase/README.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/README.md:137) 的 how-it-works；复用价值：可直接借用它的提问目录做 code review / onboarding 教练；局限：问题质量高度依赖上下文和讲解者判断。

## 事实
- README 把它直接称作 “The anti-vibe-coding skill”，并明确说它面向 onboarding、PR 准备和 legacy code 学习；见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/README.md:9)。
- `SKILL.md` 明确要求用 `AskUserQuestion` 工具做结构化选择，并在会话开始时检查学习日志；见 [SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:26) 与 [SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md:56)。
- 这个仓库没有 CLI、Web 或 MCP 入口，核心交付物就是 skill 本身和它管理的 journal 文件。

## 推断
- 它的设计重心不是“回答问题快”，而是“让用户下次还能解释清楚”；这和大多数 coding agent 的默认目标是反着来的。
- `ASK_USER_QUESTION + journal + spaced repetition` 这套组合很像一个轻量版 tutor system。

## 未知
- 仓库没有展示明显的执行代码或测试套件，所以它的实际宿主兼容性主要依赖 skill 平台本身，而不是本仓库内的 runtime。

## 对 Skill / 项目 / CLI 决策的启示
learn-codebase 适合在用户打开报告后增加预测、提示和回忆交互，但它不生成可复现的仓库事实；应作为未来 Skill 层，不替代 CLI 和持久 HTML。
