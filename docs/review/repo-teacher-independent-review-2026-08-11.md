# Repo Teacher 独立 Review：参考采用真实性核查 + 需求匹配评估

日期：2026-08-11
审查对象：`/Volumes/T7/workspace/ontology/graph/dev/repo`
审查依据 Brief：`/Volumes/T7/workspace/ontology/graph/dev/repo/docs/review/repo-teacher-engineering-and-reference-review.md`
审查方式：4 路独立只读核查（实现代码 / 文档链 / 参考仓 ground truth / 测试与产物）+ GitHub 与 X(Twitter) 同类工具生态扫描。本报告未修改被审查仓库的任何文件。

---

## 0. 总结论

**REQUEST CHANGES** —— 参考采用**整体是真的**，不是表面包装；但 brief 自身承认的两项未完成工作（全量测试未跑、Coze 报告未生成）经实测确认仍然成立，且测试套件实测有 3 个红。在修复门（§6）完成前不应视为可交付状态。

三句话回答"有参考吗"：

1. **有，且证据链异常扎实**：13 个本机参考克隆的 HEAD SHA 与阅读笔记声明逐一吻合；笔记中约 30 处抽查的 file:line 引用几乎全部精确命中；代码里有 `reference_catalog.py` + `test_reference_ground_truth.py` 把"参考借鉴"做成了逐文件 sha256 钉死的可执行回归门（19 能力、66 切片、59 技术 claim、18 条关系边的精确断言）。
2. **12 项采用声明中 9 项在代码/Prompt 里确认存在**，3 项是文档宣称先行、实现未跟上（codewiki 功能树、serena 运行时集成、openwiki 式 skeleton→critic→prose 次序）。
3. **有 1 处对参考仓的误读**：openwiki 的降级机制真实存在，但其校验回退策略在源码中明确是保守偏 fail-open 的（`src/ingestion/code-mode.ts:81` 写着 "Fail-open"），brief 称之为"fail-closed 降级"属于归因不准。

---

## 1. 对用户需求的匹配评估

用户需求：对一个代码仓库输出它的功能 → 讲清底层运行原理 → 支撑技术选型 → 输出是给人看的报告，不是文字堆砌。

| 需求 | 实现对应 | 判定 |
|---|---|---|
| 输出仓库功能 | 确定性索引（scanner/analyzers/indexer）+ Codex 全功能 coverage pass（`cli.py:300`、`:462`；`human_report.py:279` "必须覆盖全部独立用户动作，不设固定章节数"） | ✅ 匹配，且明确拒绝"固定 10 功能上限"式的偷懒 |
| 讲清底层原理 | 章节合同强制 9 段叙述顺序（为什么存在 → 先说结论 → 一次任务怎样运行 → 核心对象 → 状态读写 → 难点/不变量/天真实现失败 → 边界 → 复用建议 → 源码证据），见 `human_report.py:291-302`；机制专项问题（Storage/Loop/Graph/Voice/Router）写进 Prompt | ✅ 匹配，这是该产品最强的一环 |
| 支撑技术选型 | 每章 `take / adapt / avoid / verify` 复用建议；`comparison.py` / `comparison_report.py` 提供跨仓机制对比；`difficulty.py` 固化"不变量/天真失败/取舍" | ✅ 匹配 |
| 报告形态而非文字堆砌 | 单页 `index.html`：「先说结论」首屏（`report.py:1101`）、章节卡片、`<details>` 证据下钻、`file://` + 行号锚点可点击源码切片（`report.py:589-605`）、mermaid codemap（`artifacts.py:376-448`） | ✅ 匹配 |
| 证据可信（隐含需求：报告不能瞎编） | `evidence.py` 路径/行号/snippet sha256 三重钉死；`validation.py` stale-evidence 重算比对；发布 fail-closed（`persistence.py:617-786` 原子 generation 切换）；每章 ≥3 个 source_refs 且至少一个非 docs/README | ✅ 匹配，属于差异化能力 |

**形态结论**：继续做 CLI 是对的。与 X/GitHub 上观察到的同类产品（§5）相比，"先功能后源码、证据可点击、发布可验证"这条路线有直接市场需求印证；Skill 只作薄入口的边界也符合生态现状（deepwiki-skill 类项目证明了薄 Skill 的可行性，但核心索引放 Skill 里无法承载）。

