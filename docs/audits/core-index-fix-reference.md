# 核心索引修复：参考实现映射与复核边界

## 结论先行

本轮只修复核心扫描、增量复用和变更判定，不宣称整个产品已通过生产审计。实现采用三个参考项目中可验证的机制，并保持本项目的零依赖、本地文件索引边界：

1. 用全树内容哈希和严格缓存指纹决定“能否复用”，不信任缺失、篡改、跨项目或跨配置的 baseline。
2. 只复用未变化文件的分析记录；记录先按路径一次分组，避免按每个文件重复遍历全部符号、关系和诊断。
3. 结构变更判定采用保守策略：没有可比较语义分析的文件一律按结构变更处理；只有受支持分析器的符号、签名、导入和调用关系都未变化，才归为 `implementation_only`。
4. 扫描具有文件数和总读取字节预算，达到预算会确定性停止并输出诊断，不再静默生成“看似完整”的结果。
5. 扫描后用相同配置执行第二次全树扫描，并再次捕获 Git/项目快照；任一文件集合、内容哈希、预算边界或快照身份变化都会拒绝本次结果。
6. 关系 ID 在汇总阶段保证全局唯一：语义完全相同的重复关系确定性去重，真正的 ID 冲突分配稳定的新 ID。

## 参考项目到本地实现的对应关系

| 能力 | 参考源码与可复用机制 | 本地实现 | 采用程度 |
|---|---|---|---|
| 内容与配置指纹 | SourceBridge `internal/livingwiki/orchestrator/fingerprint.go:72` 的版本化、确定性输入哈希；Understand Anything `packages/core/src/fingerprint.ts:70-131` 的内容哈希与结构指纹 | `src/repo_teacher/indexer.py:_analysis_fingerprint`、`_integrity_digest` | 采用“实现版本/配置进入指纹”和 SHA-256 内容校验；没有复制其页面或 tree-sitter 数据结构 |
| baseline 缺失时 fail closed | CodeBoarding `repo_utils/fingerprint_diff.py:21-70` 明确把缺少全树 fingerprint 当作 `BaselineUnavailableError`，避免空 diff 被误判成无变化 | `src/repo_teacher/indexer.py:_baseline_rejection_reason` | baseline 缺失时全量索引；baseline 存在但 schema、项目路径、配置指纹、完整性、记录结构或扫描完整性不符时拒绝复用并输出 `baseline-rejected` |
| 全树文件变化集合 | CodeBoarding `repo_utils/fingerprint_diff.py:34-50` 使用 old/new 路径集合和内容哈希得到 added/modified/deleted | `src/repo_teacher/indexer.py:build_index` | 采用同类集合差分；文件哈希为完整 SHA-256，且结果按路径排序 |
| 未变结果复用 | CodeBoarding `static_analyzer/analysis_cache.py:338` 的 changed-file invalidation、`:395` 的结果合并，以及 `static_analyzer/incremental_orchestrator.py:36` 的“保留未变、重算变化、再合并”流程 | `src/repo_teacher/indexer.py:_group_records_by_path` 与 `build_index` | 采用文件级 copy-forward；本轮未实现 CodeBoarding 的 LSP 跨边界边重新验证，因此变化文件的关系会重新分析和全局解析，不声称 LSP 等价 |
| 保守结构分类 | Understand Anything `packages/core/src/fingerprint.ts:131-244`：内容不同但没有结构分析时按 `STRUCTURAL`；`change-classifier.ts:21-87`：局部、架构和全量更新阈值 | `src/repo_teacher/indexer.py:_structural_signature`、`_classify_changes` | 采用 NONE/内部实现/结构变化的保守基础，并使用 `>10`、`>30`、`>50%` 与顶层模块变化决定建议动作；未实现 AST 属性级完整指纹，故结果显式标为 `conservative` |
| 更新预算与可观察降级 | SourceBridge `internal/livingwiki/orchestrator/incremental.go:36-44,244-302` 的 diff/page budget guard 和排队结果 | `src/repo_teacher/scanner.py:ScanOptions`、`scan_repository` | 转化为本地扫描的 `max_files`/`max_total_bytes` 硬预算；达到边界会输出 `max-files-exceeded` 或 `max-total-bytes-exceeded` 并设置 `scan_complete=false` |
| 变化事件可靠性 | SourceBridge `internal/changewatch/watcher.go:94` 与 `router.go:323` 将文件变化、去重、限流和执行结果显式化 | `src/repo_teacher/scanner.py` 的逐文件错误诊断、`indexer.py:_source_is_stable` 的扫描后验证 | 采用“错误与不完整必须可观察”和最终一致性门；未实现常驻 watcher、debounce、breaker 或事件总线 |
| 关系图增量安全 | CodeBoarding `static_analyzer/incremental_orchestrator.py:36` 先失效变化文件，再重建边；SourceBridge 的 fingerprint 依赖确定性排序 | `src/repo_teacher/indexer.py:_ensure_unique_relationships` | 对相同关系去重、对真实哈希冲突稳定改号；本轮真实自索引样本从 5058 条原始关系归一化为 4843 条唯一关系（215 条语义重复，0 个真实冲突） |

