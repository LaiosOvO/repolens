# 纯 Skill 阶段合同

| 阶段 | 读取 | 必写产物 | 通过条件 |
|---|---|---|---|
| context | Git 身份、README/docs、manifest、工程树 | `00-context.md` | 项目声明、用户表面、主要模块和外部系统均出现 |
| project | context + 少量关键源码 | `01-project.md` | 一句话本质、核心概念、真实旅程、概念图 |
| capabilities | context + project | `02-capabilities.md` | 功能不限量；五类覆盖账本闭合 |
| implementation | 单个功能 + 对应关系查询 | `03-implementation/NN-*.evidence.md` 与 `.md` | 一功能一证据包一融合章节 |
| engineering | context + 跨功能事实 | `04-engineering.md` | 前后端、目录、进程、Worker、数据、部署 |
| render | 上述全部 Markdown | `05-report.md`、`index.html`、`performance.md` | 导航、图、证据、章节与待核验项闭合 |

## Context

1. 固定 commit/branch/remote；非 Git 仓库记录目录 manifest。
2. 先读产品声明与顶层工程树，不遍历依赖、构建产物、二进制和密钥文件。
3. 仓库存在 `.codegraph/` 时先使用 CodeGraph；否则使用语言 AST/LSP、引用搜索和源码阅读建立等价关系事实。
4. 分别收集：用户旅程与业务对象、业务入口与可见结果、Worker/状态/集成/部署。

## Capabilities

先列产品承诺和真实用户动作，再做能力归并。每个能力必须有独立用户价值、开始条件和可见结果；模块或页面不能单独成为功能。按用户认知顺序排序，而不是按目录顺序。

## Implementation

对每个能力单独查询，不重扫整仓。查询入口、核心转换、状态读写、路由条件、循环/并发、Worker 交接、失败与结束。只读取查询命中的必要源码。各能力可并发取证和写作，但最后由当前 agent 统一语气与结构。

## 恢复与耗时

每阶段开始、结束时记录 wall time 到 `performance.md`。已经存在的阶段只有在源码身份与其输入未变化、章节合同仍满足时才复用。某个功能失败时保留其他功能文件；再次执行只补失败项。不得为“变好”而重复启动模型审校。
