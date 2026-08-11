# Feature Section Output Contracts from Mature Tutorial / Docs Projects

结论先行：这些成熟项目都不是“先写一段解释再说”，而是先定义**产物格式**，再反推每个功能章节该输出什么。

你现在这个页面之所以显得“太简单”，本质上是因为它只有概念，没有把每个功能的**输入、执行链、输出物、更新机制、证据**拆开。下面这份研究稿就是把这几类项目的真实输出协议拆出来，方便你直接借到当前教程里。

## 一、跨项目共性

1. **先定义产物，不先写散文。**
   - `codebase-to-course` 先规定目录结构和模块 brief，再写 HTML。
   - `PocketFlow Code2Tutorial` 先规定 YAML 抽象、章节顺序、章节文件名，再写正文。
   - `CodeWiki` 先规定 `module_tree.json`、`overview.md`、`metadata.json`，再让模型填内容。
   - `SourceBridge` 先规定 `page_id / template / audience / dependencies`，再生成页面块。

2. **每个功能至少要给出四件事。**
   - 它是谁触发的
   - 它接谁的数据
   - 它产出什么文件/页面/块
   - 它什么时候会刷新或失效

3. **成熟项目都把“更新机制”当作一等公民。**
   - 有的看 `metadata.json + commit_id`
   - 有的看 `stale_when`
   - 有的看 `learning-journal.md`
   - 有的看缓存和任务状态

4. **真正能复用的不是文案，而是字段。**
   - `actor / responsibility / data flow / output artifact / update trigger / evidence`
   - 这几个字段比长篇解释更能把一个功能讲清楚

## 二、项目对比总表

| 项目 | 真实产物 | 章节树 / 模板字段 | 执行链 | 更新机制 | 最值得借的部分 |
|---|---|---|---|---|---|
| DeepWiki-Open | 交互式 Wiki、codemap、聊天 / 深度研究页面 | `wiki_structure` 里有 `title / description / sections / pages`，page 还包含 `importance / relevant_files / related_pages` | clone repo -> analyze -> embeddings -> docs -> visual diagrams -> wiki -> chat/research | 本地仓库存储、RAG、深度研究多轮迭代 | “页面结构先行”的思路，特别适合做“功能树” |
| PocketFlow Code2Tutorial | `output/<project>/index.md` + 章节 markdown | 抽象列表、关系、章节顺序、章节文件名、前后章、历史摘要 | FetchRepo -> IdentifyAbstractions -> AnalyzeRelationships -> OrderChapters -> WriteChapters -> CombineTutorial | `--no-cache`、语言切换、最大抽象数 | 章节写作 prompt 的约束最完整 |
| codebase-to-course | `styles.css`、`main.js`、`_base.html`、`_footer.html`、`build.sh`、`modules/*.html`、`index.html` | 模块 brief：Teaching Arc / Code Snippets / Interactive Elements / Reference Files / Connections | 分析代码 -> 设计课程 -> 写 briefs -> 写模块 -> build.sh 组装 | briefs 可删，模块独立写；无复杂增量逻辑 | 最像“真正教程站”的产物协议 |
| learn-codebase | `.claude/learning-journal.md` | Focus & Goals / Concept Mastery Map / Open Questions / Spaced Review Queue / Aha Moments / Session Log | 检查 journal -> 发现兴趣 -> Socratic 问答 -> 持续更新 journal | `setup_done`、间隔复习、学习状态迁移 | 问题设计和学习状态跟踪 |
| CodeWiki | `docs/overview.md`、`module_tree.json`、`first_module_tree.json`、`metadata.json`、各模块 `.md` | Main doc / sub-module doc / Mermaid diagrams / cross-links | dependency graph -> clustering -> leaf-first docs -> parent overview -> metadata/validation | `--update`、`--compare-to`、按 commit_id 失效、只重跑受影响模块 | 模块树 + 增量更新 + 父子文档联动 |
| SourceBridge | cliff notes、learning paths、code tours、workflow stories、system overview、API reference、glossary | 页面 frontmatter + block markup：`page_id / template / audience / dependencies / stale_when` | index repo -> 生成 field guides -> web / MCP / VS Code 展示 | `stale_when`、影响分析、缓存文档 | “一页一个功能契约”的最成熟模板 |

## 三、逐项目拆解

### 1) DeepWiki-Open

**功能识别**
- 这是一个“仓库 -> 交互式 Wiki”的系统，同时还带 RAG 问答和 deep research。
- README 明确说它会分析结构、生成全面文档、创建图表、组织成 Wiki、生成 codemap。

