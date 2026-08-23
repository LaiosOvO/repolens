---
name: repo-learning
description: 仓库学习报告（流水线第 1 步）。对任意代码仓库做一次源码取证与产品表面全量覆盖，产出一份给人学习的 Markdown：项目是干什么的、怎么跑起来、功能全量覆盖账本、逐跳因果证据、学习路径与值得讲的点；产品可运行时实跑核心功能，真实运行截图直接嵌入这份 MD。当用户要求"帮我学习这个仓库""出一份仓库学习文档""先把仓库讲清楚"时使用。后续可用 repo-script 把学习成果补全成视频稿、repo-video 渲染成片。
---

# 仓库学习报告

由当前 agent 本体执行：读源码取证、实跑产品、写 MD、截图嵌入，全部由 agent 完成；不得调用任何报告生成程序或辅助脚本。

定位：**这份 MD 是给人学的，不是给机器存档的**。读者是一个想在 1–2 小时内搞懂这个仓库、然后自己动手写教程稿的开发者。功能覆盖必须全量，但写法是"带着学"，不是堆砌证据。

## 输入

- `SOURCE`：源码仓库绝对路径（必填）；
- `OUTPUT`：输出根目录绝对路径（缺省时在 `SOURCE` 父目录创建 `{repository-name}-learning/`），其下为 `learning.md`、`stages/`、`screenshots/`；不要写入上游源码仓库；
- `LANGUAGE`：默认简体中文。

## 阶段一：取证基座（只做一遍）

完整读取同仓 `skills/repository-report/references/` 下的 pipeline.md、coverage.md、chapter.md、narrative-good-bad.md、performance.md，按其合同执行（下为摘要，冲突处以那些文件为准）：

1. 固定源码身份，写 `stages/00-context.md` 与 `stages/00-run-manifest.md`；
2. 建立/刷新/验证 CodeGraph（仓库无 `.codegraph/codegraph.db` 时自行查明本机 codegraph 入口并建索引），写 `stages/00-codegraph.md`。CodeGraph 不只是索引步骤，它是分层阅读 L0/L2/fan-in 的**执行引擎**（见下）；索引完成后跑 `codegraph status`，把节点/边规模记入 00-codegraph.md；
3. **只做一次产品读取**（README/docs、路由/命令、持久对象、Worker、依赖清单、外部边界、**工程封装边界**：workspace 成员/子包及其作者自述），写 `stages/01-project.md` 与 `stages/02-product-surfaces.md`；md 文档是一手产品声明证据源，与代码不符处以代码为准并显式标注；
4. surface 账本归并核心功能，写 `stages/02-capabilities.md`（每个 surface_id 恰好处置一次，禁止"取前 N 个"式静默截断）；
5. 每个核心功能闭合逐跳因果证据（`文件:行号`），写 `stages/03-implementation/{功能}.evidence.md`；功能并发不超过 3、禁止递归分派；
6. 工程地图 `stages/04-engineering.md`。

### 分层阅读深度合同（模块数 >30 或代码量 >5 万行时必用）

逐文件全读既不可行也无信息量（大头是胶水代码）。按五层分配阅读深度，**每层指定执行引擎**——机械部分交给 CodeGraph（符号级、kind 感知、带 file:line、已缓存），语义判断留给 agent：

- **L0 结构地图**（全量，分钟级）：`codegraph files --format grouped` 出模块清单+每文件符号数；目录级汇总（模块→文件数/符号数）由 agent 从中蒸馏。禁止再手工 `ls`+`find` 统计——索引里都有；
- **L1 作者自述**（全量）：agent 读各模块 `//!`/docstring 头注释、子包 README——CodeGraph 不解析文档语义，这层必须 agent 亲自读；
- **L2 公开合同**（头部 ~30% 模块）：`codegraph query <模块名/符号前缀> --json` 拿符号清单（kind/file:line/visibility），`codegraph node <symbol>` 拿单符号源码+调用边；回答"这个模块对外承诺什么能力"，不读函数体。比 grep pub 更准（kind 感知、含调用边、不误匹配字符串）；
- **L3 故事深读**（典型 30–50 文件全文）：候选由 `tools/cg_rank.py`（加权 PageRank 排序器，基于 codegraph.db，移植 aider 边权乘数——mentioned ×10 / 长特定名 ×10 / 私有 ×0.1 / >5 处定义 ×0.1 / sqrt 引用缩放）机械产出 TOP 文件与 TOP 符号，agent 再按语义信号复核——① 入口可达性（用户可见路径：CLI 子命令/路由/协议 handler 能到达）；② fan-in（`codegraph callers <symbol>` 计被调数）；③ 代码量与内部模块划分复杂度；④ 含状态机/算法而非纯装配。**降权折扣**：私有/内部符号（`_` 前缀、pub(crate)、visibility 非 public）降权、被超多模块引用的通用工具降权——fan-in 高不等于值得深读，通用胶水是例外。依赖 networkx/scipy（workbuddy venv `envs/default` 已装）；大库 DB 扫描慢（~1ms/行）时后台跑，勿前台等待；
- **L4 动态实证**：实跑验证读码结论（即阶段二）。**行号接地纪律**：LLM/文档给的一切行号不可信，只信 `文件:行号` 在源码中的逐字 snippet 反查结果（deepwiki-open `_ground_citations` 同款做法）；
- **对象级批量生成序**（如做对象级文档）：按依赖拓扑排序任务——叶子先做，环引用取破坏程度最小的节点先做并记录（RepoAgent `get_task_manager` 同款）。

