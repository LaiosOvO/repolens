# 人类可读 HTML 合同

## 阅读顺序

1. Hero：第一句话说明这是什么项目、为谁解决什么问题。
2. **业务入口覆盖图**：按平台与菜单层级展示可执行叶子、数量、归属和支持边界；可折叠查看完整 `container_path`，不能只显示已选核心功能。
3. **用户能直接体验的业务功能**：按用户目标说明“在哪里做什么 → 系统完成什么 → 看见什么结果”，并回链 entry/surface。
4. **核心功能有哪些**：不限数量，每项说明支撑哪个业务结果、实现本质、关键判定及依赖的系统能力。
5. **系统核心能力**：按 18 个审计轴显示 implemented/partial/external/not-applicable、具体机制、消费者和关键缺口；不是目录树。
6. **核心架构**：解释调用方/前端、后端/运行时、状态、Worker 与外部系统如何共同完成运行。
7. **技术栈与依赖实现**：紧接核心架构，按实际层说明入口、职责、协议与边界。
8. 核心概念与一次真实用户旅程。
9. 各核心业务功能；每章就地讲完整底层运行。
10. 系统机制与工程目录地图、前后端/进程/Worker/数据/部署。
11. 双台账覆盖、知识索引和证据边界。

不要先平铺功能卡，再在页面后半段重复实现详情。

发布前先做内容结构检查，不依赖浏览器：

- HTML 正文必须有“用户能直接体验的业务功能”与“核心功能有哪些”两个非空章节；
- HTML 正文必须有“业务入口覆盖图”和“系统核心能力”；入口计数与 `02-business-entries.md` 相等，18 审计轴无缺项；
- “技术栈与依赖实现”必须位于“核心架构”和第一个详细功能章之间，且每个关键依赖都包含实际源码入口与职责；
- 核心功能清单数必须等于详细功能章数，每项必须能链接到对应章节；
- 每个 `.biz-fn` 内，“先用自然语言讲清运行原理”必须在第一个 Mermaid、组件表和符号链之前；
- 每个核心功能必须从当前 evidence 动态生成并回答机制问题集；不按仓库名或领域类型套模板，图不能替代答案。
- 每个 catalog `knowledge_id` 在 HTML 中有唯一锚点，并能从 `knowledge/index.md` 定位；HTML 与根目录 `report.md` 的正文来源一致。

任一项不通过时保留阶段 Markdown，不写/不覆盖 `index.html`。

## 版式

- 使用“深海墨色 + 纸白内容面 + 青绿强调”的技术编辑风格，不使用低对比紫色、透明淡字或发光渐变。
- 页面令牌固定为：页面 `#09111b`、侧栏 `#0f1b28`、正文 `#e8eef5`、次要文字 `#aebdca`、强调 `#2dd4a7`、警示 `#ffb454`、内容纸面 `#f6f8fa`、纸面文字 `#17212b`、边框 `#30465b`。
- 正文固定 `13px/1.65`，H1 28px，H2 21px，H3 16px；摘要 15px，表格 12.5px，图注和源码证据 12px；不得因内容少而放大字号填充页面。
- 左侧 272px sticky TOC；桌面端始终可见，列出一级、二级章节，当前章节使用青绿色左边线和浅色背景标识。
- 侧栏必须包含“回到顶部”、项目/业务入口/业务功能/系统能力/架构/工程/证据导航；点击锚点后标题不能被顶部遮挡。
- 视口窄于 900px 时侧栏变成顶部可展开目录；不得直接消失，也不得覆盖正文。
- 主内容宽 940–1100px；表格和图可以局部横向滚动，页面本身不得横向溢出。
- 每个功能章用 `.biz-fn` 容器；组件、流程、关键细节使用不同小标题色，不堆装饰卡。
- 普通正文只允许在单词/路径边界换行，禁止在 `body`、`li`、`p` 上使用 `overflow-wrap:anywhere`。长 commit/hash 可在专用 `.commit` 内 `word-break:break-all`；行内 `code` 使用 `overflow-wrap:normal; word-break:normal; white-space:normal`，不能把 `index.html`、`scripts.start`、符号名或路径逐字符竖排。
- 带编号的步骤列表不得让自然文本直接成为 CSS Grid 的多个匿名网格项。优先使用 `li { position:relative; padding-left:... }` + `li::before`；若使用 Grid，必须把整条步骤正文包进单一 `<div>`/`span`，并为正文设置 `min-width:0`。浏览器 QA 必须至少包含一条带两个以上行内 `code` 的步骤。

