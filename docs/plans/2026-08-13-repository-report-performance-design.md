# Repository Report 性能设计

## 目标

在不减少业务功能覆盖、核心功能数量和逐功能底层证据的前提下，把同一源码快照的报告生成压到 3–5 分钟，把首次小/中型仓库控制在 5–12 分钟；继续保持纯 Skill，不新增 Python、JavaScript、Shell helper 或报告 CLI。

## 根因

现有流水线的主要耗时不是 CodeGraph，而是同一事实被重复消费：项目定位与 surface 各读一次产品入口，每个功能各自查询公共 runtime/store/provider，engineering 再扫跨模块事实，render 最后再次总结全部正文。并行如果仍给每个单元整仓上下文，只会放大模型排队和重复读取。

## 采用方案

1. 用 `00-run-manifest.md` 记录源码、Skill、CodeGraph 和阶段输入指纹，按阶段与功能单元局部复用。
2. project 与 surface 共用一次产品读取；capability 只消费 surface ledger。
3. 增加 `02-evidence-plan.md`，公共运行事实只查询一次，每个功能只拿自己的关系与源码路径。
4. 功能章最多 3 路并发，禁止按文件/符号启动 Agent 和递归分派。
5. engineering 复用公共事实；render 只组装 Markdown，不再读源码或重新总结。

## 拒绝方案

- 删除 evidence 字段换速度：会直接破坏技术选型用途。
- 固定 32 个分片或一功能一 Agent：上下文重复、排队和汇总成本更高。
- 全局语义返修循环：不可预测且会让已通过阶段反复失效。
- 新增生成脚本：违背纯 Skill 与跨 Coding CLI 使用边界。

## 验证

静态验证 Skill 元数据、引用闭包和纯 Markdown 文件边界；下一次真实仓库执行时以 manifest/performance 的 wall time、query 数、源码读取数、并发峰值和 cache hit 证明效果，不用目标值冒充实测。