---

## 2. 参考采用真实性：逐项核查结果

### 2.1 代码层（实现里有没有）

| 参考仓 | 声称采用 | 代码核查结果 |
|---|---|---|
| pocketflow-code2tutorial | 抽象→关系→教学序→章节 | ✅ Prompt 级确认：`cli.py:301-302`、`human_report.py:280`；"并行写章→合并"未实现（单次生成，与采用栏措辞自洽） |
| codeboarding | 静态分析先行、统一中间产物、full/incremental/partial | ✅ 确认：`indexer.py:1248-1313` 增量 baseline + `_classify_changes` 四级变更分级（:891-900）；`validation.py:833-839` 拒绝 partial 索引进 baseline |
| deepwiki-open | 源码链接、层级、下钻 | ✅ 确认：`report.py:589-605` file:// 行号锚、`module_report.py:315-359` 层级下钻、`validation.py:1374` stale-evidence 重定位 |
| openwiki | no-op 验证、fail-closed | ⚠️ no-op 验证确认（`indexer.py:1353-1357` 暖启动仍全量重算派生物 + 伪造重签回归测试）；fail-closed 是 Repo Teacher 自身立场，openwiki 本体偏 fail-open，**归因需修正** |
| understand-anything | fresh/stale、增量上下文 | ✅ 确认：`validation.py:950/1374/1484` stale-file/stale-evidence/commit-drift，`skill_export.py:540-641` 导出前 freshness preflight |
| sourcebridge | audience voice、learning path、code tour、workflow story | ✅ 机制映射确认：`cli.py:293-296` 读者定位、`indexer.py:1106-1198` 阅读路线、`models.py:232-246` FeatureStep、`human_report.py:83-91` runtime_story |
| codewiki | 功能树、叶子先写、父级综合 | ❌ 仅 coverage pass 存在（`cli.py:300`）；功能树/父级综合全源码无实现，brief §9 自认是未来工作 |
| codebase-to-course | why 先行、中心用例、零基础翻译 | ✅ 章节合同级确认：`human_report.py:291-302`、`cli.py:308-310` |
| serena | LSP 符号检索专项层 | ❌ 运行时零集成。存在的只有：`tools/build_serena_specialist_report.py` 静态研究报告 + 该报告的保鲜测试（`test_serena_specialist_report.py` 测的是报告不过期，不是 LSP 功能） |
| codegraph-ai / gitnexus / learn-codebase | 评估参考，非硬依赖 | ✅ 定位相符，代码未冒充依赖 |

### 2.2 参考仓本体（借鉴对象是不是真的）

13 个本机克隆全部存在；抽查的机制声称与参考仓源码吻合：

- pocketflow `flow.py:24-28` 确有 `identify_abstractions >> analyze_relationships >> order_chapters >> write_chapters` 串联；
- codeboarding `analysis.py` 确有 `run_full/run_partial/run_incremental` 与统一 `analysis.json`；
- deepwiki `prompts.py:108-118` 确有强制 `Sources: [path:start-end]()` 引用格式；
- codewiki `documentation_generator.py:93-111` 确有"leaf modules first"拓扑序与父级加载子文档综合；
- sourcebridge 确有 voice 片段嵌入 system prompt 与 LearningPath/CodeTour/WorkflowStory 三种产物 RPC；
- understand-anything 确有 staleness 检测与 onboard/explain 分离；
- codebase-to-course / learn-codebase 的叙述要求与声称逐条吻合。
- **唯一偏差**：openwiki 的 mermaid 降级是"无效图降级为文本围栏"（内容保全），其校验刻意保守（"a valid diagram is never degraded"），并出现 "Fail-open" 字样——brief 的"fail-closed 降级"表述应改为"内容保全式降级 + 保守校验"。

### 2.3 文档链（笔记是不是真读过）

判定：**真读过，证据强度高于常规水平**。

