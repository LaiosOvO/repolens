# 六个基准仓库 + 一个兼容性仓库：完整克隆与固定版本清单

> 核验时间：2026-08-10。本文只记录本地参考仓的身份与可复现性，不代表 Repo Teacher 已通过生产审计。

## 结论

七个测试仓库都位于 `/Volumes/T7/workspace/ontology/graph/repo`，都是可解析历史的完整 Git clone，`git rev-parse --is-shallow-repository` 均返回 `false`。前六个是固定 curated 基准；`waku-agent` 是用户新增的真实兼容性与泛化测试仓，不会在没有单独源码审计清单时伪装成 curated 技术选型事实。产品中的可信结论必须同时绑定仓库远端、HEAD、工作树状态、源码路径和内容摘要；仅凭目录名匹配不能进入可信结果。

| 本地目录 | Origin | 核验 HEAD | 完整 clone | 工作树说明 |
| --- | --- | --- | --- | --- |
| `sourcebridge` | `https://github.com/sourcebridge-ai/sourcebridge.git` | `2a128bf0c8461fae91d2b424d9168ddf205bb11b` | 是 | 保留用户已有的 `D LICENSE`，Repo Teacher 不恢复或覆盖 |
| `pocketflow-code2tutorial` | `https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge.git` | `05b24cbbb0fe409c5e23c9791f0342f07524ffdc` | 是 | 核验时 clean |
| `openwiki` | `https://github.com/langchain-ai/openwiki.git` | `7531d615216e8cbccf464f66cfbbae3668871c84` | 是 | 核验时 clean |
| `understand-anything` | `https://github.com/Egonex-AI/Understand-Anything.git` | `fe8c5bc591716aafd79b4765549328f08ef5a52e` | 是 | 核验时 clean |
| `codeboarding` | `https://github.com/CodeBoarding/CodeBoarding.git` | `8c3f2218c3ecab1294902db5914f5e526f78524d` | 是 | 核验时 clean |
| `deepwiki-open` | `https://github.com/AsyncFuncAI/deepwiki-open.git` | `4181daa5ebde79a1baf8e92a09dd874f8b74411b` | 是 | 核验时 clean |
| `waku-agent` | `https://github.com/ShenSeanChen/waku-agent.git` | `75b0a6d27a19009b0482c877def3eb124181f121` | 是 | 核验时 clean；MIT；作为第七个兼容性测试仓 |

## 参考边界

- SourceBridge：增量索引、证据门、学习路径与代码导览的机制基准；采用合同与设计思想，不复制源码。
- PocketFlow Code2Tutorial：从仓库事实到教程章节的产品流程基准。
- OpenWiki：结构骨架、coverage critic、页面与链接闭包的基准。
- Understand Anything：结构指纹、变更分级、图与消费型 Skill freshness 的基准。
- CodeBoarding：LSP 位置语义、组件聚类、增量边重验证与缓存回滚的基准。
- DeepWiki-Open：Wiki、Codemap、citation 与 CodeViewer 交互的基准。
- Waku Agent：不进入现有 48 项 curated 排名；用于验证 Python 本地 Agent 仓的 loop、graph、memory、gateway、eval、HTML、模块定位和 cold/warm 增量行为。独立结果见 [Waku Agent 兼容性审计](waku-agent-index-compatibility.md)。

## 发布门

正式报告重生成时必须重新核验上述身份。任一仓库 HEAD、remote、工作树或证据文件内容与 curated 清单不一致时，对应方案必须降级为未验证，不能沿用旧的“当前推荐”。

## 补充研究仓库（不进入六仓 curated 排名）

以下仓库是 2026-08-10 GitHub / X / Skills 扩展研究中新增的完整 clone。它们用于改进“如何把代码仓库讲给人看”的产品方法，不会自动成为正式技术选型结论。

| 本地目录 | Origin | 核验 HEAD | 完整 clone | 采用边界 |
| --- | --- | --- | --- | --- |
| `codewiki` | `https://github.com/FSoft-AI4Code/CodeWiki.git` | `a61f0f2b608d6972ca967fd60447280ad6100fd3` | 是 | 仓库未声明 License；只参考层级功能树、叶子文档和父级综合方法 |
| `gitnexus` | `https://github.com/abhigyanpatwari/GitNexus.git` | `49c5b7d81fd5173771b31e7a136f33fde281bd70` | 是 | PolyForm Noncommercial 1.0.0；只作研究与非商业验证，不进入商业产品复制路径 |
| `codebase-to-course` | `https://github.com/zarazhangrui/codebase-to-course.git` | `ff8837ecf8e9f6ce9874ffa42e42633394a52a00` | 是 | 仓库未声明 License；只参考 product-first 课程编排和代码↔自然语言交互 |
| `learn-codebase` | `https://github.com/ktaletsk/learn-codebase.git` | `cbc0304609e76041f7f29b3ae9a1e3f1a16e07ad` | 是 | MIT；可复用主动回忆、预测问题与学习日志的 Skill 方法 |
| `codegraph-ai` | `https://github.com/codegraph-ai/CodeGraph.git` | `489ccf1612555510f8367e3e673181f6a1275fe4` | 是 | Apache-2.0；可作为多语言语义图与 MCP 查询 PoC 候选 |
| `serena` | `https://github.com/oraios/serena.git` | `946ad9817875cbf46b308423296c33eb65e3e728` | 是 | MIT；作为 live LSP 语义查询/编辑专项参考，不把付费 JetBrains 能力、任务编排或沙箱能力算入开源核心 |

这些补充仓的事实与社区证据见 [代码仓库教学、Skills 与社区研究](../research/repository-teaching-skills-and-community.md)。GitHub star 或 X 热度只用于发现需求，不能替代许可证、源码和测试审计。