## 本轮具体行为合同

### 扫描预算

- 默认最多检查 100,000 个可识别文件，总读取预算 1,000,000,000 字节，单文件最多 1,000,000 字节。
- 二进制或解码失败文件也消耗文件数/总字节预算，避免通过不可索引内容绕过资源上限。
- 预算必须为正整数或 `None`；无效配置立即失败。
- `stats.scan_complete` 只有在未截断且没有 walk/read/并发修改错误时才为 `true`。

### baseline 复用

- `schema_version`、分析代码与预算 fingerprint、绝对项目路径、核心记录 integrity、完整扫描标记必须全部匹配。
- 文件路径和 symbol/relationship ID 不允许重复；记录缺必填字段时整份 baseline 被拒绝，不做部分信任。
- baseline 记录按 `path` 一次分组；恢复复杂度从“每个未变文件扫描全部记录”降为“全部记录一次分组 + 未变记录一次恢复”。

### 一致性

- 每次打开文件后比较打开前、读取期间和读取后的 device/inode/size/mtime/ctime；变化文件不会进入本次索引。
- 分析完成后以同一排除目录和预算执行第二次扫描，比较路径、大小、SHA-256、跳过统计和截断状态。
- 前后项目快照的路径、Git 根、commit、branch、dirty、remote 和 license 必须一致。
- 这是检测式一致性门，不是文件系统原子快照；无法替代 APFS/ZFS snapshot 或 Git commit-only 模式，因此不声称无理论竞态窗口。

## 验证证据

- 专项单元测试：`tests/test_scanner.py` 和 `tests/test_indexer.py` 共 17 项通过。
- 覆盖场景：文件/字节预算、二进制预算绕过、非法预算、FIFO、跨项目/schema/配置 baseline、重算 integrity 后的畸形记录、非 Git 扫描期间新增文件、unsupported analyzer、内部实现与结构签名变化、重复关系 ID。
- 真实仓库自索引（共享工作区仍在并行修改，数字为本轮复核时样本快照）：66 个文件、4843 条输出关系、4843 个唯一关系 ID、0 个重复 ID，扫描完整。

## 尚未对齐参考项目的能力

- 没有 SourceBridge 的常驻 changewatch、debounce、circuit breaker、two-watermark 和队列续跑。
- 没有 Understand Anything 基于 tree-sitter 的 class property、return type 和 import specifier 完整结构指纹。
- 没有 CodeBoarding 基于 LSP 的变化文件重分析、跨变化边界引用验证和 call-site column 恢复。
- 没有文件系统级原子 snapshot；当前通过双扫描和前后项目快照拒绝混合状态。
- 扫描截断会生成明确的部分索引，但该结果不能作为下一次增量复用 baseline。

这些差异应由独立复审 Agent 判断是否满足当前核心索引模块的生产门槛；本文件不替代复审结论。