- `docs/project-readings/` 13 份逐仓笔记 + 3 份导航全部实质：带行号引用、含否定性发现（pocketflow 全仓无 tests、codebase-to-course 未声明 LICENSE、deepwiki 缓存键不含 commit 的缺陷、gitnexus 是 PolyForm Noncommercial 许可证）——空泛模板写不出这些。
- `docs/research/` 4 份中最重的 `human-readable-repository-teaching.md`（833 行）含四层 schema 与失效传播设计，用固定 commit permalink 引用。
- 3 份 ADR 有真实备选权衡（6 方案比较表）。
- 小误差 3 处：codewiki 许可证行号（:5 应为 :11）、codegraph-mcp.js:19 内容漂移、difficulty 综合文档 serena 路径前缀不一致。
- brief 称"14 个本机参考仓库"，实际本机克隆 13 个（RepoAgent/Tour-de-Code-AI/walkthrough-plugin 只是固定 commit 在线核查），口径应修正。

---

## 3. 工程状态实测（2026-08-11）

| 项 | 结果 |
|---|---|
| `compileall src tests` | ✅ 通过 |
| CLI 可用性 | ✅ 9 个子命令（index/report/compare/explain/export-skill/validate/prepare-report/render-report/serve） |
| 全量测试 | ❌ **285 个测试，282 过 3 红**（单次全量超 300s，需分批跑完） |
| Waku 验收产物 | ⚠️ `outputs/waku-agent/index.html` 存在（2026-08-10 13:58，9 功能 4 section），但 `human-report.json` 全机找不到，产物不完整 |
| Coze 验收产物 | ❌ 本机不存在（`/tmp/repo-teacher-coze-review` 与 outputs/ 均无） |
| 版本管理 | ⚠️ `dev/repo` 不是 git 仓库，无提交史可查（ADR 时序无法验证，变更不可回溯） |

3 个失败测试：

1. `tests.test_reference_ground_truth...test_waku_is_a_separate_evidence_bounded_compatibility_corpus` — 断言 "Agent Loop：推理、工具调用与终止条件" 未在报告中出现（`test_reference_ground_truth.py:556`），疑似 waku 叙述模板漂移；
2. `tests.test_single_report...test_all_embedded_file_links_exist` — HTML 引用了磁盘上不存在的 `docs/decisions/0001-go-decision-first-repo-teacher.md`（实际文件名为 `0001-go-project-cli-and-human-project-report.md`）；
3. `tests.test_single_report...test_release_status_links_current_independent_audits` — "生产验收 PASS · 单页为唯一阅读入口" 文案未出现。

---

## 4. 与 brief 不符的差距清单（按严重度）

1. **测试不绿**：3 红（§3），其中 waku ground-truth 失败直接关联验收语料可信度。
2. **Coze 大型验收缺失**：brief 自己列为未完成；它是"功能覆盖率"问题（§7 问题 3）唯一能回答的实验，目前功能覆盖率无法计算。
3. **codewiki 功能树未实现**：单次大报告 + 40 章上限（`human_report.py:12`）。对 Coze 级仓库既有超时风险也有覆盖率风险。文档措辞已收窄，但 `PRODUCT-BRIEF.md` 与 `REFERENCE-PROJECTS.md` 的表述偏满。
4. **serena"专项层"名不副实**：实为静态研究报告。建议文档统一改口"专项研究/未来集成候选"。
5. **openwiki 归因误读**：fail-closed 是本项目立场，不是借来的机制（§2.2）。
6. **skeleton→critic→prose 次序未实现**：`REFERENCE-PROJECTS.md:25` 描述的三阶段在代码里不存在；确定性 coverage 在教程之后计算。
7. **小项**：导出包文件名与 PRODUCT-BRIEF 清单不一致（实际 `SKILL.md + agents/openai.yaml + references/code-index.{json,md}`）；`.tour` 导出不存在；`indexer.py:1357` 死代码分支（有注释说明，可接受但宜删）；确定性阅读路线不是按依赖排序（只在 Prompt 里要求模型按依赖）。

---

## 5. 外部生态扫描（GitHub + X，2026-08-11）

这个赛道已经很挤，需求被反复验证，但也意味着差异化必须守住在"证据可验证"上：

**GitHub 同类**：

