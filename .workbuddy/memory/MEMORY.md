# RepoLens 项目长期记忆

## 用户的核心业务

代码仓库教学内容生意：用融合 skill `repo-teaching`（路径 `/Volumes/T7/kb/repo/仓库分析工具/repolens/skills/repo-teaching/SKILL.md`，分支 skill/repo-tutorial-script）对 AI/Agent 开源项目做源码级拆解，一次取证产出双产物——仓库讲解报告（report.md + 单文件 HTML）和视频口播稿件（manuscript.md + 提词器 HTML），风格对标抖音博主"全栈观察员"。repolens 本身还有产品愿景（见 PRODUCT-BRIEF.md：报告 HTML → 选功能 → 导出 Skill+索引）。

## 关键路径速查

- 总控进度手册（任何 agent 续写的入口）：`/Volumes/T7/kb/repo/产出进度.md`
- 源头风格材料：`/Volumes/T7/kb/代码教程整理/`（全栈观察员/Leo与Frank/小哲 129 题）、`/Volumes/T7/kb/douyin_全栈观察员/转录合集.md`
- 六仓产出：Proma、eigent（桌面agent应用/）；loopx、prime-agent、codex（agent-cli与运行时/）；cumora（agent协作平台/），各在 `{仓库名}-teaching/`
- **单仓单夹合同**（2026-08-24 固化，commit 6b536c1）：一个仓库全部产物收进 `{repo}-teaching/` 单根目录——report/（repository-report）、learning/（repo-learning）、script/（repo-script）、video/（repo-video）、_legacy/（旧布局归档）；发现散落布局先迁移归位再开工。旧布局（*-system-explainer/、*-learning/、*-script/）已于当日全部清理归位，备份在 `/Volumes/T7/kb/repo_备份_2026-08-24_单仓单夹迁移/`
- codegraph CLI：`/Users/admin/.local/bin/codegraph`，各仓 `.codegraph/` 已建索引
- 报告侧深度合同：`repolens/skills/repository-report/references/`

## 项目规则要点（AGENTS.md）

- 禁止为特定仓库写专用分支/过滤表/Prompt 条款；修复必须落在通用 Pipeline 阶段
- 顶级业务功能四要件：独立使用者目标、独立可见结果、独立业务状态、源码证明的因果链
- 每个通用修复保留两类回归证据：原失败仓重放 + 不同产品类型的最小合成反例

## 已知坑

- 子代理可能撞 403 额度限制（主会话顺序执行兜底）
- ego-browser 截图管线间歇性故障：滚动后黑帧用 `captureBeyondViewport:true` + clip 绕过
- 上游仓库更新后需 `codegraph sync` 并复核稿件行号（行号只对快照 commit 有效）
- **热更新必须顺序执行**（2026-08-24 两次教训）：pull → repo-teacher index → codegraph sync，严禁并发——codegraph 写 `.codegraph/` 会触发 repo-teacher 稳定性校验 fail-closed（「repository changed while being indexed」）；codegraph sync 偶发「Maximum call stack size exceeded」爆栈，直接重跑即可；sync 后用 `codegraph query <新增文件名>` 验证入库
- 不写入上游源码仓库；loopx/prime-agent/codex 的 AGENTS.md 有严格 git/命令禁令
- 网络坑：git clone/codeload tarball 大概率 137 被杀，jsDelivr 逐文件拉是可靠通道，但 curl 循环连发也会被杀（逐条单发）；GitHub push 间歇 HTTP2 framing layer 错误，本地 commit 保留即可
- md 效果参考已沉淀（2026-08-24）：pocketflow-tck（每章中心用例/<10 行代码块/前文摘要续写）与 AIDotNet/OpenDeepWiki（prompt 是外部 md 模板；catalog 读者心智模型+右尺寸；content Source 引用块+mermaid 细则+薄页即失败）——条款已固化进 repo-learning SKILL.md 阶段三「md 效果质量条款」
- **官方文档语义层条款**（2026-08-24，起因 loopx 教程漏掉飞书官方手册被用户指出）：生成教程必须先通读仓库官方文档（docs/、官网、飞书 wiki 等外部载体），官方产品语言与源码逐概念对齐（找不到对应物显式标注）；docs/ 禁止归入「可跳过的非源码资产」；飞书/Notion 等 JS 虚拟化页面用 ego-browser 滚动逐屏收集（按 data-block-id 去重累积）。已固化进 repo-learning SKILL.md 阶段一