**真实输出**
- Wiki 页面结构不是随便写散文，而是有显式 `wiki_structure`。
- 从测试可以看到，结构至少包含 `title`、`description`、`sections`、`pages`、`rootSections`。
- `page` 级别会携带 `id`、`title`、`importance`、`relevant_files`、`related_pages`。

**执行链**
- `api/main.py` 先挂载 `auth / repo / wiki / chat / codemap` 路由。
- 仓库先被 clone 到本地，再做代码结构分析、向量嵌入、RAG 检索、文档生成。
- README 中文版还明确了 deep research 的三段式：研究计划 -> 研究更新 -> 最终结论。

**更新机制**
- 本地存储在 `~/.adalflow/repos/`、`~/.adalflow/databases/`、`~/.adalflow/wikicache/`。
- 深度研究最多 5 轮，属于“迭代式收敛”。

**未验证项**
- 我没有把前端页面完整跑一遍，所以具体 Wiki 页面渲染模板没有全量反向验证。

**可复用点**
- 如果你要解释“某个功能页面为什么存在”，可以直接借它的 `title / sections / pages / related_pages` 这种结构。

**来源**
- [https://github.com/AsyncFuncAI/deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open)
- [本地 README.zh.md](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/README.zh.md)
- [本地 api/main.py](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/main.py)
- [本地 tests/backend/services/test_wiki_structure.py](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_structure.py)
- [本地 tests/backend/services/test_wiki_content.py](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_content.py)

### 2) PocketFlow Code2Tutorial

**功能识别**
- 这是“把代码库变成初学者教程”的流水线，不是单页概览。

**真实输出**
- 最终输出是一个项目目录，核心是 `index.md` + 多个章节 markdown。
- 章节写作时会强制生成：
  - 章节标题
  - 过渡语
  - 用例驱动的解释
  - 10 行以内的小代码块
  - `sequenceDiagram`
  - 与其它章节的 Markdown 链接

**执行链**
- `FetchRepo` 收文件。
- `IdentifyAbstractions` 抽象出核心概念。
- `AnalyzeRelationships` 产出关系摘要和边。
- `OrderChapters` 决定讲解顺序。
- `WriteChapters` 用 `BatchNode` 批量写章节。
- `CombineTutorial` 合并输出。

**数据流**
- `shared` 字典贯穿全局，里面有 `files / abstractions / relationships / chapter_order / chapters / final_output_dir`。
- 章节 prompt 会把 `previous_chapters_summary` 带进去，保证后文接上文。

**更新机制**
- `use_cache`、`max_abstraction_num`、`language` 都是显式开关。
- 章节写作是按顺序累积前文摘要的，所以章节之间不是孤立的。

**未验证项**
- 我没有实际跑生成命令，只是读了源码和示例文档树。

**可复用点**
- 这是最适合借来回答“这个功能怎么运行”的模板，因为它把“运行链”本身当作章节骨架。

**来源**
- [https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge)
- [本地 README.md](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/README.md)
- [本地 main.py](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/main.py)
- [本地 flow.py](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/flow.py)
- [本地 nodes.py](/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/nodes.py)

### 3) codebase-to-course

**功能识别**
- 这是最接近“把仓库做成课程网站”的项目。
- 它不是单个 markdown，而是一个可直接浏览的 HTML 课程站点。

**真实输出**
- 输出目录固定包含：
  - `styles.css`
  - `main.js`
  - `_base.html`
  - `_footer.html`
  - `build.sh`
  - `briefs/`
  - `modules/`
  - `index.html`
- `modules/*.html` 只放 `<section class="module">`，不放完整 HTML 壳。

**章节树 / 模板字段**
- `Module Brief` 的字段非常明确：
  - Teaching Arc
  - Code Snippets
  - Interactive Elements
  - Reference Files
  - Connections
- 这其实就是你当前页面最应该学的结构。

**执行链**
- 先理解代码库，再设计课程，再写模块 brief，再写模块 HTML，最后 `build.sh` 装配成 `index.html`。
- complex codebase 会先写 briefs，这样后续写模块的人不需要重读完整代码库。

**更新机制**
- `styles.css` / `main.js` 不允许重写，只能复制引用版。
- brief 可以在生成后删除，模块之间靠导航点和链接串起来。

**未验证项**
- 我没有执行 `build.sh` 生成页面，只核对了协议和模板。

**可复用点**
- 如果你要把“功能章节”做得不空泛，最应该抄的是它的 brief 字段，而不是视觉风格。

**来源**
- [https://github.com/zarazhangrui/codebase-to-course](https://github.com/zarazhangrui/codebase-to-course)
- [本地 SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md)
- [本地 references/module-brief-template.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/module-brief-template.md)
- [本地 references/content-philosophy.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/content-philosophy.md)
- [本地 README.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/README.md)

### 4) learn-codebase

**功能识别**
- 这不是“生成教程页面”的项目，而是“让你学会提问”的 Socratic 教学技能。

**真实输出**
- 核心输出不是网页，而是 `.claude/learning-journal.md`。
- journal 的字段固定为：
  - Focus & Goals
  - Concept Mastery Map
  - Open Questions
  - Spaced Review Queue
  - Aha Moments
  - Session Log

**执行链**
- 先检查 journal 是否存在。
- 新项目则创建 journal。
- 再做兴趣发现、预测式提问、追问、复盘。

**更新机制**
- 有 `setup_done` 标记，避免每次重复提示关闭答案建议。
- 会按掌握度和复习间隔做间隔重复。

**可复用点**
- 这套技能最值得借的是“如何逼出理解缺口”，不是输出格式。
- 如果你想让功能章节不空，你可以把每一节后面都接一个“你会怎么改？”或“如果失败会怎样？”的问题。

**未验证项**
- 没有实际跑终端问答会话，只读了技能和模板。

**来源**
- [https://github.com/ktaletsk/learn-codebase](https://github.com/ktaletsk/learn-codebase)
- [本地 SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/SKILL.md)
- [本地 QUESTION-PATTERNS.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/QUESTION-PATTERNS.md)
- [本地 JOURNAL-TEMPLATE.md](/Volumes/T7/workspace/ontology/graph/repo/learn-codebase/JOURNAL-TEMPLATE.md)

### 5) CodeWiki

**功能识别**
- 这是“仓库级文档生成器”，重点是架构感知和增量更新。

**真实输出**
- 文档目录里最关键的是：
  - `overview.md`
  - `module_tree.json`
  - `first_module_tree.json`
  - `metadata.json`
  - 各模块 `*.md`
- `overview.md` 负责仓库总览，子模块文档负责局部职责。

**章节树 / 模板字段**
- 主文档结构明确是：
  - Brief introduction and purpose
  - Architecture overview with diagrams
  - Sub-module references
  - Visual documentation
- 子模块文档结构也是固定的：简介 -> 架构图 -> 依赖 -> 关联模块 -> 代码例子。

**执行链**
- 先构建依赖图。
- 再做模块聚类和 super-group。
- 再按 leaf-first 顺序生成模块文档。
- 父模块和仓库总览最后生成。

**更新机制**
- `metadata.json` 里存 `commit_id`。
- `--update` 和 `--compare-to` 会对比提交差异。
- 变更文件会触发受影响模块失效，`overview.md` 也会重建。
- 这里还有一个很重要的细节：已有的 `first_module_tree.json` 不会被随便覆盖。

**未验证项**
- 我没有打开最终 HTML viewer 的完整页面，只确认了输出文件和更新路径。

**可复用点**
- 如果你想让教程章节“能跟着代码变更更新”，这是最值得借的项目。

**来源**
- [https://github.com/FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki)
- [本地 README.md](/Volumes/T7/workspace/ontology/graph/repo/codewiki/README.md)
- [本地 codewiki/src/be/documentation_generator.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/src/be/documentation_generator.py)
- [本地 codewiki/src/be/prompt_template.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/src/be/prompt_template.py)
- [本地 codewiki/codewiki/src/config.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/src/config.py)
- [本地 codewiki/cli/commands/generate.py](/Volumes/T7/workspace/ontology/graph/repo/codewiki/codewiki/cli/commands/generate.py)

### 6) SourceBridge

**功能识别**
- 这是“requirement-aware field guide”系统，不只是文档生成，而是把仓库变成可追踪、可更新、可检索的知识地图。

**真实输出**
- 产物不是单一文档，而是一组 field guides：
  - cliff notes
  - learning paths
  - code tours
  - workflow stories
  - system overview
  - API reference
  - glossary

**章节树 / 模板字段**
- 页面前置元数据非常关键：
  - `page_id`
  - `template`
  - `audience`
  - `dependencies`
  - `stale_when`
- 正文不是纯 markdown，而是被 `<!-- sourcebridge:block ... -->` 包起来的块。

**执行链**
- 先索引仓库。
- 再按模板生成不同类型的 field guide。
- 再在 Web、MCP、VS Code 中呈现。

**更新机制**
- `stale_when` 可以基于签名变化失效。
- 还有缓存、影响分析、变更报告。

**未验证项**
- 没有完整执行它的生成流程，但样例文档已经足够说明输出协议。

**可复用点**
- 如果你的教程想强调“功能页面何时过期、为何需要重跑”，SourceBridge 是最好的模板。

**来源**
- [https://github.com/sourcebridge-ai/sourcebridge](https://github.com/sourcebridge-ai/sourcebridge)
- [本地 README.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/README.md)
- [本地 GETTING-STARTED.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/GETTING-STARTED.md)
- [本地 samples/wiki-example/test-repo.system_overview.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/samples/wiki-example/test-repo.system_overview.md)
- [本地 samples/wiki-example/test-repo.arch.internal.auth.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/samples/wiki-example/test-repo.arch.internal.auth.md)
- [本地 samples/wiki-example/test-repo.api_reference.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/samples/wiki-example/test-repo.api_reference.md)
- [本地 samples/wiki-example/test-repo.glossary.md](/Volumes/T7/workspace/ontology/graph/repo/sourcebridge/samples/wiki-example/test-repo.glossary.md)

## 四、你现在这个教程最该抄的“功能章节输出契约”

如果你要把“每个功能”讲清楚，我建议每一节都固定输出下面这 9 个字段。这个字段集是上面 6 个项目里重复出现最多、最能防止空话的部分。

| 字段 | 作用 | 最接近的参考项目 |
|---|---|---|
| `触发方式` | 谁点、谁调、谁开始 | codebase-to-course / PocketFlow |
| `功能定位` | 它负责什么，不负责什么 | CodeWiki / SourceBridge |
| `输入` | 接什么数据、文件、路由、任务 | DeepWiki-Open / CodeWiki |
| `执行链` | 1 -> 2 -> 3 的顺序 | PocketFlow / DeepWiki-Open |
| `模块角色` | 谁负责什么 | SourceBridge / CodeWiki |
| `输出物` | 页面、章节、JSON、Markdown、图 | 全部项目 |
| `例子` | 一个具体案例或调用 | codebase-to-course / SourceBridge |
| `更新条件` | 什么时候重建、失效、缓存命中 | CodeWiki / SourceBridge / learn-codebase |
| `证据与未知` | 哪些是源码证据，哪些只是推断 | 全部项目 |

### 推荐章节骨架

1. 这是什么功能
2. 谁会触发它
3. 它吃什么输入
4. 它经过哪些步骤
5. 它最后输出什么
6. 它和别的功能怎么协作
7. 一个具体例子
8. 什么时候需要重跑 / 会失效
9. 这部分我确认了什么，哪些还没验证

## 五、最适合直接借到你当前页面的两个项目

1. **如果你想要“真正的教程章节格式”**，优先抄 `codebase-to-course`。
   - 它最擅长把功能拆成教学弧线、代码块、交互元素、连接关系。

2. **如果你想要“功能如何运行的协议”**，优先抄 `PocketFlow Code2Tutorial` 和 `CodeWiki`。
   - 前者强在章节生成链条。
   - 后者强在模块树、依赖图和增量更新。

3. **如果你想要“功能页面的过期/刷新规则”**，优先抄 `SourceBridge`。
   - 它把 `stale_when`、依赖范围、模板类型写得最清楚。

4. **如果你想要“逼用户真的理解”**，优先抄 `learn-codebase`。
   - 它告诉你怎么通过提问，把空洞解释变成可验证理解。

## 六、这次研究的限制

- 我只做了源码/模板/样例文档的只读调研，没有运行完整生成流程。
- `DeepWiki-Open` 和 `CodeWiki` 的完整 UI 交互没有在本轮里重新点击验证。
- 但就“每个功能的要求输出是什么”这个问题来说，已经足够抽出稳定的契约字段了。

## 七、你接下来最可直接改的方向

把你当前教程里每个功能章节改成这三层：

1. **功能定义层**：这个功能是谁触发、解决什么问题。
2. **运行链层**：输入 -> 中间步骤 -> 输出。
3. **证据层**：对应源码文件、配置字段、输出文件、更新条件。

只要这三层补齐，你现在这类“看完还是不知道怎么跑”的问题，基本就会消失。
