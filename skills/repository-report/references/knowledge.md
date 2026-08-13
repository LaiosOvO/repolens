# Markdown、HTML 与问答知识包合同

本合同让一次仓库分析同时产生可阅读报告和可继续问答的持久知识，而不是只剩一个不可复用的 HTML。知识目录由业务入口台账、系统能力台账和证据闭包决定；模型不得只凭文件树自由挑选少量主题。

## 1. 必写产物

```text
OUTPUT/
  report.md
  index.html
  knowledge/
    index.md
    source-catalog.md
    sources/{repository-relative-path}
  stages/
    00-context.md
    00-run-manifest.md
    00-codegraph.md
    01-project.md
    02-business-entries.md
    02-system-capabilities.md
    02-product-surfaces.md
    02-capabilities.md
    02-evidence-plan.md
    03-implementation/*.evidence.md
    03-implementation/*.md
    04-engineering.md
    05-report.md
```

`stages/05-report.md` 是组装阶段的权威 Markdown；通过发布门后，原子复制为根目录 `report.md`。两者正文必须一致，不能让 HTML 和 Markdown 分别总结一次。`index.html` 只排版同一份已通过内容。

## 2. 起始文档快照

把 context/project 阶段实际用于确定项目定位、业务声明、使用方式、架构和运行配置的公开文本保存到 `knowledge/sources/`，保持仓库相对路径。默认包括实际读过的：

- `README*`、`CONTRIBUTING*`、公开 LICENSE/SECURITY/architecture/overview/getting-started；
- docs 导航入口及其直接引用的产品、架构、部署文档；
- package/workspace manifest 与公开 example config；
- 菜单、路由、命令和协议的声明性注册文件，只有当它们确实作为发现输入被读取时才保存。

不得复制 `.env`、token、cookie、credential、私钥、用户数据、数据库、媒体、二进制、依赖目录或构建产物。疑似 Secret 的文本不进入知识包；只在 catalog 中记录 `excluded-sensitive`，不记录值。大文件或生成文档必须记录大小与排除理由，不得为了“完整”无界复制。

快照文件保持原始字节内容；不在副本内加标题或注释。`source-catalog.md` 记录：

| `source_doc_id` | 仓库相对路径 | 知识副本 | 文档角色 | 源码快照 | 内容摘要 | 被哪些阶段/knowledge ID 使用 | 状态 |
|---|---|---|---|---|---|---|---|

状态使用 `snapshotted`、`excluded-sensitive`、`excluded-binary`、`excluded-size`、`unreadable`。实际读过的公开起始文档若既没有快照也没有排除记录，停止发布。

## 3. `knowledge/index.md`

这是右侧问答、后续比较和任务生成的检索入口。按下列类型列出所有知识单元：

- `source-document`：保存的起始文档；
- `business-entry`：菜单、路由、命令、动作等叶子；
- `product-surface`：归并后的用户结果；
- `business-capability`：报告中的核心业务功能；
- `system-capability`：系统机制与不变量；
- `engineering-area`：前端、后端、Worker、数据、部署等工程边界；
- `evidence-pack`：逐功能证据与因果账本。

每行必须包含：

| `knowledge_id` | 类型 | 标题 | Markdown 锚点/文件 | HTML 锚点 | 直接源码引用 | 关联 knowledge IDs | 支持边界 |
|---|---|---|---|---|---|---|---|

ID 在同一源码快照中稳定，Markdown 标题和 HTML `id` 必须能直接定位。业务功能必须关联其 entry/surface/system/evidence；系统能力必须关联消费者或 `platform-support`。这样问答可以先检索知识单元，再沿关系补上下游，而不是只做相似文本召回。

## 4. 问答读取合同

本 Skill 只产出知识包，不伪装已经实现在线聊天后端。任何阅读器或后续 Agent 使用它问答时必须遵守：

1. 先固定 `source_snapshot` 与 `skill_contract`；知识包过期时明确提示，不混用新源码。
2. 按问题先检索 `knowledge/index.md` 的类型、标题和关联 ID，再读取命中的 Markdown/evidence/source snapshot；不要把整个仓库无界塞入 Prompt。
3. 回答技术或业务结论时引用 `knowledge_id` 和仓库相对路径/行范围；点击引用能打开报告章节或源码证据。
4. 区分 `verified-runtime`、`partial`、`declared-only`、`external`、`unknown`，不得用 README 声明补齐运行证据。
5. 多轮问答保留问题、命中的 knowledge IDs、源码快照和最终引用；模型回答本身不是新的源码事实。
6. “据此生成 Spec/Ticket”必须引用选中的业务入口、业务 capability、系统 capability 和不变量；未选择的参考项目能力不能自动进入需求。

若后续阅读器提供右侧实时问答，最小接口应是：当前仓库/快照、当前章节 knowledge ID、用户问题、可选选中源码范围；返回流式文本、引用 knowledge IDs、源码路径/行和 `verified/unknown` 状态。provider、模型和传输协议由阅读器实现决定，不写死在本 Skill。

## 5. 发布一致性

发布前机械核对：

```text
report.md 正文 = stages/05-report.md 正文
HTML 中每个核心章节都有 knowledge_id 对应的 id
knowledge/index.md 的 Markdown/HTML 链接全部存在
每个 business capability 关联 entry + surface + system + evidence
每个适用 system capability 有 consumer 或 platform-support
每个已读起始文档已快照或有安全排除记录
知识包 source_snapshot = run manifest source_snapshot
```

任何链接、计数或快照身份不一致时，保留已完成阶段，停止覆盖 `report.md` 与 `index.html`。
