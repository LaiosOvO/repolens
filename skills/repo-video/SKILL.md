---
name: repo-video
description: 视频稿渲染成片（流水线第 3 步）。输入 repo-script 产出的视频口播稿（manuscript.md）与素材目录，先把稿件拆成分镜交接稿 storyboard.md（场景表：口播原文逐字切分、画面类型、强调元素、素材引用、预估秒数、转场），再 TTS 配音、生成字幕、按选定路线渲染成片——路线 A：Remotion + TTS + 字幕（场景表机械翻译成 SCENES 数组）；路线 B：HyperFrames（HTML IN Canvas，每场景一个 HTML section + GSAP 时间轴）。当用户说"把视频稿做成视频""渲染成片"时使用。
---

# 视频稿渲染成片

由当前 agent 本体执行：拆分镜、配 TTS、生成字幕、写渲染工程、跑渲染、验收成片。

**核心原则：稿件是唯一的 upwards 事实源。** 口播原文逐字取自 manuscript.md，不改写、不增删事实；分镜与渲染只做"翻译"（文字 → 场景 → 画面），不做"创作"。

## 输入

- `MANUSCRIPT`：repo-script 产出的 `manuscript.md` 绝对路径（必填；系列稿逐集处理）；
- `ASSETS`：素材目录（缺省时取 manuscript 同级的 `../learning/screenshots/` 与 repo-script 的素材清单）；缺素材的场景显式标「待补拍」，不得用无关图片凑数；
- `OUTPUT`：输出目录（缺省时取 manuscript 同级 `video/`），其下为 `storyboard.md`、渲染工程、`audio/`、`subtitles/`、`out/`；
- `ROUTE`：`remotion`（默认，路线 A）/ `hyperframes`（路线 B）；
- `TTS`：本机可用 TTS 入口自行查明；语速按 550 字/分钟（约 1.35x 口播）估算；
- `FORMAT`：`1080x1920` 竖屏（默认，抖音）/ `1920x1080` 横屏；fps 默认 30。

## 步骤

1. **分镜交接稿**：完整读取 [storyboard.md](references/storyboard.md)，按其合同把稿件拆成场景表，写 `OUTPUT/storyboard.md`：口播原文逐字切分（每场景 2–3 句、5–10 秒，超 12 秒再拆，全片 15–25 场景）、画面类型从词表选、强调元素到字词级同步锚点、素材引用已有真实运行截图（缺则标「待补拍」）、预估秒数、转场；含片头信息表与字幕安全区/封面检查清单；
2. **TTS 配音**：按场景逐段合成 `audio/s{NN}.wav`，记录每段实际时长回填场景表（实际时长优先于预估）；全片拼接前逐段试听校验无截断、无乱码读音（命令按稿件里的中文读法合成）；
3. **字幕**：按场景生成 SRT/ASS，时间轴与音频对齐；遵守安全区（竖屏底部 padding ≥ 290px）；
4. **渲染工程**（按 ROUTE 二选一）：
   - **路线 A · Remotion**：把场景表机械翻译成 `config.ts` 的 SCENES 数组 + 场景组件（cover / title-card / key-points / big-number / steps / comparison / demo-terminal / code-walk / diagram / pitfall / closing 各对应一个组件）；全片单一强调色；封面场景静态无入场动效；参考模板：`meimouren/make-video-template` 的 TTS+字幕接线方式；
   - **路线 B · HyperFrames**：每个场景写成一个 HTML section + GSAP 时间轴，走 HTML IN Canvas 渲染；注意其限制：对 CSS 要求多、不合规会回退（CSS 只用其支持的子集）；RenderKit 为 Linux+Intel VAAPI 专用，macOS 不可用，只能参考结构；
5. **渲染与验收**：渲染出 `out/final.mp4`；抽帧检查：首帧即封面、字幕在安全区内、强调元素与口播同步、无黑帧/无样式回退（HyperFrames 路线重点检查回退）；音画对齐抽检至少 3 个场景；成片时长与场景表总时长偏差 > 5% 时查明原因；
6. **交接**：成片路径、各场景实际时长表、待补拍清单写入 `OUTPUT/render-notes.md`。

## 完成门

- storyboard.md 通过 [storyboard.md](references/storyboard.md) 的规则检查（场景数、单场景时长、词表、素材列无空项——要么有路径要么标「待补拍」）；
- 口播原文与 manuscript.md 逐字一致（diff 级核对）；
- 成片音画对齐、字幕安全区达标、封面静态；HyperFrames 路线无样式回退；
- 产物清单：`storyboard.md`、`audio/`、`subtitles/`、渲染工程、`out/final.mp4`、`render-notes.md`；
- 最终返回成片绝对路径、总时长、场景数、待补拍清单和各步骤耗时。
