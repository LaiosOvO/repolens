# Go Report Bundle Independent Audit

- Audit date: 2026-08-10
- Auditor: Codex subagent `/root/repair_three_readings`
- Scope:
  [main.go](/Volumes/T7/workspace/ontology/graph/dev/repo/cmd/repo-teacher/main.go:1)
  [model.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/model.go:1)
  [load.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/load.go:1)
  [render.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/render.go:1)
  [bundle.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:1)
  [projectreport_test.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/projectreport_test.go:1)
  Waku 产物：
  [waku-agent.html](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent.html:1)

## Verdict
`REQUEST CHANGES`

主因不是“页面不好看”，而是当前实现还存在一个真实的路径逃逸问题，以及一个验证闭包不完整的问题。其余方向总体是对的：CLI 形态合理，bundle 闭集、原子发布、HTML 转义、evidence 重算思路都明显参考了 OpenWiki / DeepWiki / SourceBridge 这类项目里最有价值的部分。

## Findings

### P0: `enrichSource` 只做字符串级仓库边界检查，仓库内符号链接可以把证据读取到仓库外
- 位置：
  [load.go enrichSource](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/load.go:71)
- 问题：
  当前逻辑用 `filepath.Clean` + `filepath.Join` + `filepath.Rel` 判断 `source.Path` 没有 `..` 且拼接后仍在 repo root 下，然后直接 `os.Open(path)`。
  这能拦住 `../escape`，但拦不住“仓库内路径本身是一个 symlink，真实目标在仓库外”。
- 影响：
  1. `report` 阶段可能把 repo 外文件内容当成“源码证据”读进去。
  2. `verify` 阶段会对同样的 repo 外文件重新 hash，导致验证通过，形成“看起来是 repo evidence，实际不是 repo evidence”的假阳性。
  3. 这直接破坏了 SourceBridge/DeepWiki 式“source-grounded evidence”的根边界。
- 对抗探针：
  我构造了 repo 内 `dir/escape.txt -> /tmp/.../secret.txt` 的符号链接。
  结果：
  - 当前路径检查会放行。
  - 真实 `resolve()` 落到 repo 外。
  - 打开时能读到外部内容 `SECRET / LINE2`。
- 建议修复：
  在 `enrichSource` 里对最终目标做 `filepath.EvalSymlinks` 或等价真实路径解析，然后再基于解析后的真实路径重新做一次 repo containment check。
  同时建议拒绝目录或 symlink 类型输入，至少要显式 `Lstat`。

### P1: `VerifyBundle` 没有验证 `report.json` 里的“人类叙述源列表”与 `evidence.json/modules.json` 的闭包一致性
- 位置：
  [VerifyBundle](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:119)
  [verifyModules](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:172)
- 问题：
  `VerifyBundle` 现在验证了：
  - bundle 闭集
  - manifest 完整性
  - `evidence.json` 每条证据能否对 repo 重算
  - `modules.json` 是否引用现有 evidence
  - repo commit/dirty 是否漂移

  但它没有验证：
  - `report.Profile.Features[].Sources` 是否与 `evidence.json` 一一对应
  - `report.json` 里的人类说明字段和 source list 是否至少与 evidence 闭包保持一致
- 影响：
  如果有人重写 `report.json` 中的 feature source 列表、reason 文案、甚至删改功能页上的 source 结构，同时重新计算 manifest，`verify` 仍可能通过，只要 `evidence.json` 和 `modules.json` 没坏。
  这意味着“机器可验证证据”和“人类真正看到的 source list”之间还不是闭环。
- 为什么是 P1 不是 P0：
  这更像“完整性模型不够严”，不是直接越界读文件。但对你的产品目标很重要，因为你最终是给人做技术选型，不只是给机器存档。
- 建议修复：
  在 `VerifyBundle` 中从 `report.Profile.Features[].Sources` 重新计算一份期望 evidence 集合，要求它与 `evidence.json` 和 `modules.json` 严格闭合。

### P1: 当前产物没有足够明确地告诉读者“这是人工审核 profile 驱动，不是自动仓库抽取”
- 位置：
  [main.go report 命令接口](/Volumes/T7/workspace/ontology/graph/dev/repo/cmd/repo-teacher/main.go:24)
  [load.go Load](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/load.go:17)
  [waku-agent.html](/Volumes/T7/workspace/ontology/graph/biz/docs/html/repo-projects/waku-agent.html:1)
- 观察：
  实现是显式 `--profile <json>` 驱动的，这一点在 CLI 上是诚实的。
  但最终 HTML 页面没有明显提示“功能卡片和叙述是人工整理 profile，经源码证据约束验证，不是自动从仓库全量抽取”。
- 影响：
  对内部作者无所谓，但对最终读者会高估自动化程度，尤其你后面要做技术选型对比时，这种“自动提取 vs 人工归纳”的差异必须说清楚。
- 建议修复：
  在 HTML 顶部或页尾加一句明确 disclosure。

### P2: `verifyModules` 只检查“引用存在”，没有检查同一 feature 下 module refs 与 reading order 的重复/遗漏/排序质量
- 位置：
  [verifyModules](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:172)
