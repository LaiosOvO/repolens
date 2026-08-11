# Repo Teacher 工程、设计与参考项目 Review Brief

更新时间：2026-08-11  
工程目录：`/Volumes/T7/workspace/ontology/graph/dev/repo`  
读者：未参与当前实现的架构、代码质量、测试与产品审查 Agent。  
读完后的动作：能够从零运行 CLI、核对设计取舍、对照参考仓库逐项判断“采用是否准确、实现是否完整、HTML 是否真的帮助人理解功能”。

## 1. 一句话定位

Repo Teacher 是一个本地代码仓库理解 CLI。它先建立可验证的文件、符号和关系索引，再让 Codex 基于真实源码归纳“用户能做什么”和“每个功能怎样工作”，最后发布面向人的 `index.html`。源码入口、函数和调用链只能作为证据，不能直接冒充产品功能。

主产品选择是 **CLI**，不是纯 Skill：

- CLI 负责扫描、索引、缓存、模型调用、证据验证、HTML 渲染和原子发布。
- Skill 只作为薄入口或选定功能的导出包，不承载核心索引逻辑。
- HTML 是主要人类交付；`index.json`、`analysis-pack.json` 和 `human-report.json` 是审计与复现产物。

## 2. 用户工作流

### 2.1 建立机器索引

```bash
cd /Volumes/T7/workspace/ontology/graph/dev/repo
PYTHONPATH=src python3 -m repo_teacher.cli index <repository> --output <output-dir>
```

产物：

- `index.json`：文件、符号、关系、模块、静态候选、证据与诊断。
- `index.html`：机器索引浏览器；不等于人类功能报告。

### 2.2 生成人类功能报告

```bash
cd /Volumes/T7/workspace/ontology/graph/dev/repo
PYTHONPATH=src python3 -m repo_teacher.cli report <repository> --output <output-dir>
```

执行阶段：

1. 扫描仓库并建立语言索引。
2. 复核 Git/非 Git 源快照和索引完整性。
3. 生成有界分析包。
4. Codex 直接检查仓库源码并做全功能 coverage pass。
5. 本地校验章节、源码路径、行号和证据闭包。
6. 原子发布 JSON 与人类可读 HTML。

CLI 现在会输出阶段日志；Codex 阶段每 30 秒输出一次已耗时。`--output-schema` 只约束机器可解析的 JSON 形状，不限制功能数量；Schema 与本地代码会再次校验字段、路径、行号和证据闭包。曾尝试移除 Structured Outputs，但 Codex 返回了不完整 Markdown，因此明确拒绝该方案。

### 2.3 其他命令面

- `explain`：定位命名模块或功能面并生成源码下钻报告。
- `compare`：比较多个参考仓库的机制和复用边界。
- `export-skill`：把选定功能、证据和索引闭包导出成固定 Skill。
- `validate`：校验索引身份、完整性、派生工件和当前 generation。

## 3. 当前架构

```text
Repository
  │
  ├─ scanner.py                  文件预算、忽略目录、二进制/大文件边界
  ├─ analyzers/*                 Python / JS / TS / Go 结构与关系
  ├─ indexer.py                  统一索引、增量基线、指纹、关系解析
  ├─ capability_graph.py        typed graph、遍历、caller/callee、依赖与影响面
  ├─ features.py                 确定性入口/框架边界候选，不负责最终产品命名
  ├─ artifacts.py               tutorial / codemap / coverage 派生工件
  └─ validation.py              身份、语义闭包、派生一致性与防重签污染
          │
          ▼
  canonical index.json
          │
          ├─ human_report.py     有界证据包、模型 JSON 合同、本地字段/路径/行号校验
          ├─ cli.py              Codex 调度、全功能 Prompt、阶段日志
          ├─ report.py           人类章节 HTML 渲染
          └─ persistence.py      immutable generation + current 指针发布
```

### 3.1 关键模块绝对路径