广度层（L0/L1）保证**每个目录至少被讲到一句**；深度层（L3/L4）保证复杂模块**讲到能懂**。两者缺一不可——只有深度层会漏掉整个长尾，只有广度层没有可看的内容。

L0/L1 产出独立交付物 `OUTPUT/directory-guide.md`：目录逐个解释，**只在内部划分构成独立架构故事的模块展开**（如 core 的 tools/session、server 的 request handler 区），其余回归一句话表格；禁止把归并账本（crate→能力域→BF 映射表）当目录讲解交付。

> 设计依据（对照开源同类实现的**源码精读**，详见 `docs/reference-implementations-notes.md`）：DeepWiki 系（deepwiki-open）用 embedding RAG 相似度召回，**无法保证全量覆盖**，与本 skill 的 exact-once 账本冲突，不采纳其检索路线；但其产物工程细节被吸收——`<wiki_structure>` XML 两层兜底解析、LLM 行号不可信时逐字 snippet 反查接地、页面强制 ≥5 源文件引用与 `<details>` 引用块。aider repo map（`aider/repomap.py`）的加权 PageRank 全套（边权乘数/personalization/sqrt 缩放/自环/rank 分摊回符号）被移植为 `tools/cg_rank.py`，tree-sitter 抽符号替换为 codegraph.db 直读。RepoAgent 的对象级依赖拓扑排序（叶子先做、second-best 破环）作为批量生成序合同。CodeGraph 本身就是持久化符号图，承担 aider 图构建的角色，不引入 embedding 依赖。教程产物形态再对照 PocketFlow-Tutorial-Codebase-Knowledge（每章中心用例/<10 行代码块/前文摘要续写/全抽象覆盖结构化校验）与 OpenDeepWiki（catalog-generator 读者心智模型 + 右尺寸反模式；content-generator Source 引用块强制 + mermaid 语法细则 + 薄页即失败），其 md 效果条款已固化进阶段三"md 效果质量条款"。

## 阶段二：实跑产品与真实截图

7. 产品可运行时（CLI / 桌面应用 / Web 可本地起服务），实跑核心功能：安装、最小可用示例、1–2 个代表性命令或操作流程；
8. 用 ego-browser（Web/桌面 UI）或终端实录（CLI）截取**真实运行截图**，存 `screenshots/`，文件名标注功能与验证点（如 `run-doctor.png`、`run-quota-should-run.png`）；
9. 跑不起来（缺账号/密钥/授权/平台不符）如实记录前提与卡点，写进 `stages/05-run-notes.md`，**不得用产物页面自拍冒充产品截图**；
10. 验证记录写 `stages/05-browser-check.md`（如走了 ego-browser）。

## 阶段三：组装 learning.md

写 `OUTPUT/learning.md`，单文件 Markdown，结构如下：

