# 自动发现“功能难点”的项目研究

目标不是“把代码讲清楚”，而是回答一个更窄的问题：**这些系统能不能自动识别某个功能里真正难的实现机制**，比如 wave scheduling、state collision、join、router、cycle、fallback、durability gap。

## 结论先行

这批系统里，没有一个已经把“难点发现”做成独立、显式、可评分的能力。它们大致分成三类：

1. **叙事/教程生成器**：DeepWiki-Open、PocketFlow Code2Tutorial、RepoAgent  
   这类系统更擅长“讲解”和“生成文档”，会把代码总结成 wiki、教程、README 或章节，但通常不会显式输出“哪个机制最难、为什么难、证据有多强”。
2. **结构抽取器**：CodeBoarding、Serena  
   这类系统更擅长“找结构”和“找引用”。它们能把模块、符号、调用关系、依赖边、索引、记忆维护起来，是做难点发现的好底座，但本身不等于难点判定器。
3. **证据驱动探索器**：Sourcegraph Deep Search / Cody  
   这是最接近“自动调查难点”的系统。它会迭代搜索、跟随引用、读历史、返回带引用的结构化答案。但它仍然更像“强调查员”，不是“难点评分器”。

如果你的目标是“每个功能都输出它的实现难点和证据”，现成系统里最有用的组合不是单选，而是：

- `Sourcegraph Deep Search` 负责发现和追问
- `CodeBoarding` 负责结构图和依赖面
- `Serena` 负责符号级定位、引用回溯、测试绑定
- `DeepWiki-Open` / `PocketFlow` / `RepoAgent` 只当作叙事输出层，而不是判定层

---

## 对比表

| 项目 | 主要输入 | 主要算法/阶段 | 主要输出 | 会不会自动发现“难点” | 绑定源码/测试能力 | 对 Waku Graph 的覆盖 |
|---|---|---|---|---|---|---|
| DeepWiki-Open | repo URL、token、RAG 上下文、 embeddings、深度研究开关 | clone -> analyze -> embeddings -> wiki/RAG -> multi-turn deep research | wiki_structure、sections、pages、importance、relevant_files、related_pages、citations | **弱**，更像多轮解释，不是难点评分 | 绑定源码较强，绑定测试较弱 | 中低，能解释功能，但不擅长自动抓 runtime 级缺陷 |
| PocketFlow Code2Tutorial | repo/dir、include/exclude、max-size、LLM | crawl -> identify abstractions -> analyze relationships -> order chapters -> write chapters -> combine | tutorial chapters、Mermaid、代码片段、章节摘要 | **弱**，抽象识别不是难点识别 | 主要绑代码片段，不绑测试 | 中低，适合讲机制，不适合判断隐藏风险 |
| RepoAgent | 整个仓库、代码文档上下文、issue/Q&A 场景 | repository-level doc generation / maintenance / update | repository-level docs、Q&A、README/文档生成 | **弱**，目标是文档生成 | 以文档/仓库级上下文为主，测试绑定不明显 | 中低，偏文档生产，不偏难点诊断 |
| CodeBoarding | 静态分析结果、代码变更、LLM 上下文 | deterministic clustering -> LLM naming -> API surface -> relation analysis -> incremental update | architecture diagrams、component docs、analysis.json、.codeboarding markdown | **中弱**，能暴露结构复杂度，但不显式打分 | 绑定源码强，能回到引用行；测试绑定弱 | 中上，适合抓 router/join/cycle 这类结构型复杂点 |
| Sourcegraph Deep Search / Cody | 自然语言问题、全仓库、code search、code navigation、git history | iterative search -> follow references -> summarize with citations | structured answer、code snippets、source links、history-backed explanation | **中强**，最接近“调查难点”，但仍不输出独立难度模型 | 绑定源码和历史强，测试绑定取决于仓库是否可查到 | 最强，尤其适合 wave/state/join/router/cycle/fallback 的证据追踪 |
| Serena | project index、symbol graph、memory、文件变更 | project create/index -> onboarding/memory -> symbol/reference query -> file-system sync | symbol lookup、reference list、rename/replace、memory docs、stale-ref report | **弱**，它是证据底座，不是判定器 | 绑定源码极强，符号级；可间接绑定测试文件 | 中上，适合定位和串联具体函数/测试，但不自动评分 |