- CLI 与模型 Prompt：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/cli.py`
- 人类报告 Schema、证据包与合成验证：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/human_report.py`
- HTML 渲染器：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/report.py`
- Waku 固定审计叙述（验收语料，不是通用规则）：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/narrative.py`
- 扫描器：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/scanner.py`
- 索引编排：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/indexer.py`
- CodeGraph 风格能力图与查询：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/capability_graph.py`
- Python/JavaScript/Go 分析器：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/analyzers`
- 静态候选发现：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/features.py`
- 教程/图/覆盖派生：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/artifacts.py`
- 索引验证：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/validation.py`
- 原子 generation 发布：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/persistence.py`
- 模块定位与模块 HTML：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/module_locator.py`、`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/module_report.py`
- 技术对比：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/comparison.py`、`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/comparison_report.py`
- Skill 导出：`/Volumes/T7/workspace/ontology/graph/dev/repo/src/repo_teacher/skill_export.py`

## 4. 确定性代码和大模型的边界

### 确定性层负责

- 文件、语言、符号、调用/包含/导入关系。
- Git identity、commit、dirty、analysis fingerprint 和 baseline compatibility。
- 路径、行号、文件范围、relationship endpoint 与 evidence closure。
- 资源预算、错误诊断、不可变 generation 与发布一致性。
- HTML 转义、链接和机器数据的可复现渲染。

### Codex 负责

- 把代码对象归纳成用户可感知的产品能力。
- 选择依赖驱动的教学顺序，而不是按目录或文件数切章。
- 解释因果运行链、存储/查询机制、循环、路由、语音边界、并发和终止条件。
- 识别真正困难的不变量、朴素实现的失败、当前取舍和复用边界。

### Codex 不得负责

- 发明不存在的文件、符号、行号或 evidence ID。
- 用 Spec、README 或路由标题单独证明功能已实现。
- 用 regex、文件名或关键词匹配最终决定“这个功能是什么”。
- 把不确定推断写成已实现事实。

当前默认 `report` 对每章要求至少 3 个 `source_refs`，至少一个来自非 `docs/specs/README` 的实现或测试源码。CLI 校验路径存在、行号在文件范围内，再将 source ref 物化为 HTML 可点击的证据切片。

## 5. 人类 HTML 的内容合同

每个功能章采用渐进披露，不再把九组内容同时平铺：

1. **30 秒理解**：为什么存在、一次怎么跑、底层机制一句话。
2. **一次任务完整运行**：触发者、接管者、产物、消费者和因果步骤；这一段默认展开。
3. **底层机制到底怎么工作**：数据、写入、查询、控制循环、路由、结束和动态边界；默认折叠。
4. **真正难点与失败方式**：每个难点按“运行过程 → 不变量 → 天真实现失败 → 设计取舍”线性展开；源码证据和迁移问题再折叠一层。
5. **边界、复用与技术选型**：支持/不支持与 `take / adapt / avoid / verify`；默认折叠。
6. **源码证据**：入口、符号、关系和行号永远放在最后，不能取代功能讲解。

机制专项要求：

- Storage/Memory：事实源、原始记录、派生记录/索引、写入提交、失败、gate、召回、排序、Top-K 与合并。
- Agent Loop：明确 `for/while/event loop`、一轮输入、工具 observation 回填、continue/return/break 和上限。
- Graph：构图、ready、wave/barrier、并发单位、state merge、冲突、Router 输入/规则/输出、终止和动态拓扑边界。
- Voice：录音边界、VAD/切段、ASR → Agent → TTS、缓冲还是流、是否可打断、串行/半双工/全双工。
- Router：必须区分“选择下一步”和“执行下一步”。

## 6. 数据和发布合同

`report` generation 包含：

- `index.json`：确定性机器索引。
- `analysis-pack.json`：发送给模型的有界导航和证据包。
- `human-report.json`：模型生成的结构化功能章节。
- `index.html`：最终人类报告。
- `generation-manifest.json`：同一 generation 的文件 hash 闭包。

输出目录通过唯一 `current` 指针切换 generation，避免新 JSON 与旧 HTML 混合。根目录兼容链接是 convenience view，权威入口是完整验证后的 current generation。

## 7. 本机参考仓库与实际借鉴点

### 第一组：核心结构与索引基线