1. **这个项目是什么**：一段话讲清解决什么问题、给谁用；README 承诺 vs 代码实际的差异显式标注；
2. **怎么跑起来**：安装命令、最小可用示例、验证生效的方法——全部来自实跑，命令配预期输出；跑不起来的前置条件写在这一节开头；
3. **功能全貌**：核心功能清单（全量，含被合并/支撑/排除项的点名），每个功能一段"是什么 + 入口在哪 + 关键实现一跳"；
4. **核心功能逐个讲**：每个核心功能一小节：痛点 → 用法（命令/配置）→ 底层怎么实现的（逐跳因果，`文件:行号`）→ 坑与边界；**真实运行截图用相对路径嵌在对应小节里**（`![run-xxx](screenshots/run-xxx.png)`），并标注实拍来源（环境、版本、日期）；
5. **架构与工程地图**：一张架构图（Mermaid）+ 关键目录/符号地图；目录逐个解释引用 `directory-guide.md`，不在本文件重复展开；
6. **学习路径建议**：按真实使用顺序排的源码阅读顺序（先读哪个文件、再读哪个），不是按目录平铺；
7. **值得讲的点**：3–5 个候选选题，每个含核心知识点、主比喻候选、三个展开场景、演示案例、坑候选、可用素材清单（指向已有截图/证据文件）——这一节是给后续写视频稿（repo-script）留的选材口；
8. **证据边界**：没覆盖到的、跑不起来的、需要用户核验的，如实列出。

### md 效果质量条款（对照 PocketFlow-TCK / OpenDeepWiki 源码精读，全部条款通用、不针对特定仓库）

**读者心智模型**：章节与功能编排按使用者旅程和心智模型组织，不按文件树平铺；「把多个独立能力藏进一个超大章 = 失败，哪怕那章很长」——定稿前逐节自检：本节是否合并了 deserving 单独成节的独立能力？是则拆分。

**中心用例驱动**：每个核心功能小节以**一个真实可跑的具体用例**贯穿（用户输入 → 命令/操作 → 实际输出），全节围绕解释"这个用例是怎么被解决的"展开，不做特性罗列；先给无码/少码的步骤走查（一步一步发生了什么），再进入代码深潜。

**代码块纪律**：每块 <10 行优先；更长的必须拆成小段逐段讲（walk through them one-by-one），用注释省略非关键实现；每个代码块紧跟一段新手友好解释，并标注来源（`文件:行号` 或块内 `// File: path` 注释）；**禁止编造代码**——只准摘自实读源码，找不到就写"无可用示例"，不编。

**章节衔接**：非首个核心功能小节开头一句上一节回顾（带锚点链接）；提及其他功能/其他章节时必须互链（Markdown 链接），不用"见上文"这种死链写法。

**Mermaid 语法细则**（渲染炸掉的实测坑）：节点/子图 ID 只用字母数字下划线，子图 ID 加 `sg_` 前缀防与节点 ID 撞名；标签一律引号包裹；classDiagram 类块用 `}` 收尾（`end` 只属于 flowchart 子图）；erDiagram 标识符限字母数字下划线；每图 5–15 节点。**图型选型**：架构/依赖 → flowchart TD，交互时序 → sequenceDiagram（≤5 参与者），数据模型 → erDiagram，状态机 → stateDiagram-v2。图必须反映真实结构——节点名与真实类/模块名一致，边必须有源码依据。

**薄页禁令**：每个核心功能小节至少含中心用例 + 逐跳因果 + 边界坑三要素；只有"标题 + 一句话"的薄小节必须深化或并入邻近节。深度承诺：宁可长而实，不可短而虚——但**边界内深**，不吸收属于其他节的内容。

**语言纪律**：正文用目标语言，代码标识符（变量/函数/类名、文件路径、配置键、API 端点、命令行参数）保持原文不翻译。

## 完成门

- repository-report 的覆盖完成门适用：全部 BF/CF 都出现在第 3、4 节，无静默截断；
- **覆盖审计通过**：对全部模块名（workspace 成员/子包）逐个 grep 计数 learning.md 与 directory-guide.md——任何 0 次出现的模块必须补讲或显式归入支撑件总表；只在分组表出现 1 次的检查是否需要升格；审计方法与结果记入 stages 账本（「顶级 BF 账本 ≠ 教程覆盖面」，两者要分别审计）；
- 第 2 节的每条命令都实跑过或显式标注「未实跑：原因」；
- 每个核心功能小节有 `文件:行号` 证据；数字有来源，无来源数字已删除或改定性描述；
- **md 效果条款自检**：逐核心功能节核对——有中心用例贯穿？代码块 <10 行或已拆段+紧跟解释？非首节有上节回顾+互链？mermaid 过语法细则（ID 防撞/标签引号/图型选型）且反映真实结构？无"标题+一句话"薄节？
- 截图全部是真实运行截图，路径有效、有来源标注；没有任何"页面自拍"式验收截图嵌进 MD；
- 产物清单：`learning.md`、`directory-guide.md`、`stages/`、`screenshots/`；
- 最终返回 `learning.md` 绝对路径、功能数、证据条数、截图清单、未实跑项与各阶段耗时。
