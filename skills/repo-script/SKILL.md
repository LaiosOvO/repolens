---
name: repo-script
description: 视频教程稿件（流水线第 2 步，人机协作：用户主笔，agent 补全）。输入 repo-learning 产出的学习 MD（或等价证据基座）与用户写的初版文稿，按风格配方（痛点钩开场、生活化比喻、数字清单、口述演示、避坑清单、三点式收尾）把初稿补全成可直接口播的视频教程稿，保留用户观点主线、事实不符回问不悄改；产出 manuscript.md + 提词器 index.html + publish.md 发布物料（标题三版、封面文案、简介、三层标签、分段时间轴、置顶评论），提词器 HTML 用 ego-browser 实机验收。当用户说"把我的初稿补全成视频稿""出教程口播稿"时使用。下游用 repo-video 把稿件渲染成片。
---

# 视频教程稿件（人机协作）

由当前 agent 本体执行：选材、补全、质量门、渲染提词器、ego-browser 验收，全部由 agent 完成。

**核心定位：agent 是编辑，不是内容主脑。** 用户写初版文稿，agent 按配方补全结构、核对事实、补齐口播性；保留用户的观点、例子与表达主线，不推倒重写。仅当用户明确说「全自动出稿」时才自己起草（从 learning.md 第 7 节选题出发），并显式告知这是全自动档。

## 输入

- `LEARNING`：repo-learning 产出的 `learning.md` 绝对路径（推荐）或其 `OUTPUT` 根目录（从中取 `stages/` 证据基座与 `screenshots/` 素材）；**禁止重新扫描源码仓库**；
- `DRAFT`：用户初版文稿路径（全自动档缺省）；
- `OUTPUT`：输出目录；**单仓单夹合同（2026-08-24 固化）：输出必须落在该仓库的 `{repository-name}-teaching/` 根目录内**，本 skill 的产物在其 `script/` 子目录（缺省取 LEARNING 所在 teaching 根的 `script/`），其下为 `manuscript.md`、`index.html`、`publish.md`、`stages/`、`screenshots/`；发现散落布局（如 `{repo}-script/`、`{repo}-tutorial-script/`）时先迁移归位再开工；
- `STYLE`：`tutorial`（默认）/ `teardown` / `interview`，见 [style-recipes.md](references/style-recipes.md)；
- `LENGTH`：`short` / `standard`（默认）/ `long`；
- `EPISODE`：`single`（默认）或 `series`；系列时产出大纲并至少完成第 1 集正稿；
- `LANGUAGE`：默认简体中文。

## 步骤

1. **读取学习基座**：读 `learning.md` 全文 + `stages/` 证据文件；选题若用户未指定，从 learning.md 第 7 节「值得讲的点」中取用户选定项；
2. **教学主线设计**，写 `stages/01-spine.md`：完整读取 [teaching-spine.md](references/teaching-spine.md)，按其字段合同完成设计（唯一核心知识点、目标观众、痛点场景、主比喻、三个展开场景、演示案例、坑、收尾三点；系列稿含递进规则与大纲）；素材列对齐 learning.md 已有截图与证据；
3. **补全成稿**，写 `manuscript.md`（系列稿为 `ep{N}-{主题}.md` + `00-系列大纲.md`）：按 [style-recipes.md](references/style-recipes.md) 选定 STYLE 的配方补全口播结构；全文口语短句，命令配中文读法；所有命令/配置/路径/数字必须与证据基座一致；**用户初稿中与仓库事实不符处显式标注并回问用户，不悄悄改掉**；
4. **覆盖显性规划**：`EPISODE=single` 时，`stages/01-spine.md` 末尾必须列「本集未覆盖的核心功能清单 + 建议的系列分集表」；核心功能数 > 6 时建议用户改 `EPISODE=series`，系列大纲把每个 CF 分配到具体集数；
5. **质量门**，写 `stages/02-quality-check.md`：逐项过 [quality-gates.md](references/quality-gates.md)，不过则回改，最多返修 2 轮；
6. **提词器渲染**：把通过的稿件写成自包含 `index.html`（大字号正文、分节锚点导航、命令/配置代码样式高亮；只排版不改写）；
7. **发布物料**，写 `publish.md`（系列稿每集一份）：字段合同见 [publish-kit.md](references/publish-kit.md)——标题三版（痛点利益/反直觉/数字清单）、封面文案（主标/副标/角标）、简介五段、三层标签、分段时间轴（各节字数 ÷ 400–430 字/分钟换算，与稿件预估总时长一致）、置顶评论（含经证据基座核验的仓库地址与 commit 快照）；只从稿件与证据基座取材，禁止新增事实，引用的数字必须与稿件正文一致；
8. **ego-browser 验收提词器 HTML**：heredoc（`ego-browser nodejs <<'EOF'`）开专用任务空间，`js()` 验证锚点导航零断链、全部章节渲染完整、无 console 报错（以 DOM 检查为准，不凭截图猜）；`captureScreenshot` 截图存 `screenshots/`（首屏 + 导航 + 至少 3 个核心章节，文件名标注验证点；滚动后黑帧用 `captureBeyondViewport:true` + clip 绕过）；**验收截图只作证据存档，不嵌入产物 HTML**；记录写 `stages/03-browser-check.md`，完成后 `completeTaskSpace(name, { keep: false })`；ego-browser 不可用不得跳过，如实报告。

## 完成门

- [quality-gates.md](references/quality-gates.md) 全部通过；
- [publish-kit.md](references/publish-kit.md) 的质量门全部通过（数字与稿件三场景一致、标题/简介/封面三方数字不打架、字数上限达标）；
- 用户初稿的观点主线保留；事实冲突处均已回问或有用户确认的处置记录；
- 提词器 HTML 通过 ego-browser 验收；
- 产物清单：`manuscript.md`（系列稿含大纲与各集正稿）、`index.html`、`publish.md`、`stages/01-spine.md`、`stages/02-quality-check.md`、`stages/03-browser-check.md`、`screenshots/`；
- 最终返回所有产物绝对路径、稿件字数/预估时长（400–430 字/分钟）、待用户确认项和各步骤耗时。