| 本机仓库 | 采用内容 | 当前没有照搬的部分 |
|---|---|---|
| `/Volumes/T7/workspace/ontology/graph/repo/sourcebridge` | audience voice、learning path、code tour、workflow story、来源导航 | 不采用其完整部署栈；不把低层静态图直接当产品功能 |
| `/Volumes/T7/workspace/ontology/graph/repo/codeboarding` | 静态分析先行、统一中间产物、full/incremental/partial 思路 | 不复制其项目特定工作流；需要更严格的证据身份门 |
| `/Volumes/T7/workspace/ontology/graph/repo/deepwiki-open` | 层级 Wiki、architecture/data-flow、源码链接、继续下钻 | 不复制 UI；不要求为了凑数引用固定数量文件 |
| `/Volumes/T7/workspace/ontology/graph/repo/pocketflow-code2tutorial` | Identify abstractions → relationships → teaching order → chapters | 不采用只有少量“核心抽象”就声称覆盖全部功能的上限 |
| `/Volumes/T7/workspace/ontology/graph/repo/understand-anything` | knowledge graph、onboard/explain 分离、fresh/stale、增量上下文 | 不把 Skill 当核心索引实现；Skill 只作薄适配 |
| `/Volumes/T7/workspace/ontology/graph/repo/openwiki` | 图/页面/no-op 验证和保留内容的保守降级 | 不把其降级描述成普遍 fail-closed；不采用纯目录/配置 fallback 冒充能力 |
| `/Volumes/T7/workspace/ontology/graph/repo/codegraph-ai` | typed node/edge graph、bounded traversal、callers/callees、module dependencies、impact query | 不复制 Rust 服务、38 语言解析、持久数据库、embedding、MCP/IDE server；当前仅复用图查询合同 |

### 第二组：教学质量与语义导航

| 本机仓库 | 采用内容 | 当前用途 |
|---|---|---|
| `/Volumes/T7/workspace/ontology/graph/repo/codewiki` | 功能树、组件聚类、叶子先写、父级综合 | Prompt 的功能层级和 coverage pass 参考 |
| `/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course` | 先回答 why、中心用例、零基础翻译、模块递进 | 人类章节叙述顺序参考 |
| `/Volumes/T7/workspace/ontology/graph/repo/learn-codebase` | 预测、提问、主动回忆 | 未来交互学习模式，不放在默认首屏 |
| `/Volumes/T7/workspace/ontology/graph/repo/serena` | LSP 符号检索、find references、精确编辑与 memory | 作为 live semantic navigation 专项层，不冒充持久图或沙箱 |
| `/Volumes/T7/workspace/ontology/graph/repo/gitnexus` | repository graph、影响面和多客户端集成 | 评估图查询与技术选型下钻，不直接复制其 UI |

### 第三组：验收语料

| 本机仓库 | 用途 |
|---|---|
| `/Volumes/T7/workspace/ontology/graph/repo/waku-agent` | 第一份深度人类报告；验证 Memory、Agent Loop、Graph、Voice 等机制是否讲清楚 |
| `/Volumes/T7/workspace/ontology/staff/coze` | 当前大型混合 Go/Electron/逆向工程验收仓；验证“不能靠 Spec 偷懒、不能限制 10 个功能、每章要有实现源码证据” |

## 8. 参考研究与逐仓阅读记录

