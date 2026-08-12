# 人类可读 HTML 合同

## 阅读顺序

1. Hero：第一句话说明这是什么项目、为谁解决什么问题。
2. **核心功能与核心架构**：紧接项目结论，先点名 2–5 个决定技术路线的能力，再解释调用方/前端、后端/运行时、状态、Worker 与外部系统如何共同完成最核心的一次运行。仓库没有前端或服务端时直接写“不存在”，不得补造。
3. 核心概念与一次真实用户旅程。
4. 其余核心业务功能；每章就地讲完整底层运行。
5. 工程目录地图、前后端/进程/Worker/数据/部署。
6. 覆盖账本和证据边界。

不要先平铺功能卡，再在页面后半段重复实现详情。

## 版式

- 使用“深海墨色 + 纸白内容面 + 青绿强调”的技术编辑风格，不使用低对比紫色、透明淡字或发光渐变。
- 页面令牌固定为：页面 `#09111b`、侧栏 `#0f1b28`、正文 `#e8eef5`、次要文字 `#aebdca`、强调 `#2dd4a7`、警示 `#ffb454`、内容纸面 `#f6f8fa`、纸面文字 `#17212b`、边框 `#30465b`。
- 正文固定 `13px/1.65`，H1 28px，H2 21px，H3 16px；摘要 15px，表格 12.5px，图注和源码证据 12px；不得因内容少而放大字号填充页面。
- 左侧 272px sticky TOC；桌面端始终可见，列出一级、二级章节，当前章节使用青绿色左边线和浅色背景标识。
- 侧栏必须包含“回到顶部”、项目/架构/功能/工程/证据五组导航；点击锚点后标题不能被顶部遮挡。
- 视口窄于 900px 时侧栏变成顶部可展开目录；不得直接消失，也不得覆盖正文。
- 主内容宽 940–1100px；表格和图可以局部横向滚动，页面本身不得横向溢出。
- 每个功能章用 `.biz-fn` 容器；组件、流程、关键细节使用不同小标题色，不堆装饰卡。

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

发布前在真实浏览器中断言：

- Mermaid 块数量等于 SVG 数量；
- 页面不存在 `Syntax error in text`；
- Mermaid SVG 内所有文字与背景的对比清楚，不出现接近白色的节点文字；
- 每张核心图至少使用 3 种语义 class；主链和旁路从线型上可区分；
- 节点文字和边标签可读；
- 390px 与桌面宽度无页面级溢出；
- 侧边栏链接都能定位到存在的章节，桌面端 sticky、移动端可展开；
- 若当前环境无法实际启动浏览器，不得声称图已渲染通过，必须在交付结论中明确列为待验证。

## 证据导航

源码链接必须能回到仓库文件；若本地 `file:` 导航会离开报告，提供“新标签打开”或明确的返回报告链接。源码证据放在每个功能章末尾，不要作为正文开头。
