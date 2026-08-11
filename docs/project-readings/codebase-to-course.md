# codebase-to-course profile

## 固定版本身份
- 完整 clone：`/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course`
- origin：`https://github.com/zarazhangrui/codebase-to-course.git`
- HEAD：`ff8837ecf8e9f6ce9874ffa42e42633394a52a00`
- 工作树：clean

## 一句话定位
codebase-to-course 是一个 Claude Code skill 包，把任意代码库变成一个可离线打开的单页 HTML 课程站，重点是“让非技术用户看懂代码怎么跑起来”。

## 产品形态与许可证
- 形态：Claude Code Skill / 静态 HTML 课程生成器。
- 版本身份：仓库未声明可执行版本号，当前更像内容/技能仓库而不是可发布程序。
- 许可证：**未在当前一手源码中声明**。仓库根目录未见 `LICENSE` 文件，`README.md` 和 `SKILL.md` 也没有给出许可证。

## 主要功能
1. 把任意代码库翻译成单页 HTML 课程：用户在 Claude Code 里说“turn this into a course”或给一个仓库路径/URL；触发→接管→输出→消费：`SKILL.md` 先识别目标代码库，再把分析结果写成 `course-name/` 目录里的 `index.html`、`styles.css`、`main.js` 和各模块 HTML，消费端是浏览器；底层机制/关键技术：技能驱动的课程生成、模块化 HTML、完全静态输出；关键源码：[codebase-to-course/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:8) 的总目标，[codebase-to-course/README.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/README.md:21) 的课程形态说明，[codebase-to-course/references/build.sh](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/build.sh:1) 的组装脚本；复用价值：很适合用来做“把复杂系统讲给非工程背景的人听”的内容生成器；局限：产物是静态 HTML，不是可执行应用。
2. 用四阶段流程控制课程质量：触发→接管→输出→消费：`SKILL.md` 把流程拆成代码库分析、课程设计、课程构建、复查打开四步，复杂仓库时先写 module briefs，再并行写模块；输出是更稳定的 4-6 模块结构，消费端是课程写作者和最终读者；底层机制/关键技术：Phase 1 深读代码、Phase 2 课程编排、Phase 2.5 briefs、Phase 3 并行写作、Phase 4 预览反馈；关键源码：[codebase-to-course/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:53) 的流程分段，[codebase-to-course/references/module-brief-template.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/module-brief-template.md:1)，[codebase-to-course/references/content-philosophy.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/content-philosophy.md:1)；复用价值：适合迁移到任何“长内容生成 + 并行写作”的工作流；局限：复杂路径依赖不少手工前置分析，交付时间较长。
3. 通过固定设计系统把输出做成“漂亮的开发者笔记本”：触发→接管→输出→消费：生成器把统一的 `styles.css`、字体、颜色、阴影、节奏和滚动行为复制到课程目录，输出是温暖、非默认 AI 风格的页面，消费端是浏览器里的读者；底层机制/关键技术：设计 token、warm palette、alternating backgrounds、scroll-snap、现代字体；关键源码：[codebase-to-course/references/design-system.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/design-system.md:18) 的颜色/字体/间距规范，[codebase-to-course/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:199) 的设计原则，[codebase-to-course/references/styles.css](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/styles.css:1)（在 skill 中要求直接复制）；复用价值：这是一套可直接借用的“温暖、克制、内容导向”课程视觉语言；局限：风格约束很强，不适合想做成原生产品 UI 的场景。
4. 用统一的交互引擎承载 quiz、翻译块、聊天动画和数据流动画：触发→接管→输出→消费：模块 HTML 只要放入约定 class/data 属性，`main.js` 就会自动扫描并挂上交互，输出包括 code↔English 翻译、选择题、拖拽题、group chat、message flow、glossary tooltip 等，消费端是课程浏览器；底层机制/关键技术：DOM 约定、`data-*` 属性、IntersectionObserver、HTML5 Drag API + touch 兜底、全局函数绑定；关键源码：[codebase-to-course/references/main.js](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/main.js:19) 的导航/tooltip/quiz/drag-and-drop 引擎，[codebase-to-course/references/interactive-elements.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/interactive-elements.md:28) 的 HTML/CSS/JS 模式，[codebase-to-course/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:96) 的“必须包含”的交互类型；复用价值：可直接拿来当交互课程组件库；局限：对 HTML 结构约束非常严格，必须遵守约定 class 和属性。
5. 用 build.sh 把模块拼成最终站点：触发→接管→输出→消费：写完模块后执行 `bash build.sh`，它只做 `cat _base.html modules/*.html _footer.html > index.html`，输出是最终单页入口，消费端是本地浏览器或静态托管；底层机制/关键技术：超简单的拼接式构建、无前端打包、无运行时依赖；关键源码：[codebase-to-course/references/build.sh](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/build.sh:1)，[codebase-to-course/SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:179) 的 assemble 步骤，[codebase-to-course/README.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/README.md:79) 的目录结构说明；复用价值：构建极简、可解释性强、便于手工排错；局限：需要人工保证模块顺序、引用和内容一致性。

## 事实
- README 明确说这是一个 Claude Code skill，输出是“single HTML file / directory”，并强调可离线打开、无 setup；见 [README.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/README.md:3) 和 [SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:8)。
- `references/main.js` 负责所有交互：导航、进度条、tooltip、quiz、拖拽、聊天动画、数据流动画等；见 [main.js](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/references/main.js:6)。
- `SKILL.md` 明确禁止重写 `styles.css` 和 `main.js`，要求直接复制引用文件；见 [SKILL.md](/Volumes/T7/workspace/ontology/graph/repo/codebase-to-course/SKILL.md:127)。

## 推断
- 这个仓库更像“内容生产系统”而不是传统软件包；它的核心资产是写作规则、设计系统和交互模式。
- 因为课程输出完全静态，所以它天然适合分享、归档和离线阅读，但不适合承载复杂运行时行为。

## 未知
- 许可证缺失是当前一手证据里最明确的空白；如果后续要对外分发，需要先补许可证决策。

## 对 Skill / 项目 / CLI 决策的启示
它证明 Skill 很适合规定“产品先、实现后”的教学法和页面体验；也同时暴露纯 Skill 缺少稳定索引、增量和独立验证。因此借其内容合同，不把它作为分析内核。
