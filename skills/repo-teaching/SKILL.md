---
name: repo-teaching
description: 仓库教学流水线（repository-report 与 repo-tutorial-script 的融合版）。对任意代码仓库只做一次源码取证与产品表面覆盖，随后同源产出两份成品：仓库讲解报告（业务功能 + 逐跳因果证据 + 工程地图，Markdown + 单文件 HTML）和可直接口播的视频教程稿件（痛点钩开场、生活化比喻、数字清单、口述演示、避坑清单、三点式收尾，Markdown + 提词器 HTML）；两份 HTML 都用 ego-browser 实机验收并保留截图。当用户要求"给仓库出报告和教程稿件""生成仓库讲解 + 视频脚本"时使用。
---

# 仓库教学流水线

由当前 agent 本体执行：读源码取证、写报告、写稿件、渲染 HTML、ego-browser 验收，全部由 agent 完成；不得调用任何报告/稿件生成程序、渲染器或辅助脚本。

**核心原则：一次取证，双产物。** 源码、CodeGraph、README/docs 的读取和证据收集只做一遍，报告与稿件从同一份证据基座派生；禁止为写稿件重新扫描仓库。

## 输入

从用户请求取得：

- `SOURCE`：源码仓库绝对路径（必填）；
- `OUTPUT`：输出根目录绝对路径（缺省时在 `SOURCE` 父目录创建 `{repository-name}-teaching/`），其下分 `report/` 与 `script/` 两个产物目录和共享的 `stages/`；不要写入上游源码仓库；
- `PRODUCTS`：默认 `both`，也可只要 `report` 或 `script`；
- `STYLE`：稿件风格，`tutorial`（默认）/ `teardown` / `interview`，见 [style-recipes.md](references/style-recipes.md)；
- `LENGTH`：稿件篇幅，`short` / `standard`（默认）/ `long`；
- `EPISODE`：`single`（默认）或 `series`；系列时产出大纲并至少完成第 1 集正稿；
- `LANGUAGE`：默认简体中文。

## 阶段一：共享取证基座（只做一遍）

完整读取同仓 `skills/repository-report/references/` 下的 pipeline.md、coverage.md、chapter.md、narrative-good-bad.md、performance.md，按其合同执行（下为摘要，冲突处以那些文件为准）：

1. 固定源码身份，写 `stages/00-context.md` 与 `stages/00-run-manifest.md`；
2. 建立/刷新/验证 CodeGraph（仓库无 `.codegraph/codegraph.db` 时自行查明本机 codegraph 入口并建索引），写 `stages/00-codegraph.md`；
3. **只做一次产品读取**（README/docs、路由/命令、持久对象、Worker、依赖清单、外部边界），写 `stages/01-project.md` 与 `stages/02-product-surfaces.md`；md 文档是一手产品声明证据源，与代码不符处以代码为准并显式标注；
4. surface 账本归并核心功能，写 `stages/02-capabilities.md`（每个 surface_id 恰好处置一次）；
5. 共享证据规划 `stages/02-evidence-plan.md`；
6. 每个核心功能闭合逐跳因果证据（`文件:行号`），写 `stages/03-implementation/{功能}.evidence.md`；功能并发不超过 3、禁止递归分派；
7. 工程地图 `stages/04-engineering.md`。

## 阶段二：产物 A —— 仓库讲解报告

8. 按 repository-report 合同的"项目 → 业务功能 → 核心功能 → 核心架构 → 技术栈与依赖实现 → 功能底层运行 → 工程地图 → 证据边界"组装 `report/report.md`（各功能正文取同阶段证据写融合讲解，可与证据文件并排存 `stages/03-implementation/{功能}.md` 再汇编）；
9. 直接写自包含 `report/index.html`（合同见 repository-report/references/html.md：固定侧边栏导航、正文 13px、深色高对比 Mermaid 技术图、仅 Mermaid 运行库允许 CDN）；render 只组合排版已通过的内容，不得重新分析源码。

## 阶段三：产物 B —— 视频教程稿件

10. **教学主线设计**，写 `script/stages/01-spine.md`：完整读取 [teaching-spine.md](references/teaching-spine.md)，从阶段一证据基座选材（不重新扫仓），选定唯一核心知识点、主比喻、三个展开场景、演示案例、至多三个坑；
11. **写稿**，写 `script/manuscript.md`（系列稿为 `script/ep{N}-{主题}.md` + `script/00-系列大纲.md`）：严格按 [style-recipes.md](references/style-recipes.md) 选定 STYLE 的配方；口播稿全文口语短句，命令配中文读法；所有命令/配置/路径必须与证据基座一致；
12. **稿件质量门**，写 `script/stages/02-quality-check.md`：逐项过 [quality-gates.md](references/quality-gates.md)，不过则回改，最多返修 2 轮；
13. **提词器渲染**：把通过的稿件写成自包含 `script/index.html`（大字号正文、分节锚点导航、命令/配置代码样式高亮；只排版不改写）。

## 阶段四：ego-browser 实机验收（两份 HTML 都过）

14. 用 ego-browser heredoc（`ego-browser nodejs <<'EOF'`）开专用任务空间（如 `repo-teaching 验收 {仓库名}`），依次打开 `report/index.html` 和 `script/index.html`：
    - 用 `js()` 验证：侧边栏/锚点导航零断链、全部章节渲染完整、Mermaid 无 `Syntax error in text`（报告）、无 console 报错——以 DOM 检查为准，不凭截图猜；
    - `captureScreenshot` 截图存 `OUTPUT/screenshots/`：报告首屏 + 核心功能章至少 3 张；稿件首屏 + 导航 + 至少 3 个核心章节（系列稿加大纲页）；文件名标注产物与验证点（如 `report-ch03.png`、`script-nav.png`）；截图超时则改用 js() DOM 验证并在记录中注明；
    - 验证记录写 `stages/05-browser-check.md`（每份 HTML 的验证项、结果、截图路径、问题），完成后 `completeTaskSpace(name, { keep: false })`；
    - 未过项回对应阶段修复重验；ego-browser 不可用不得跳过，如实报告。

## 完成门

- repository-report 完成门全部适用产物 A（见该 skill 的"完成门"清单）；
- [quality-gates.md](references/quality-gates.md) 全部适用产物 B；
- 报告与稿件的事实陈述一致（同一证据基座），数字、命令、路径在两份产物中不打架；
- 两份 HTML 均通过 ego-browser 验收，截图齐备；
- manifest 能证明源码只取证一遍；产物清单：`stages/`、`report/report.md` + `report/index.html`、`script/manuscript.md` + `script/index.html`、`screenshots/`、`stages/05-browser-check.md`；
- 最终返回所有产物绝对路径、功能数、稿件字数/预估时长（400–430 字/分钟）、证据条数、截图清单、待核验项和各阶段耗时。
