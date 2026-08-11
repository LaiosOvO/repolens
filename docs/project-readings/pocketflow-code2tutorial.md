# PocketFlow-Code2Tutorial

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial`
- origin：`https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge.git`
- HEAD：`05b24cbbb0fe409c5e23c9791f0342f07524ffdc`
- 工作树：clean
- 许可证：MIT，见 [LICENSE](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/LICENSE:1)
- 版本说明：仓库里没有明确版本文件，主要通过 [README](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/README.md:80) 和 [main.py](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/main.py:40) 描述运行方式。

## 一句话定位
这是一个“把代码仓库变成教程”的 LLM 流水线样例，重点是串联六个步骤，不是做严谨静态分析。

## 产品形态判断
- 形态：独立项目 + CLI。
- 更像“教程生成工作流模板”，不像成熟的知识产品。
- 对你的启示：它最值得借的是“叙述链条怎么拆步骤”，不是底层代码理解精度。

## 先看结论
- PocketFlow 这套链路最清晰的价值，是把“抓仓库 -> 找抽象 -> 找关系 -> 排章节 -> 写章节 -> 合教程”做成了显式 Flow。
- 但它的很多理解步骤都依赖 LLM 推断，不是 AST 图，不是静态 call graph，也没有像样的自动化测试兜底。
- 所以它适合做你的“讲解编排层”参考，不适合当“证据层”或“源码真相层”。

## 功能清单

### 1. FetchRepo：抓取 GitHub 仓库或本地目录
- 提供什么：把远程仓库或本地目录转成 `{path -> content}` 文件集合，供后续节点分析。
- 触发到输出：CLI 接受 `--repo` 或 `--dir` -> `shared` 里放入 include/exclude/max-size -> `FetchRepo` 调 GitHub crawler 或本地 crawler -> 产出 `shared["files"]`。
- 谁消费：后续所有节点。
- 底层机制：GitHub 路径走 API/clone 读取，本地路径走 `os.walk + .gitignore + fnmatch`；不是 AST，只是文件内容抓取。
- 关键源码：
  [CLI 参数进入 shared](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/main.py:69)
  [FetchRepo](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:22)
  [crawl_github_files](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/utils/crawl_github_files.py:11)
  [crawl_local_files](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/utils/crawl_local_files.py:6)
- 真实测试：
  `未发现 tests/ 或 pytest；这一层没有真实自动化测试。`
- 复用判断：`需改造`
- 怎么改：抓文件这一步可借，但你应该换成更稳定的本地 clone/索引层，不建议直接依赖这里的 GitHub API 递归抓取逻辑。

### 2. IdentifyAbstractions：让 LLM 先挑“核心抽象”
- 提供什么：从全量文件上下文中，先挑出 5 到 N 个“新手应该先懂的核心抽象”。
- 触发到输出：`shared["files"]` -> 拼成长 prompt 和文件索引列表 -> LLM 回 YAML -> 代码校验 key 和 file index -> 产出 `abstractions`。
- 谁消费：关系分析、章节排序、章节写作。
- 底层机制：它不是从 AST 自动识别 abstraction，而是把源码文本喂给 LLM，让 LLM 选概念，再用简单的 YAML/索引校验兜底。
- 关键源码：
  [IdentifyAbstractions.prep](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:84)
  [IdentifyAbstractions.exec](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:118)
- 真实测试：
  `未发现针对 abstraction 识别的自动化测试。`
- 复用判断：`需改造`
- 怎么改：这个思路很适合你的“先讲功能再讲实现”，但必须加证据约束，不能只信 LLM 自选概念。

### 3. AnalyzeRelationships：让 LLM 把抽象之间的关系讲成图
- 提供什么：给出项目摘要，以及抽象之间的主要依赖/调用关系标签。
- 触发到输出：已有 `abstractions` -> 汇总每个 abstraction 的描述和相关文件片段 -> LLM 回 YAML -> 校验 `from/to/label` -> 产出 `relationships.summary + details`。
- 谁消费：章节排序、最终 index 图。
- 底层机制：依然是 LLM 推断；代码只做结构校验、索引边界检查，不做静态调用关系求证。
- 关键源码：
  [AnalyzeRelationships.prep](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:240)
  [AnalyzeRelationships.exec](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:289)
- 真实测试：
  `未发现针对 relationship 推断的自动化测试。`
- 复用判断：`需改造`
- 怎么改：这一步可以保留成“叙述关系层”，但你的生产版必须接入真实源码引用，否则关系图只是一种猜测。

### 4. OrderChapters：把抽象排序成教程叙事顺序
- 提供什么：把一组抽象按“新手先学什么、后学什么”的顺序排出来。
- 触发到输出：`abstractions + relationships` -> LLM 产出有序索引列表 -> 校验无重复、无缺失、索引合法 -> 得到 `chapter_order`。
- 谁消费：`WriteChapters`、`CombineTutorial`。
- 底层机制：这一层的核心不是代码理解，而是“叙事编排”；模型根据 summary 和 relationships 决定先后顺序。
- 关键源码：
  [OrderChapters.prep](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:410)
  [OrderChapters.exec](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:454)
- 真实测试：
  `未发现 chapter order 的自动化测试。`
- 复用判断：`复用`
- 为什么能用：你明确要的是“有叙述逻辑、轻松看懂”，这一层正是它最值得借的部分。

### 5. WriteChapters：逐章写给新手看的讲解
- 提供什么：按排序后的章节逐章生成 Markdown，每章带过渡、例子、Mermaid、链接到其他章节。
- 触发到输出：`chapter_order` -> 给每个 abstraction 准备相关文件片段和上下文章节摘要 -> BatchNode 逐章调用 LLM -> 得到 `chapters`。
- 谁消费：`CombineTutorial`，最终人类读者。
- 底层机制：它不是一次生成全文，而是每一章都拿到前文摘要与全章节目录，这样叙事连续性更强。
- 关键源码：
  [WriteChapters.prep](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:537)
  [WriteChapters.exec](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:630)
- 真实测试：
  `未发现章节写作的自动化测试。`
- 复用判断：`复用`
- 为什么能用：如果你的 HTML 想做到“先功能概览，再逐层进入实现”，这一层的“按章写、保留上下文”非常有参考价值。

### 6. CombineTutorial：把章节合并成最终教程目录
- 提供什么：生成教程首页、章节索引、简单 Mermaid 关系图，并把每章写入单独 Markdown 文件。
- 触发到输出：`relationships + chapter_order + chapters` -> 生成 `index.md` 和多个 `NN_name.md` -> 写到输出目录。
- 谁消费：最终读者、后续静态站点或 HTML 转换器。
- 底层机制：它把前面 LLM 产出的 relationships 画成 Mermaid flowchart，再把章节和 index 物理写盘。
- 关键源码：
  [CombineTutorial.prep](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:753)
  [CombineTutorial.exec](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py:854)
- 真实测试：
  `未发现 combine/output 的自动化测试。`
- 复用判断：`复用`
- 为什么能用：你不一定只输出一个 HTML，所以“主文档 + 分章节附件”这套产物结构对你是有价值的。

### 7. 显式 Flow：把六段链路串起来
- 提供什么：把上面六个阶段固定成一个清晰、能讲给人听的 pipeline。
- 触发到输出：CLI `main.py` -> `create_tutorial_flow()` -> `FetchRepo >> IdentifyAbstractions >> AnalyzeRelationships >> OrderChapters >> WriteChapters >> CombineTutorial`。
- 谁消费：开发者、维护者、后续扩展者。
- 底层机制：PocketFlow 提供简单 Flow/Node/BatchNode 运行模型；这里最强的不是能力深度，而是结构表达足够清楚。
- 关键源码：
  [main.py 启动 flow](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/main.py:104)
  [create_tutorial_flow](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/flow.py:12)
- 真实测试：
  `未发现 flow 层自动化测试。`
- 复用判断：`复用`
- 为什么能用：你现在最缺的是“讲解产品的工作流骨架”，这部分可以直接借设计，不一定借代码。

## 它不是什么
- 它不是 AST 语义图系统。
- 它不是 source-grounded citation 系统。
- 它不是 repo 索引数据库。
- 它不是经过完整自动化测试验证的生产级仓库讲解器。

## 对你产品形态的直接启示
- 对“独立项目”：支持。它本身就是独立 CLI。
- 对“CLI 优先”：强烈支持。这个项目天然证明“先做 CLI 产物，再渲染展示”是顺手的。
- 对“主 HTML + report/evidence/modules 附件”：强烈支持。它已经是 `index + chapter files` 的雏形。
- 对“二期薄 Skill”：支持。后面完全可以做一层 skill 包装，驱动这个 CLI，而不是把逻辑塞回 skill。

## 不建议直接照搬的部分
- 不建议直接照搬它的“仓库理解”方法，因为关键理解步骤主要是 LLM 推断。
- 不建议把它的 relationships 视为可靠技术事实，因为缺少源码级 grounding。
- 不建议把它当作“证据系统”，更适合当“叙事系统”。

## 事实 / 推断 / 未知
- 事实：它确实有六段明确流水线，而且每一步都写在 `main.py/flow.py/nodes.py` 里。
- 事实：仓库里没有发现 `tests/`、`pytest` 或同等级自动化测试。
- 推断：它最适合拿来做你的“内容编排层”和“人类可读叙事层”参考。
- 未知：在复杂仓库上，LLM 选出来的 abstractions/relationships 是否稳定、是否忠于源码，单看当前仓库无法证明。