## Mermaid

使用 Mermaid 11 的 `base` 主题和深色技术图画布。图容器固定 `#111827` 背景、`#263449` 边框、16px 圆角和充足留白。初始化值固定为：

```text
background: #111827
primaryColor: #111827
primaryTextColor: #f8fafc
primaryBorderColor: #60a5fa
secondaryColor: #171329
secondaryTextColor: #f8fafc
secondaryBorderColor: #c084fc
tertiaryColor: #0b211c
tertiaryTextColor: #f8fafc
tertiaryBorderColor: #34d399
lineColor: #aebbd0
textColor: #f8fafc
edgeLabelBackground: #0b1220
clusterBkg: #111827
clusterBorder: #334155
```

每张图都追加这些 class，并把节点显式归类：

```mermaid
classDef actor fill:#0f172a,stroke:#60a5fa,color:#f8fafc,stroke-width:2px;
classDef control fill:#1b1630,stroke:#c084fc,color:#f8fafc,stroke-width:2px;
classDef compute fill:#0b211c,stroke:#34d399,color:#f8fafc,stroke-width:2px;
classDef state fill:#241b0b,stroke:#fbbf24,color:#f8fafc,stroke-width:2px;
classDef external fill:#25151b,stroke:#fb7185,color:#f8fafc,stroke-width:2px;
classDef output fill:#172033,stroke:#facc15,color:#f8fafc,stroke-width:2px;
```

节点正文固定高对比浅色，边标签使用不透明深色底。禁止低对比淡字、同色节点铺满整图和发光渐变。主链只保留决定结果的 5–9 个节点；数据库、Trace、通知等旁路用虚线或拆图。SVG 不强制压缩到容器宽度；复杂图在 `.mermaid` 内横向滚动。

每张图必须附一个纯文字“读图顺序”，即使 Mermaid 运行库不可用，读者仍能理解主链。业务交互图按“参与者 → 触发 → 核心处理 → 状态/外部系统 → 结果”组织；部署拓扑不得冒充功能运行图。

默认发布前在真实浏览器中断言；若用户明确要求只评估内容、跳过浏览器或优先快速生成，则本节降级为非阻断待验收项，只执行 Mermaid 块结构、导航锚点、源码链接与 HTML 闭合的静态检查，并在 `performance.md`/最终交付如实写明未运行浏览器：

- Mermaid 块数量等于 SVG 数量；
- 页面不存在 `Syntax error in text`；
- Mermaid SVG 内所有文字与背景的对比清楚，不出现接近白色的节点文字；
- 每张核心图至少使用 3 种语义 class；主链和旁路从线型上可区分；
- 节点文字和边标签可读；
- 390px 与桌面宽度无页面级溢出；
- 所有步骤正文占满编号右侧可用宽度；行内代码没有落入编号列、没有逐字符竖排；
- 侧边栏链接都能定位到存在的章节，桌面端 sticky、移动端可展开；
- 若当前环境无法实际启动浏览器，不得声称图已渲染通过，必须在交付结论中明确列为待验证。

## 证据导航

源码链接必须能回到仓库文件；若本地 `file:` 导航会离开报告，提供“新标签打开”或明确的返回报告链接。源码证据放在每个功能章末尾，不要作为正文开头。