---

## 逐项目证据

### 1) DeepWiki-Open

**它做什么**

DeepWiki-Open 的公开说明把核心目标写成“生成 wiki / 提问 / 深度研究”。中文 README 明确列出：

- 克隆并分析仓库
- 创建代码嵌入做检索
- 用上下文感知 AI 生成文档
- 生成图表
- 组织成结构化 Wiki
- 通过提问功能做 RAG
- 通过深度研究做多轮调查

对应证据：

- `README.zh.md:107-115`
- `README.zh.md:175-198`
- `api/prompts.py:60-120`
- `api/main.py:64-73`
- `api/repository.py:14-114`

**输出结构**

测试里能直接看到 wiki 结构契约：

- `title`
- `description`
- `sections`
- `pages`
- `rootSections`
- `importance`
- `relevant_files`
- `related_pages`

对应证据：

- `tests/backend/services/test_wiki_structure.py:9-51`
- `tests/backend/services/test_wiki_structure.py:54-88`
- `tests/backend/services/test_wiki_task.py:28-40`
- `tests/backend/services/test_wiki_task.py:125-198`

**为什么它不是“难点发现器”**

它的 deep research prompt 强调的是：

- 分多轮研究
- 先 plan，再 update，再 final conclusion
- 聚焦某个 topic
- “不要给最终结论太早”

这说明它是一个**多轮解释器**，不是一个显式的“难点判定器”。它会帮你把某个主题讲深，但不会天然告诉你“这个功能最难的是 state collision 而不是 router”。

**对 Waku Graph 的判断**

- 能做：围绕某个功能做解释，给出引用和路径
- 不强：自动识别“真正难”的实现点
- 很弱：仅靠它主动发现运行时语义问题，尤其是 durability gap

**结论**

DeepWiki-Open 可以当“章节输出层”或“问答层”，不能当“难点发现层”。

官方/源码来源：

- https://github.com/AsyncFuncAI/deepwiki-open
- `README.zh.md`
- `api/prompts.py`

---

### 2) PocketFlow Code2Tutorial

**它做什么**

PocketFlow Code2Tutorial 是典型教程生成器。README 里写得很直接：

- crawl GitHub repo 或本地目录
- build a knowledge base
- identify core abstractions
- analyze how they interact
- turn complex code into beginner-friendly tutorials

对应证据：

- `README.md:15-16`
- `README.md:98-121`
- `README.md:161-166`

**输出结构**

它的命令行参数说明了输出的控制面：

- `--repo` / `--dir`
- `--include` / `--exclude`
- `--max-size`
- `--language`
- `--max-abstractions`

它本质上是“先抽象、再排章节、再写教程”：

- 识别抽象
- 分析关系
- 排序章节
- 写章节
- 合并成最终教程

**为什么它不是“难点发现器”**

它识别的是 “core abstractions” 和 “interactions”，不是 “hardest mechanism”。
也就是说，它会告诉你“这个项目有哪些概念”和“这些概念怎么串”，但不会自动回答：

- 哪一条路径最脆弱
- 哪个边界条件最容易坏
- 哪个机制必须和测试/持久化一起看

**对 Waku Graph 的判断**

- 能做：概念层解释、模块间关系说明
- 不强：识别隐藏状态冲突、持久化缺口、故障恢复逻辑
- 低覆盖：运行时竞争、恢复语义、超时/fallback 这种问题不会自然冒出来

**结论**

PocketFlow 更像“教材工厂”，不是“难点侦察兵”。

官方/源码来源：

- https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge
- `README.md`

---

### 3) RepoAgent

**它做什么**

RepoAgent 的官方 GitHub / arXiv 说明都把它定义成 repository-level documentation generation framework：

- 主动生成、维护、更新代码文档
- 面向仓库级文档
- 还包括 issue/README 风格的自动问答能力

对应证据：

- https://github.com/OpenBMB/RepoAgent
- https://arxiv.org/abs/2402.16667
- https://arxiv.org/html/2402.16667v1