- 问题：
  它只校验 `feature.FeatureID` 合法、`SourceRefs` 存在、每个 feature 至少出现一次。
  它没有检查：
  - `ReadingOrder` 是否有重复
  - `Modules[*].SourceRefs` 是否覆盖该 feature 的全部 evidence
  - `ReadingOrder` 与 module index 是否一致
- 影响：
  当前不是安全洞，更像“模块索引质量约束不够完整”。
  对你想要的“功能到模块文件索引”来说，这部分迟早要收紧。

### P2: 没有直接覆盖 symlink/path-escape、malformed manifest、modules coverage 退化的自动化测试
- 位置：
  [projectreport_test.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/projectreport_test.go:1)
- 观察：
  现有测试覆盖了：
  - 人类 HTML 是否有关键结构
  - bundle 生成与 verify 正常路径
  - artifact tamper
  - 现有目标已存在
  - `../outside` 这类字符串级逃逸
  - HTML escape

  但缺失：
  - repo 内 symlink 指向 repo 外
  - manifest 恶意重写但 bundle 文件集不完整/多余
  - modules/evidence/report 三者闭包退化
- 影响：
  这也是为什么 P0/P1 问题现在能存活。

## Strengths

- bundle 发布路径总体是对的：
  [WriteBundle](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:67)
  先 staging、逐文件 `O_EXCL`、`Sync` 文件、`Sync` staging dir、`Rename`、再 `Sync` parent，已经是比较认真的原子发布实现。

- manifest closed-set 是对的：
  [verifyClosedSet](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:152)
  它拒绝 symlink、拒绝非 regular file、拒绝多余或缺失 bundle 文件，这部分明显比很多“只看 manifest”实现更稳。

- HTML 注入边界是对的：
  [render.go template + EscapeHTML](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/render.go:8)
  [projectreport_test.go script escape test](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/projectreport_test.go:112)
  当前页面没有出现原始 `<script>`，Waku 产物里也未发现脚本标签直出。

- 现有 Waku 页面的人类可读性比此前平铺版好很多：
  当前页面至少已经具备：
  - 先结论后实现
  - 9 个 capability card
  - 9 个 detail panel
  - `仍需验证` 分区
  - 17 条 source hash 行

## Verification

### 1. 代码阅读审计
- 已逐文件阅读：
  [main.go](/Volumes/T7/workspace/ontology/graph/dev/repo/cmd/repo-teacher/main.go:1)
  [load.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/load.go:1)
  [render.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/render.go:1)
  [bundle.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/bundle.go:1)
  [projectreport_test.go](/Volumes/T7/workspace/ontology/graph/dev/repo/internal/projectreport/projectreport_test.go:1)

### 2. Go tool verification
- `go test ./...`：
  失败。
- `go vet ./...`：
  无法继续，因为同一工具链问题先阻断。
- `go run ./cmd/repo-teacher verify ...`：
  无法执行。
- 阻断原因：
  当前环境的 Go 标准库编译版本与 `go` 二进制不匹配。
  实际报错为：
  `compile: version "go1.22.4" does not match go tool version "go1.26.3"`
- 结论：
  这是当前机器 Go 安装问题，不是本审计范围内的产品代码缺陷；但它阻断了“用真实 CLI 重跑 verify”的最后一层确认。

### 3. Independent probes
- Probe A: 现有 Waku bundle 基线完整性
  - closed-set：通过
  - manifest generation id：通过
  - manifest entry hash/bytes：通过
  - sample evidence source hash：通过

- Probe B: artifact tamper
  - 修改 `report.json` 为 `{}` 后，不更新 manifest
  - 结果：完整性失配可被检测

- Probe C: source drift
  - 在 repo 副本里直接改动首条 evidence 覆盖的真实行段
  - 结果：source hash 失配可被检测

- Probe D: malformed bundle
  - 构造只有 `manifest.json` 的 bundle
  - 结果：closed-set 可拒绝

- Probe E: symlink escape
  - 构造 repo 内 symlink 指向 repo 外文件
  - 结果：当前 `enrichSource` 的路径检查会放行，真实读取发生在 repo 外

## Recommended next changes

1. 先修 P0：
   在 `enrichSource` 里做真实路径解析并重新校验 containment。

2. 再修 P1：
   让 `VerifyBundle` 严格验证 `report.json <-> evidence.json <-> modules.json` 的闭包一致性。

3. 加 disclosure：
   在最终 HTML 标明“当前是 reviewed profile 驱动 + source evidence 验证”，不是全自动语义抽取。

4. 补测试：
   - symlink escape
   - malformed manifest
   - report/evidence/modules mismatch
   - module reading order 重复/遗漏

## Bottom line

这个 Go 模块已经有“生产化意识”，不是随手脚本，尤其在 bundle 原子发布、manifest 完整性、HTML escape 上做得不错。

但现在还不能给 `PASS`，因为：
- repo boundary 还可以被 symlink 绕过
- verify 还没有把“人类看到的 report”与“机器验证的 evidence”完全锁死

修掉这两点后，再重跑一次真实 `go test` / `go vet` / `repo-teacher verify`，这条线才足够接近你要的生产级要求。
