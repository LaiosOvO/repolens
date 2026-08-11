# DeepWiki-Open

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open`
- origin：`https://github.com/AsyncFuncAI/deepwiki-open.git`
- HEAD：`4181daa5ebde79a1baf8e92a09dd874f8b74411b`
- 工作树：clean
- 许可证：MIT，见 [LICENSE](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/LICENSE:1)
- 后端版本字段：见 [api/pyproject.toml](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/pyproject.toml:2)

## 一句话定位
这是一个“仓库先建索引，再生成 Wiki，再给前端实时展示”的全栈产品，重点不是静态文档，而是任务化生成和交互式阅读。

## 产品形态判断
- 形态：独立项目，后端 API + 前端 Web。
- 它不是单纯报告生成器，而是“索引、生成、查看、追问、codemap guided tour”一体化产品。
- 对你的启示：它非常适合参考“任务状态流、RAG、citations、代码查看器”这些能力，但不适合把整个前端照搬成你的最终阅读形态。

## 先看结论
- DeepWiki-Open 最有价值的是“先把 repo 变成可检索索引，再把长生成任务拆成状态机，再把结果用可点击 citations 还原到源码行”。
- 你的产品如果要让人轻松比较不同项目，DeepWiki 的强项不是最终页面文案，而是“证据链和异步任务骨架”。

## 功能清单

### 1. 仓库预热与索引准备
- 提供什么：在真正聊天、生成 wiki 或 codemap 之前，先把仓库 embedding/index 准备好，避免首次请求超慢。
- 触发到输出：前端调 `/api/repo/prepare` -> 后端检查索引是否已存在 -> 未命中就异步构建索引并持续发 SSE 心跳 -> 索引完成后返回 `done`。
- 谁消费：后续 RAG、wiki 生成、codemap 生成。
- 底层机制：`/repo/prepare` 不直接返回结果，而是以 SSE 报告 indexing progress；已经存在时走 fast path。
- 关键源码：
  [README 对产品目标的描述](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/README.md:5)
  [prepare_repo_index 路由](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/routers/repo.py:23)
  [前端 prepareRepoIndex helper](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/src/utils/prepareRepo.ts:47)
- 真实测试：
  `未见 prepare 路由的专门 pytest；更多靠任务与集成测试间接覆盖。`
- 复用判断：`复用`
- 为什么能用：你的系统后面也要分析很多仓库，这种“先预热索引，再让人进入阅读”的体验很关键。

### 2. RAG 索引与仓库检索层
- 提供什么：把仓库文件转成向量检索库，后面无论是问答还是 codemap 都不需要重新扫全仓。
- 触发到输出：repo prepare 或 codemap/wiki 任务触发 -> `RAG.prepare_retriever` -> DatabaseManager 准备文档 -> embedding 过滤 -> 建立 FAISS retriever。
- 谁消费：wiki structure 生成、chat、codemap。
- 底层机制：它会过滤 embedding 维度不一致的 document，再建检索器；并用 semaphore 限制并发 prepare 数。
- 关键源码：
  [RAG 并发与类定义](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/rag/rag.py:23)
  [prepare_retriever](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/rag/rag.py:238)
  [embedding 过滤](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/rag/rag.py:183)
- 真实测试：
  [test_rag.py](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/rag/test_rag.py:7)
  [tests/README 对测试分层的说明](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/README.md:68)
- 复用判断：`复用`
- 为什么能用：这层很适合成为你“仓库解释系统”的证据底座。

### 3. Wiki 结构先生成，再逐页生成内容
- 提供什么：不是直接写一整本 Wiki，而是先产出结构树，再按 page 逐页生成内容。
- 触发到输出：提交 wiki task -> 若无索引先建索引 -> 读取 repo 文件树和 README -> LLM 生成 `<wiki_structure>` XML -> 解析为 `WikiStructureModel` -> 再逐页生成 `WikiPage.content`。
- 谁消费：任务状态页面、WikiTreeView、最终缓存。
- 底层机制：结构阶段读 repo tree + README；生成阶段有并发控制、每页重试、单页失败回退成 error placeholder，不拖垮整任务。
- 关键源码：
  [generate_repo_wiki 状态机](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/tasks.py:212)
  [_determine_structure](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/tasks.py:315)
  [read_repo_file_tree](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/structure.py:20)
  [parse_wiki_structure](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/structure.py:142)
- 真实测试：
  [task 状态机测试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_task.py:54)
  [结构 XML 解析测试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_structure.py:41)
- 复用判断：`复用`
- 为什么能用：这非常适合你的“先大纲、再正文、再人类阅读”的目标。

### 4. 页面内容后的 citation 修正与源码落点归一化
- 提供什么：把模型吐出来的空 citation、文件路径、行号，转成真正可点的 GitHub/GitLab/Bitbucket 链接。
- 触发到输出：页面内容生成后 -> `post_process_wiki_content` 重建 `Relevant source files` -> 解析 `[README.md:1-2]()` 这类占位 -> 转成带行号锚点的真实链接。
- 谁消费：前端 wiki 页面、人类读者。
- 底层机制：不同 host 用不同行号锚点格式；本地 repo 不强行生成 web URL。
- 关键源码：
  [post_process_wiki_content](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/content.py:93)
  [generate_file_url](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/content.py:24)
  [_citation_link](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/content.py:66)