**输出结构**

从论文摘要和仓库描述能确认它的产物是仓库级文档，而不是一个显式的难点向量或难度评分。

**为什么它不是“难点发现器”**

RepoAgent 的定位是“生成、维护、更新文档”。这意味着它面向的是：

- 文档覆盖
- 仓库解释
- 交互式问答

而不是：

- 困难机制提取
- 风险排序
- 证据门控

**对 Waku Graph 的判断**

- 能做：如果你问对问题，可能解释某个机制
- 不强：自动发现最难的 runtime semantics
- 没有看到明确的“难点排序”输出契约

**结论**

RepoAgent 是“文档 agent”，不是“难点发现 agent”。

---

### 4) CodeBoarding

**它做什么**

CodeBoarding 是这批里最像“结构理解引擎”的项目之一。README 直接说它结合：

- static analysis
- LLM reasoning

来生成：

- architecture diagrams
- component-level documentation
- navigable outputs
- incremental updates

对应证据：

- `README.md:5`
- `README.md:29-35`
- `README.md:37-60`
- `README.md:94-98`
- `README.md:219-255`

**关键方法**

`agents/abstraction_agent.py` 的实现很关键：

- `step_clusters_grouping` 用确定性 Leiden / modularity peak 做顶层分组
- LLM 只负责给固定分组命名和描述
- `step_api_surfaces` 用静态调用证据分析 API surface
- `step_relation_analysis` 用组件摘要 + API surface + 静态 call evidence 做关系发现
- `run()` 明确是：聚类 -> 命名 -> API surface -> 关系 -> 引用行 -> relation endpoint index

对应证据：

- `agents/abstraction_agent.py:83-95`
- `agents/abstraction_agent.py:97-144`
- `agents/abstraction_agent.py:147-191`
- `agents/abstraction_agent.py:193-226`

**为什么它离“难点发现”更近**

它不是只生成章节，而是在做：

- 结构聚类
- 关系提取
- API surface 归纳
- 递增式更新

这些信号对于发现“难点模块”很有价值，因为难点通常伴随：

- 高内聚/高耦合簇
- 关系密度高
- API surface 边界复杂
- change delta 反复触发

但它仍然没有一个明确的“difficulty score”或“hard mechanism”字段。

**对 Waku Graph 的判断**

- 较强：router / join / cycle 这类结构型复杂点
- 中等：state collision、fallback 路径
- 较弱：durability gap 这种需要测试/运行时/语义证据才能定性的点

**结论**

CodeBoarding 是结构层最佳候选之一，但它更适合做“难点候选生成器”，不是最终裁决器。

本地证据：

- `README.md`
- `agents/abstraction_agent.py`
- `codeboarding_workflows/analysis.py`
- `agents/dependency_discovery.py`

---

### 5) Sourcegraph Deep Search / Cody

**它做什么**

Sourcegraph 官方文案最明确：Deep Search 是一个在整个代码库上推理的 agent，会：

- 跨仓库搜索
- 跟随代码和历史
- 显示每个答案背后的来源
- 用自然语言回答研究类问题

官方说明还强调它会：

- iterative searches
- follow references
- use code search / code navigation
- give cited answers

对应来源：

- https://sourcegraph.com/deep-search
- https://sourcegraph.com/blog/introducing-deep-search
- https://sourcegraph.com/blog/deep-search-goes-ga-now-with-role-based-permissions
- https://sourcegraph.com/blog/semantic-code-search-what-it-is-and-how-it-works
- https://sourcegraph.com/blog/the-right-tool-at-the-right-time-using-sourcegraph-search-effectively

**为什么它最接近“自动识别难点”**

因为它的默认动作不是“总结全文”，而是：

- 先问问题
- 再迭代搜索
- 再沿引用链深入
- 再看 history
- 再合成带引用的解释

这和“找难点”的工作流高度一致。真正的难点通常不是某一个关键词，而是：

- 跨文件引用链
- 依赖链
- 历史上的改动痕迹
- 某个 guard / fallback / test 是否真的存在

Deep Search 正好擅长把这些证据串起来。

**但它仍然不是难度评分器**

