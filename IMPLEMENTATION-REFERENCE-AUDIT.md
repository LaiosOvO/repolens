# Repo Teacher：实现—参考—审计总账

> 这是一份当前状态总账，不是宣传页。
>
> 只有独立审计结论为 `PASS` 的模块才算当前稳定；`REQUEST CHANGES` 和 `BLOCK` 都表示还不能把对应结果写成生产完成。

## 当前总览

| 模块 | 本地实现 | 参考机制与本地源码路径 | 当前审计状态 |
| --- | --- | --- | --- |
| 核心索引链 | `scanner.py`、`snapshot.py`、`indexer.py`、`evidence.py`、`validation.py`、`persistence.py`、`cli.py` | SourceBridge `repo/sourcebridge/internal/indexer/indexer.go`、`repo/sourcebridge/workers/knowledge/evidence.py`；Understand Anything `fingerprint.ts`、`change-classifier.ts`；CodeBoarding `fingerprint_diff.py`、`incremental_orchestrator.py` | `PASS` |
| 教学 HTML、功能讲解 | `features.py`、`artifacts.py`、`report.py` | PocketFlow `repo/pocketflow-code2tutorial/flow.py` / `nodes.py`；SourceBridge `learning_path.py` / `code_tour.py`；OpenWiki skeleton critic；DeepWiki Wiki / Codemap / CodeViewer | `PASS` |
| 六仓技术选型对比 | `reference_catalog.py`、`comparison.py`、`comparison_report.py` | 六个固定快照的 48 个“仓库 × 能力”审计条目，行级 claim 与上下文入口分层 | `PASS`，正式产物已重生 |
| 命名功能定位到具体模块 | `module_locator.py`、`module_report.py`、CLI `explain` | CodeBoarding component / cluster；SourceBridge 图查询与 Code Tour；Understand Anything tour / graph；DeepWiki Codemap / CodeViewer | `PASS` |
| 选中功能导出 Skill | `skill_export.py`、`skill_validation.py` | Understand Anything freshness preflight；本地 Skill Creator 格式合同 | `PASS` |
| Go 分析器 | `analyzers/go.py`、`analyzers/go_semantic.py` | SourceBridge `parser.go` / `languages.go`；CodeBoarding 的 LSP / 位置语义；gopls 作为可选 differential probe | `PASS` |

## 六个参考仓库的角色分工

这六个仓库不是同一种“基准”。

1. **SourceBridge**：生产可靠性、证据门、增量状态机、Learning Path / Code Tour 的主基准。
2. **PocketFlow Code2Tutorial**：教程章节顺序、先抽象再关系再展开的叙事基准。
3. **OpenWiki**：skeleton critic、独立 coverage critic、canonical page 与链接完整性的基准。
4. **Understand Anything**：结构指纹、变更分类、知识图、tour 与 freshness 的基准。
5. **CodeBoarding**：LSP 位置级语义、component 聚类、增量边重验证的基准。
6. **DeepWiki-Open**：Wiki / Codemap / CodeViewer 交互形态与证据引用的基准。

“参考完整”不表示复制六套系统，而是表示：每项产品能力都要有明确的参考机制、明确的本地证据和明确的排除边界。

## 每个模块当前到底算什么

### 核心索引链：独立复审通过

独立复审结论是 `PASS / CLEAR`。

当前已验证：

- `index`、`explain`、`compare` 通过单一 generation 指针发布，失败不混合 JSON / HTML；
- 完整重签的 Go / JS / Python 伪关系会被拒绝，暖启动不继承污染基线；
- Waku 与 SourceBridge 的冷建、磁盘暖启动、root/current 双入口均通过；
- 扫描预算、常见 secret、非 Git 尾窗和兼容入口自愈都有回归门。

详细证据见 [core-index-reaudit-round3.md](docs/audits/core-index-reaudit-round3.md)。

### 教学 HTML：独立复审通过

独立复审结论是 `PASS / CLEAR`。

当前已验证：

- 六仓保持 19 个 curated 能力、66 个职责切片、18 条真实关系和 59 条窄技术 claim；
- Waku 的 memory / graph / loop / gateway 只作为兼容性候选，不冒充 curated 事实；
- Python 与 JS 的作用域、重绑定、延迟闭包、非法 JS 和评论绕过反例均 fail closed；
- 真实 Chrome 1440 / 390 双视口、展开交互和源码跳转通过。

详细证据见 [teaching-reaudit-round13.md](docs/audits/teaching-reaudit-round13.md)。

### 技术选型对比：源码与正式产物均已更新

当前结论是：

- **源码实现：PASS**
- **正式 examples：PASS**

六个完整克隆已用同一当前分析指纹重建并完成身份校验。主单页提供 8 组技术决策、48 张机制卡、15 个行级 claim proof；其余源码入口明确标为继续阅读上下文。

详细证据见 [technology-comparison-reaudit-round4.md](docs/audits/technology-comparison-reaudit-round4.md)。

### 命名模块定位：可用

模块级复审是 `PASS`。

这意味着：

- 负向扩展名和 emitted JS 路径都能正确收敛；
- 结果可以稳定指向具体模块；
- 页面可定位到功能目录、具体源码切片和实现关系；不确定的跨层功能仍保守返回候选。

详细证据见 [module-locator-reaudit-round4.md](docs/audits/module-locator-reaudit-round4.md)。

### Skill 导出：当前稳定模块

独立复审结论是 `PASS`。

它的关键保证是：

- append-only；
- fail closed；
- 不会静默覆盖已有入口；
- 事务链可重放、可验证。

详细证据见 [skill-export-reaudit-append-only-final.md](docs/audits/skill-export-reaudit-append-only-final.md)。

### Go 分析器：当前稳定模块

独立复审结论是 `PASS`。

它的边界也写得很清楚：

- 这是 precision-first lexical / semantic fallback；
- 不等于完整 Go type checker；
- 正式 SourceBridge 产物已统一重生并通过校验；其既有 `D LICENSE` 只保留为 dirty-source warning。

详细证据见 [go-analyzer-reaudit-round5.md](docs/audits/go-analyzer-reaudit-round5.md)。

## 已确认不能夸大的边界

- 文件和符号齐全仍不等于覆盖了全部运行时行为。
- 生成的调用图不等于确定性运行时事实。
- JS 确认入口依赖可用的 Node 语法检查；不可用、超时或语法非法时会保守降级。
- TypeScript 动态行为仍只做保守词法分析，无法证明时不提升为事实。
- SourceBridge 参考克隆中用户既有的 `LICENSE` 删除状态被保留，因此报告显示一个 dirty-source warning。

## 读这个仓库时建议怎么用这些结论

1. 人工阅读先打开 [Repo Teacher 单页报告](../../biz/docs/html/repo-teacher.html)。
2. 需要定位一个功能时，使用 `repo-teacher explain` 并打开生成的模块 HTML。
3. 需要交给 Agent 时，使用 `export-skill` 生成受 freshness 与闭包校验约束的工作包。
4. 需要查验结论时，从主单页的行级证据或审计链接下钻。

## 相关文档

- [README](README.md)
- [最终实现建议](FINAL-IMPLEMENTATION-GUIDE.md)
- [单一主 HTML 最终独立审计](docs/audits/single-html-final-reaudit.md)
- [本次文档刷新说明](docs/audits/final-documentation-refresh.md)
- [参考仓库清单](docs/audits/reference-clone-inventory.md)