- [sopaco/deepwiki-rs](https://github.com/sopaco/deepwiki-rs) — 代码生成技术文档 + AI-ready context；
- [natsu1211/deepwiki-skill](https://github.com/natsu1211/deepwiki-skill) — DeepWiki 风格文档的可移植 agent skill（薄 Skill 路线的直接例证）；
- GitNexus / codegraph-ai / serena — 图检索与 LSP 语义层（已在参考清单中）。

**X(Twitter) 信号**：

- OpenWiki 发布帖（@BraceSproul，7 月 2 日）199K 浏览、346 转发——"agent for repo documentation"有真实关注度；
- Repowise（约 5K star）"index once, dependency graph + PageRank，让 Claude Code 直接看到全仓" 类推文近期密集（@TheTechDiggest、@heyrohitai）；
- Repolyzer（@0xzdev）：GitHub 仓库分析器，生成系统架构 + 摘要 + 上下文对话；
- Understand-Anything 被多次推荐为代码库理解工具；
- Harrison Chase 把 DeepWiki/AutoWiki/LLM Wiki 归纳为 "Wiki Memory" 模式——仓库理解产物正在被视为 agent 的长期记忆层；
- 中文社区把 `deepwiki` MCP + `context7` MCP 列为"必不可少"（@miantiao_me，40K 浏览）。

**对 Repo Teacher 的含义**：功能摘要 + 架构图 + 对话式下钻已是商品化能力；多数竞品没有做的是——确定性证据门（路径/行号/sha256 三重钉死）、fail-closed 发布、参考 ground-truth 回归。这是应该继续加深的护城河，也是对外叙事时最该讲的差异点。

---

## 6. 最小修复门（达成 PASS 的条件）

1. 修掉 3 个红测试；把全量测试拆批纳入常规验证（单次 >300s 的事实要写进测试说明）。
2. 跑完 Coze 人类报告并记录：章节数、非文档 source_refs 占比、模型耗时/超时行为——没有它，"功能覆盖率"无数据。
3. 修正 openwiki 归因（brief §7 表与 REFERENCE-PROJECTS.md），补一句"fail-closed 是本项目立场，openwiki 本体为内容保全式降级"。
4. codewiki 功能树、serena 集成、skeleton→critic 次序三处，要么实现，要么在所有宣称性文档统一标注"未实现/未来工作"。
5. `git init` 并提交当前状态——没有版本史，后续所有"回归"都无从谈起。
6. brief 参考仓数量口径 14 → 13。

---

## 7. 对 brief §12 七个问题的直接回答

1. **CLI 还是拆 Skill/多阶段 workflow**：继续 CLI。索引/验证/发布需要确定性工程承载；大仓库超时问题用"按功能树分片 + 父级综合"（即真正采用 codewiki 机制）解决，而不是拆成 Skill。
2. **采用是否真实**：9/12 代码确认；3 项宣称先行（§4）；1 项归因误读（openwiki）。没有发现"只学到表面 UI"的情况——阅读笔记普遍深入机制层。
3. **Coze 覆盖率如何计算**：目前无法计算（产物缺失）。建议以"独立用户动作清单 vs 章节归属"为分母分子，由 coverage pass 输出显式缺口列表。
4. **source_refs 是否足以防 Spec 伪装**：机制充分（≥3 refs + 至少一个非文档源码 + 行号范围 + snippet hash + 难点证据必须是章节证据子集）；但 waku ground-truth 测试红说明执行层有漂移，先修测试再下结论。
5. **机制解释能否让陌生人复述**：合同设计足够（9 段 + 机制专项问题 + "不能只说负责/管理"反空话条款）；实证待 Coze 报告。
6. **生产门 vs 候选**：达到生产门——索引/验证/发布链（indexer/validation/persistence/evidence）；候选——人类报告生成（单次大报告、Coze 未验）、compare/export-skill（产物未独立验收）；实验——serena 研究、codegraph/gitnexus 评估。
7. **结论**：**REQUEST CHANGES**，最小修复门见 §6。

---

*本报告由独立审查 Agent 基于四路只读核查与外部生态扫描生成；所有 file:line 引用均在 2026-08-11 当日核实。*
