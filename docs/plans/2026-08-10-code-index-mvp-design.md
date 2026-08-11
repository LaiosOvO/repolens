# 本地代码索引 MVP 设计

## 目标

让用户对任意本地 Git 仓库执行一条命令，得到一个可以直接用浏览器打开的代码索引报告。报告首先回答仓库规模、语言、入口和主要模块，再允许按文件、符号和关系检索。所有结果固定到当前 commit；单个文件解析失败不能中断整个仓库。

## 方案比较与决定

### 方案 A：Python 标准库扫描 + 单文件 HTML（采用）

优点是零外部依赖、安装和测试成本最低、适合立即验证产品价值。Python 使用 `ast` 得到可靠符号和调用；JavaScript/TypeScript 第一版使用保守的声明与 import 提取，只声称“发现的语法线索”，不伪装成编译级语义。

### 方案 B：Node + Tree-sitter

多语言 AST 更统一，但需要引入 parser、grammar 和 native/WASM 依赖。只有第一版证明报告和交互有价值后再接入。

### 方案 C：改造 SourceBridge 或 Understand Anything

能力最全，但集成面和部署重量过大；SourceBridge 还有 AGPL 边界。两者继续作为实现参考，不作为 MVP 运行时依赖。

## 组件

1. **Repository Snapshot**：读取 Git 根目录、HEAD、分支、dirty 状态、许可证和远程地址；非 Git 目录仍可扫描，但明确标记没有 commit 身份。
2. **File Scanner**：按忽略目录、扩展名和大小限制枚举文本源码，计算语言与目录统计。
3. **Language Analyzers**：Python 分析类、函数、方法、import 与调用；JS/TS 分析声明、export 与 import；未知语言保留文件级记录。
4. **Index Builder**：生成统一的 project/files/symbols/relationships/modules/reading paths 结构，并为所有实体分配稳定 ID。
5. **Report Renderer**：把索引嵌入单文件 HTML，提供概览、模块、文件、符号、关系和阅读路线筛选；使用 `file://` 打开时不依赖 `fetch`。
6. **CLI**：`index` 生成 JSON 与 HTML；`serve` 使用本地只读 HTTP 服务打开报告。

## 数据流

`本地路径 → 仓库快照 → 文件清单 → 语言分析 → 统一索引 → JSON + 单文件 HTML`。

索引结论分为两种强度：

- `exact`：Git、文件、Python AST 等确定性事实；
- `heuristic`：JS/TS 正则发现的声明、模块优先级和阅读路线。

UI 必须能显示这种差异，避免把启发式关系当作精确调用图。

## 错误处理

- 无权限、二进制、超大文件和排除目录进入 skipped 统计；
- 单文件语法错误进入 diagnostics，其他文件继续；
- Git 命令失败时降级到非 Git 模式；
- 输出目录禁止位于被扫描目录时被再次扫描；
- HTML 转义所有仓库内容，嵌入 JSON 时避免 `</script>` 提前闭合。

## 测试

- 临时 Git 仓库验证 commit、dirty、许可证和文件统计；
- Python fixture 验证类、函数、方法、import、contains 和 calls；
- TypeScript fixture 验证 import、class、function 和 export；
- 语法错误、超大文件和排除目录验证容错；
- HTML 验证数据内嵌、转义、关键区域和无外部资源；
- CLI 端到端验证生成 `index.json` 与 `index.html`。

## 第一版非目标

不做 LLM 功能提炼、编译级跨语言调用图、向量搜索、图数据库、IDE 插件、自动改代码和 Agent 派单。索引格式预留 analyzer 与 confidence 字段，后续可以接 Tree-sitter、SCIP 或 LSP。

