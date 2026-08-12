# ADR-0001：采用 Understand Anything 启发的分阶段生产流水线

## 状态

Accepted

## 背景

RepoLens 需要把任意仓库转化为给技术决策者阅读的业务功能报告。用户要求：

- 先用 CodeGraph/静态分析建立关系证据，再由模型识别业务功能；
- Prompt、Agent、Schema、Provider 和 CLI 分离；
- 功能清单先人工确认，再生成机制章节与 HTML；
- 大仓库支持有界并发、缓存、进度、失败恢复；
- 每个阶段可单测，完整运行可审计，发布不能混代；
- `index.html` 先讲项目、架构和业务功能，再下钻源码。

单文件 CLI 与一次性长 Prompt 无法满足这些要求。

## 决策

采用分层单体（modular monolith）和持久化阶段流水线：

```mermaid
flowchart LR
    A["源码快照"] --> B["CodeGraph + 语言分析器"]
    B --> C["有界 Evidence Packet"]
    C --> D["并发业务域 Inventory Agent"]
    D --> E["确定性 Assemble + Capability Review"]
    E --> F["人工确认功能清单"]
    F --> G["Project Architecture Agent"]
    G --> H["并发 Chapter/Tour Agent"]
    H --> I["Evidence + Human Readability Review"]
    I --> J["Fingerprint + Manifest + 原子发布"]
```

### 模块边界

| 模块 | 唯一责任 |
| --- | --- |
| `cli.py` | 参数定义与命令路由 |
| `commands/` | inventory/report/index 等应用用例与事务边界 |
| `pipeline/codegraph.py` | CodeGraph 生命周期与有界关系切片 |
| `pipeline/paths.py` | 安全仓库相对路径合同 |
| `pipeline/module_scope.py` | 确定性模块分类 |
| `pipeline/evidence_packets.py` | 全局、分片、章节 Evidence Packet 与隔离源码切片 |
| `pipeline/inventory_contracts.py` | Inventory 规范化、scope 闭包、确定性合并 |
| `pipeline/grouping.py` | 细粒度候选到人类业务功能的语义归组 |
| `pipeline/report_contracts.py` | 项目总览与章节证据闭包 |
| `pipeline/synthesis.py` | 有界并发、缓存协调与阶段顺序；不再拥有 Prompt/Provider/证据算法 |
| `pipeline/stage_artifacts.py` | 中间产物、validation 与 run manifest |
| `providers/` | 模型 transport、超时、重试、严格 JSON 解码 |
| `prompts/` | 版本化模型指令 |
| `agents/` | 中文角色与输入/输出/质量/失败合同 |
| `schemas/` | 公开 JSON Schema 与确定性交叉验证 |
| `renderers/` | 已验证模型到离线 HTML；不重新判断功能 |

### 非功能要求

- **正确性**：任何越出 evidence scope 的路径/ID fail closed。
- **可靠性**：源码先冻结；发布采用 immutable generation + 单次 current switch。
- **可恢复性**：模型缓存必须重新校验；失败从最小阶段恢复。
- **性能**：静态分析近似 O(files + graph records)；模型按业务域最多 4 路并发。
- **安全**：模型只读 source slice；API Key 不进入参数、日志或产物。
- **可维护性**：CLI 不得包含 Prompt、Schema、SQL、模型 transport 或流水线算法。

## 影响

### 正面

- 可以单独修复功能发现、章节写作或 HTML，而不重跑所有阶段。
- 每个模型结论能追溯到稳定源码路径、行范围与 evidence ID。
- Provider 可替换，业务 Pipeline 不依赖 Codex/OpenCode/DeepSeek 细节。
- 中间产物让耗时任务可观察、可恢复、可独立审计。

### 负面

- 模块与契约数量增加，需要维护 Schema 版本和 migration 规则。
- 大仓库仍受模型延迟影响，必须严格控制 packet 上界与缓存键。
- 业务功能是语义产物，确定性校验只能证明证据闭包，不能证明所有措辞正确。

### 中性

- 保留单进程 CLI；当前没有引入消息队列或微服务，避免为假想规模过度设计。

## 备选方案

1. **一个 `cli.py` 包含全部逻辑**：拒绝；职责混合、测试补丁依赖内部符号、无法独立恢复。
2. **一个 Skill 完成全部执行**：拒绝；难以提供稳定类型、事务、缓存和机器校验。
3. **每个文件调用一次模型**：拒绝；慢、贵且缺乏全局业务能力合并。
4. **只使用 README/目录名归纳功能**：拒绝；会把营销描述与运维表面误当实现事实。
5. **立即拆微服务**：拒绝；当前本地 CLI 不需要网络分布式复杂度。

## 失败模式与缓解

| 失败 | 缓解 |
| --- | --- |
| 源码分析中途变化 | 一致源码快照与 manifest hash |
| 模型超时/无效 JSON | Provider 超时、一次受控重试、Schema fail closed |
| Shard 漏项或重复 | deterministic merge、ID partition 与 module disposition closure |
| 缓存污染 | 每次复用前 normalize + validate，cache key 绑定源码与 contract version |
| HTML 与 JSON 混代 | immutable generation，validate-before-publish，单次 current switch |
| 人类报告平铺无重点 | inventory approval、project overview、capability order、readability review |

## 参考

- [Understand Anything](https://github.com/Egonex-AI/Understand-Anything)
- `docs/references/understand-anything-reading.md`
- `skills/repository-report/references/pipeline-contract.md`