- Prompt 参考合同：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/research/prompt-contract-from-repository-teaching-tools.md`
- 人类仓库教学综合：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/research/human-readable-repository-teaching.md`
- Skill/社区研究：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/research/repository-teaching-skills-and-community.md`
- 自动难点发现研究：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/research/automatic-feature-difficulty-discovery-synthesis.md`
- 逐仓阅读入口：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/project-readings/README.md`
- 架构决策：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0001-go-project-cli-and-human-project-report.md`
- 内容合同决策：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0002-human-project-report-content-contract.md`
- CodeGraph 查询层决策：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/0004-codegraph-style-capability-query-layer.md`
- 机制讲解决策：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/decisions/human-first-mechanism-report.md`

## 9. 当前验证状态

已验证（2026-08-11 当前冻结代码）：

- 全量：295 tests PASS，1 项因本机缺少可选 `gopls` 语料而 skip；`compileall src tests` PASS。
- JavaScript 语法门使用本机已安装的 `/opt/homebrew/Cellar/node@22/22.23.1/bin/node`；Node 不可用时按设计保守不确认 JS 边界。
- 能力图专项：6 tests PASS；覆盖 feature slice、connected component、caller/callee、依赖、影响、方向/深度/数量边界及“contains 不是 call”。
- 人类报告、CLI、单页、Serena 与浏览器组合回归：55 tests PASS。
- Waku 正式人类 HTML 由 CLI 重生成：212 files、1,557 symbols、9,879 relationships、13 modules；canonical index validate 为 0 errors / 0 warnings。
- 真实 Chrome：1440×900 与 390×844 均无页面横向溢出；功能深读与难点二级折叠可点击。

仍需后续工作：

- 还没有开始 `/Volumes/T7/workspace/ontology/voice/VoxMesh/references` 的五仓批量索引；按用户顺序，必须先冻结本工程再执行。
- 模型语义层仍需更多非 Waku 仓库验证；结构图候选只进入模型上下文，不能自动升级成人类功能。
- 当前图层是内存派生 JSON，不是 CodeGraph 的持久图数据库，也没有 MCP/IDE 服务。
- 语义功能判断禁止 regex；现存 regex 只能用于 secret 脱敏或受控格式校验，review 时应继续核对边界。

## 10. 建议 Review 顺序

1. **产品正确性**：HTML 是否先讲功能和机制，而不是入口/调用链。
2. **功能覆盖**：无固定 10 项上限；同一入口可合并，但行为/状态/机制不同的用户动作不能被吞掉。
3. **证据可靠性**：Spec/README 不得单独证明实现；`source_refs` 必须落到当前源码行范围。
4. **机制准确性**：storage/query、loop、graph/router、voice/concurrency 是否回答了具体问题。
5. **大模型边界**：模型只能解释和选择证据，不能修改 canonical index 或生成未验证 ID。
6. **增量与发布**：baseline、fingerprint、current generation、异常恢复和 stale source 是否 fail closed。
7. **安全**：secret redaction、路径逃逸、symlink、输出覆盖、Skill 导出和本地 HTML 链接。
8. **性能**：Coze/SourceBridge 级仓库的 cold/warm 时间、RSS、分析包大小和模型超时行为。

## 11. 可复现 Review 命令

```bash
cd /Volumes/T7/workspace/ontology/graph/dev/repo

# focused 人类报告合同
PYTHONPATH=src python3 -m unittest \
  tests.test_human_report tests.test_artifacts tests.test_cli -v

# 全量
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests

# Waku 人类报告
PYTHONPATH=src python3 -m repo_teacher.cli report \
  /Volumes/T7/workspace/ontology/graph/repo/waku-agent \
  --output /tmp/repo-teacher-waku-review

# Coze 人类报告
PYTHONPATH=src python3 -m repo_teacher.cli report \
  /Volumes/T7/workspace/ontology/staff/coze \
  --output /tmp/repo-teacher-coze-review \
  --model-timeout 1200

# 校验发布索引
PYTHONPATH=src python3 -m repo_teacher.cli validate \
  /tmp/repo-teacher-coze-review/index.json \
  --source /Volumes/T7/workspace/ontology/staff/coze
```

## 12. 独立审查应给出的最终结论

请不要只给“测试通过”。至少回答：

1. 当前产品应该继续做 CLI，还是需要把 Prompt 拆成独立 Skill/多阶段 workflow？
2. 参考仓库的机制采用是否真实，是否错误归因或只学到了表面 UI？
3. Coze HTML 的功能覆盖率如何计算，漏掉了哪些非页面功能？
4. source refs 是否足以防止 Spec/README 伪装成已实现功能？
5. 每章机制解释是否让陌生读者不打开源码也能复述“它怎样运行”？
6. 哪些模块达到生产门，哪些只能算候选或实验实现？
7. 给出 `PASS / REQUEST CHANGES / BLOCK`，并列出最小修复门。