- 真实测试：
  [README.md:1-27 citation 测试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_content.py:40)
  [Sources: bare filename 解析测试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_content.py:61)
- 复用判断：`复用`
- 为什么能用：你的人类 HTML 如果没有稳定 citation，会很快失去“技术选型证据”价值。

### 5. 任务注册表、去重、SSE 进度流
- 提供什么：仓库 Wiki 生成不是一次 HTTP 阻塞请求，而是一个可查询、可加入、可缓存的长期任务。
- 触发到输出：前端提交任务 -> registry 判断是 `created`、`joined` 还是 `from_cache` -> 轮询详情或订阅 `/wiki/tasks/{id}/stream` -> 得到 `progress/done/error`。
- 谁消费：首页任务列表、详情页、后续恢复逻辑。
- 底层机制：同 repo key 的活跃任务会 join；终态任务 TTL 后移除；SSE payload 里不会泄漏 token。
- 关键源码：
  [TaskRegistry.submit](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/wiki/tasks.py:161)
  [submit_wiki_task 路由](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/routers/wiki.py:218)
  [stream_wiki_task](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/routers/wiki.py:271)
  [前端 subscribeWikiTask](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/src/utils/wikiTask.ts:139)
- 真实测试：
  [创建并完成任务](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_task.py:54)
  [重复提交 join 活跃任务](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/services/test_wiki_task.py:87)
  [SSE done/error/progress 测试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/tests/backend/routers/test_wiki_tasks_api.py:178)
- 复用判断：`复用`
- 为什么能用：你后面提到一个 idea 会拆成很多 session/work item，这套 registry + stream 是直接可参考的。

### 6. CodeMap：skeleton -> enrich -> citation grounding
- 提供什么：回答“这个仓库这条用法链怎么走”的 guided tour，而不只是静态 Wiki 页面。
- 触发到输出：用户提问 -> RAG 先取回相关源码 chunk -> 第一轮 LLM 产出 codemap skeleton（sections/steps/citations）-> 第二轮 enrich prose/diagram -> 最后用真实文件内容重算 citation 行号 -> 按 NDJSON 持续流给前端。
- 谁消费：CodeMap 组件、CodeViewer。
- 底层机制：
  先 `analyzing`；
  再 `initial_codemap`；
  再 `diagrams`；
  第二轮失败会退回 skeleton；
  最后 `_ground_citations` 用 snippet 在真实源码里重新定位。
- 关键源码：
  [codemap 模块说明](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py:1)
  [_generate_json 重试](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py:46)
  [_ground_citations](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py:201)
  [generate_codemap 主流程](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/services/codemap.py:225)
  [codemap router](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/api/routers/codemap.py:14)
- 真实测试：
  `未见 codemap 的专门 pytest；这里是源码证据充分、自动化测试不足。`
- 复用判断：`复用`
- 为什么能用：这几乎就是你要的“按功能讲实现并可点进源码”的关键参考。

### 7. 前端阅读层：结构树、Codemap、CodeViewer
- 提供什么：把上面的任务结果变成“能读”的产品，而不是只返回 JSON。
- 触发到输出：
  任务完成 -> `WikiTreeView` 展示章节树；
  codemap 流回前端 -> `CodeMap` 展示阶段状态、步骤和 citation chip；
  用户点 citation -> `CodeViewer` 拉取文件并高亮行。
- 谁消费：人类读者。
- 底层机制：前端把 codemap 三阶段进度单独建模；CodeViewer 按 cited file lazy load；citation 里有 start/end line。
- 关键源码：
  [CodeMap 阶段与 citation chip](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/src/components/CodeMap.tsx:19)
  [CodeViewer 按文件拉取并高亮行](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/src/components/CodeViewer.tsx:51)
  [WikiTreeView](/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open/src/components/WikiTreeView.tsx:45)
- 真实测试：
  `前端这些组件在当前仓库里未看到对应的单独前端测试文件；主要靠后端和少量集成层。`
- 复用判断：`需改造`
- 怎么改：你的最终阅读目标是“快速技术选型”，所以页面层要更强调“功能摘要、实现路径、可复用模块、风险”而不是 DeepWiki 这种偏浏览型结构。

## 对你产品形态的直接启示
- 对“独立项目”：强烈支持。DeepWiki-Open 证明这件事天然是一个项目，不是一条 prompt。
- 对“CLI 优先”：部分支持。它更偏 Web 产品；但你可以把后端任务骨架挪到 CLI first 形态里。
- 对“主 HTML + report/evidence/modules 附件”：强烈支持。尤其是 citation grounding、code viewer、任务状态这三块。
- 对“二期薄 Skill”：支持。skill 更像是“调用你的索引/讲解系统”的入口，而不是系统本体。

## 不建议直接照搬的部分
- 不建议直接照搬当前首页和阅读交互，它更偏“聊仓库 + 看 codemap”。
- 不建议把所有生成都压在 Web 前端场景；你的批量技术调研更适合 CLI/后台任务产物，再渲染给人看。

## 事实 / 推断 / 未知
- 事实：repo prepare、RAG、任务状态机、wiki 结构生成、页面后处理、codemap 两阶段生成、citation grounding、代码查看器都是真实存在的。
- 推断：它很适合作为你系统里的“证据检索层 + 长任务编排层 + 引文落点层”参考。
- 未知：codemap 缺少同等强度的专门自动化测试；前端阅读体验是否适合高密度技术选型，还需要你自己的信息架构重做。
