# Understand Anything 源码阅读记录

## 固定版本与本机位置

- 上游仓库：<https://github.com/Egonex-AI/Understand-Anything>
- 本机完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/understand-anything`
- 固定提交：`fe8c5bc591716aafd79b4765549328f08ef5a52e`
- 分支：`main`
- clone 类型：`git rev-parse --is-shallow-repository = false`
- origin：`https://github.com/Egonex-AI/Understand-Anything.git`

本机 clone 是非 shallow 的完整 Git 仓库，工作树干净。2026-08-12
尝试重新 fetch 时外部 GitHub 连接失败；现有本地 `HEAD` 与已保存的
`origin/main` 都是上述提交。本记录以该固定版本为依据，不冒充在线最新提交。

## 它是什么

Understand Anything 是一个“确定性结构提取 + 并发语义 Agent + 图合并与审校 +
持久化知识图 + Dashboard”的代码库理解流水线。核心产物是
`.ua/knowledge-graph.json`，不是一段临时模型回答。

## 实际工程组织

| 路径 | 责任 |
| --- | --- |
| `understand-anything-plugin/src/index.ts` | 极薄公共导出层 |
| `skills/understand/SKILL.md` | 0–7 阶段运行协议、人工确认点、失败与恢复语义 |
| `agents/*.md` | scanner、file analyzer、architecture、tour、review 等独立 Agent 合同 |
| `skills/understand/*.mjs|*.py` | 确定性扫描、批次、结构提取、图合并、fingerprint |
| `packages/core/src/types.ts` | 稳定领域模型：node、edge、layer、tour、project meta |
| `packages/core/src/schema.ts` | 图验证、修复、清洗与错误报告 |
| `packages/core/src/fingerprint.ts` | 文件结构 fingerprint 与增量变更判断 |
| `packages/core/src/staleness.ts` | 图新鲜度与影响传播 |
| `packages/dashboard` | 消费最终图的独立查看器 |
| `.ua/intermediate/*.json` | 可复跑、可审计的阶段产物 |

## 真实 Pipeline

1. **Pre-flight**：固定项目根、Git 提交、输出目录、语言和忽略规则。
2. **Scan**：生成 `scan-result.json`，确定文件、语言、框架、import map。
3. **Batch**：按语义依赖而不是固定文件数生成 `batches.json`。
4. **Analyze**：最多 5 个 file-analyzer 并发，每批先运行 tree-sitter/专用解析器，
   再由模型补语义；输出 `batch-*.json`。
5. **Assemble review**：确定性合并节点/边、去重、丢弃悬空边，再独立审校。
6. **Architecture**：独立生成 `layers.json`，不让文件 Agent 自行决定全局分层。
7. **Tour**：基于最终图生成教学顺序 `tour.json`。
8. **Review**：默认确定性校验，可选 LLM graph reviewer。
9. **Save**：先写最终 graph，再成功生成 fingerprints，最后才写 `meta.json`；
   防止半完成运行被误认成新鲜基线。

## RepoLens 采用

| Understand Anything 机制 | RepoLens 采用方式 |
| --- | --- |
| 极薄入口 | `cli.py` 只保留参数和路由 |
| 稳定 core types/schema | `schemas/` + pipeline contracts + deterministic validators |
| 确定性扫描先于模型 | source snapshot → index/CodeGraph → bounded evidence packet |
| 语义批次并发 | business-domain shards，最多 4 路并发 |
| Agent 独立合同 | 中文 `agents/*.md`，每个写清输入、输出、Good/Bad、失败语义 |
| 中间产物 | `pipeline/01..06-*.json`、inventory validation、run manifest |
| Assemble/review 独立关卡 | capability reviewer + human readability reviewer |
| Architecture/Tour 后置 | project overview 与 chapter writer 只消费已确认 inventory |
| fingerprint 后提交 meta | source manifest + cache key + generation manifest 后原子发布 |

## RepoLens 不照抄

- 不把文件、类、函数作为人类报告的第一层；第一层是业务能力。
- 不把 858 行 Skill 当生产执行引擎；Skill 只保留人工确认流程，Python pipeline
  才是可测试的执行所有者。
- 不让模型自行重扫整仓；每个 Agent 只能读取有界 evidence packet/source slice。
- 不让示例、健康检查、路由、鉴权或 UI primitive 自动升级为核心业务功能。

## 对当前重构的直接约束

1. `cli.py` 不包含 SQL、Prompt、Schema、模型 transport、批次或合并算法。
2. `pipeline/` 拥有证据获取、路径合同、模块分类、inventory/report synthesis。
3. `commands/` 拥有应用用例与发布事务。
4. `providers/` 拥有 Codex/OpenCode/DeepSeek 的执行与 JSON 解码。
5. `prompts/`、`agents/`、`schemas/` 都是版本化 package resources。
6. 每个阶段必须有机器可读产物、校验结果、失败退出和可恢复边界。