它输出的是“结构化答案”，不是：

- 难度等级
- 证据权重
- 机制风险排序
- 是否已覆盖 test / runtime / history 的完整门控

所以它是**调查引擎**，不是**裁判引擎**。

**对 Waku Graph 的判断**

这套问题里，Deep Search 的覆盖最强：

- wave scheduling：能沿执行路径和引用链追
- state collision：能找共享状态、并发/合并逻辑、相关历史改动
- join：能查分支聚合、合流点、路由条件
- router：很强，引用追踪非常适合
- cycle：很强，适合沿调用/依赖链找闭环
- fallback：很强，能找显式 fallback 分支和相关变更
- durability gap：有机会发现，但前提是代码/测试/历史里真的留了痕迹；纯运行时语义缺陷仍可能漏掉

**结论**

如果你现在就要选一个“最像难点发现”的现成系统，Deep Search 是第一名。

---

### 6) Serena

**它做什么**

Serena 的定位是“IDE for your coding agent”。它的核心是：

- project creation / activation
- indexing
- onboarding
- memories
- symbol lookup / reference lookup
- rename / replace symbol body
- file-system change sync

对应证据：

- `README.md`
- `docs/02-usage/040_workflow.md:10-13`
- `docs/02-usage/040_workflow.md:80-89`
- `docs/02-usage/040_workflow.md:111-126`
- `docs/02-usage/045_memories.md:156-174`
- `src/serena/symbol.py:810-855`
- `src/serena/ls_manager.py:266-305`

**为什么它不是“难点发现器”**

Serena 不负责给你答案，它负责让你**更快、更多证据地到达答案**。

它强在：

- 符号级定位
- 引用反查
- 索引更新
- 记忆维护

这意味着它很适合把“一个难机制”的相关证据绑起来，但它并不会自动说“这个功能难点在这里”。

**对 Waku Graph 的判断**

- 很强：定位 wave/state/join/router/cycle 对应符号和引用
- 中等：找 fallback 分支和测试
- 弱：单独判断 durability gap 的语义缺口

**结论**

Serena 是证据锚点，不是结论引擎。

---

## 采用/拒绝

### Adopted

如果要真的做“自动发现功能难点”的系统，我建议采用下面这个组合：

1. **Sourcegraph Deep Search** 作为发现引擎  
   用来提问题、追引用、看历史、产出带证据的答案。
2. **CodeBoarding** 作为结构地图  
   用来找聚类、关系密度、API surface、incremental diff。
3. **Serena** 作为证据绑定层  
   用来精确定位符号、引用、测试、文件变更。

这三层加起来，才更像一个真正的“难点发现流水线”。

### Rejected

1. **DeepWiki-Open** 作为主判定器  
   它很适合做 wiki 和多轮解释，但不适合做难度排序。
2. **PocketFlow Code2Tutorial** 作为主判定器  
   它是教程生成器，不是风险识别器。
3. **RepoAgent** 作为主判定器  
   它是仓库文档生成器，不是难点评分器。

---

## 建议的数据契约

如果你想把这件事产品化，输出不要再是“章节”，而要是“功能难点候选卡”。

```json
{
  "feature_id": "waku_graph",
  "feature_name": "Graph Workflow",
  "mechanism_candidates": [
    {
      "mechanism": "state merge / reducer",
      "difficulty_score": 0.82,
      "confidence": 0.76,
      "difficulty_tags": ["shared-state", "merge-order", "collision-risk"],
      "evidence": [
        {
          "kind": "static",
          "source": "file:///Volumes/T7/workspace/ontology/graph/repo/waku-agent-candidate/src/...",
          "symbol": "run_graph",
          "span": "L120-L214",
          "weight": 0.35
        },
        {
          "kind": "test",
          "source": "file:///Volumes/T7/workspace/ontology/graph/repo/waku-agent-candidate/tests/...",
          "symbol": "test_state_collision",
          "span": "L10-L58",
          "weight": 0.35
        },
        {
          "kind": "history",
          "source": "git",
          "span": "commit abc123..def456",
          "weight": 0.2
        }
      ],
      "gaps": [
        "No runtime trace for concurrent collision case",
        "No durability assertion across restart"
      ],
      "next_queries": [
        "find all reducer writers",
        "trace join fan-in",
        "inspect fallback path under failure"
      ]
    }
  ]
}
```

### 字段含义

- `mechanism_candidates`: 不要只给一个结论，先给候选机制
- `difficulty_score`: 不是“重要性”，而是“实现难度/出错概率/跨边界复杂度”
- `evidence`: 至少区分静态、测试、历史、运行时
- `gaps`: 还缺什么证据
- `next_queries`: 下一步要自动追的查询

---

## 证据门 / 排名规则

建议把“难点”判定分成 4 档：

- **L0**：只有摘要，没有证据
- **L1**：有代码结构解释，但没有边界/测试/历史证据
- **L2**：有源码 + 引用 + 至少一个测试或变更历史
- **L3**：有源码 + 测试 + 历史/运行时痕迹，而且能定位到具体失败模式

只有到 **L2 以上**，才允许把某个机制标成“难点候选”。  
只有到 **L3**，才允许把它标成“高风险难点”。

### 一个更实用的评分公式

```text
difficulty =
  0.35 * structural_complexity
  + 0.20 * cross_file_fanout
  + 0.15 * test_edge_density
  + 0.15 * history_churn
  + 0.10 * runtime_semantics_gap
  + 0.05 * doc_staleness
```

这不是学术真理，但足够作为产品的初版排序器。

---

## 对 Waku Graph 的具体覆盖判断

如果目标是自动找出下面这些点：

- wave scheduling
- state collision
- join
- router
- cycle
- fallback
- durability gap

我会这样分配能力：

- **Deep Search**：最适合找 router / join / cycle / fallback，也最可能把 state collision 拉到可解释层
- **CodeBoarding**：最适合暴露 router / join / cycle 的结构面，以及高耦合簇
- **Serena**：最适合把这些点落到具体符号、引用和测试上
- **DeepWiki-Open**：适合写成章节，但不适合自动发现
- **PocketFlow Code2Tutorial**：适合讲给新人听，但不适合诊断难点
- **RepoAgent**：适合生成仓库文档，不适合判定难度

对 **durability gap** 的判断最谨慎：  
这通常不是纯静态解释能可靠抓住的，必须要有测试、恢复路径、历史变更或运行时痕迹，否则很容易漏判。

---

## 相关来源

### 官方/一手网页

- DeepWiki-Open: https://github.com/AsyncFuncAI/deepwiki-open
- PocketFlow Code2Tutorial: https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge
- RepoAgent: https://github.com/OpenBMB/RepoAgent
- RepoAgent paper: https://arxiv.org/abs/2402.16667
- CodeBoarding: https://github.com/CodeBoarding/CodeBoarding
- Serena: https://github.com/oraios/serena
- Sourcegraph Deep Search: https://sourcegraph.com/deep-search
- Sourcegraph Deep Search launch post: https://sourcegraph.com/blog/introducing-deep-search
- Sourcegraph Deep Search GA post: https://sourcegraph.com/blog/deep-search-goes-ga-now-with-role-based-permissions
- Sourcegraph Deep Search explanation: https://sourcegraph.com/blog/semantic-code-search-what-it-is-and-how-it-works

### 本地源码证据

- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/README.zh.md`
- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/prompts.py`
- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/repository.py`
- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_structure.py`
- `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_task.py`
- `/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial/README.md`
- `/Volumes/T7/workspace/ontology/graph/repo/codeboarding/README.md`
- `/Volumes/T7/workspace/ontology/graph/repo/codeboarding/agents/abstraction_agent.py`
- `/Volumes/T7/workspace/ontology/graph/repo/codeboarding/codeboarding_workflows/analysis.py`
- `/Volumes/T7/workspace/ontology/graph/repo/serena/docs/02-usage/040_workflow.md`
- `/Volumes/T7/workspace/ontology/graph/repo/serena/docs/02-usage/045_memories.md`
- `/Volumes/T7/workspace/ontology/graph/repo/serena/src/serena/symbol.py`
- `/Volumes/T7/workspace/ontology/graph/repo/serena/src/serena/ls_manager.py`

