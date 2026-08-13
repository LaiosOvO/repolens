# 业务入口与系统能力双台账合同

本合同解决两个不同的漏报问题：用户看得到的菜单、页面和动作没有被完整枚举；系统真正依赖的状态、协议、Worker、安全和恢复机制没有被完整审计。两者必须分别建账，再通过 `surface_id`、`capability_id` 和 `system_capability_id` 双向闭合。CodeGraph 只证明符号、调用和读写关系，不代替产品发现。

## 目录

1. [共同不变量](#共同不变量)
2. [业务入口台账](#业务入口台账)
3. [系统核心能力台账](#系统核心能力台账)
4. [产品表面与业务功能归并](#产品表面与业务功能归并)
5. [双向闭包与发布门](#双向闭包与发布门)
6. [配置、协作与外部集成](#配置协作与外部集成)
7. [Good / Bad](#good--bad)

## 共同不变量

- 先枚举，后归并。发现阶段不得因为多个入口“看起来相似”而提前合并。
- 以注册事实和可执行事实为主，文本搜索只定位候选。不得用仓库名、领域词、路径关键词或某个样例项目的固定功能清单决定结论。
- 所有清单都有稳定 ID、源码证据、计数和处置状态；“看过主要文件”不等于完成覆盖。
- 不允许静默 `LIMIT N`。大仓库必须分批，保留游标、批次范围、原始总数和 omitted 诊断；未完成分批时不得进入 capabilities。
- 显示标签不是稳定身份。ID 优先由平台、注册容器、路由/命令键和处理器身份组成；本地化文案只作展示证据。
- 声明、注册、可达和运行成功是四种不同事实。报告必须分别标注，不能把“菜单存在”“路由注册”写成端到端已实现。

## 业务入口台账

写 `stages/02-business-entries.md`。该文件是用户能直接操作什么的权威清单，不是功能摘要。

### 1. 按平台机械枚举入口

对仓库实际存在的平台逐一检查；不存在的平台写 `not-applicable` 与证据，不填空表：

| 入口族 | 必查注册事实 | 需要展开的叶子 |
|---|---|---|
| Web / Desktop / Mobile 导航 | route table、sidebar/topbar、menu config、layout、tab registry、deep link | 每个可点击菜单项、子菜单、tab、route、deep link |
| 页面交互 | button、toolbar、row action、context menu、form submit、drag/drop、upload、keyboard shortcut、command palette | 每个会导航、提交、创建、变更、执行、导出、取消或删除的动作 |
| 本地与桌面能力 | tray、native menu、IPC/Tauri command、protocol handler、file association、notification action | 每个用户可触发命令及其 renderer/native handler |
| CLI 与开发者入口 | command/subcommand registry、flags、stdin、exit/output contract | 每个有独立结果的命令叶子；父 command 只作容器 |
| HTTP / RPC / WebSocket | router registration、method/path、message kind、subscription | 每个有业务副作用或独立可见结果的端点/消息 |
| 自动与外部入口 | scheduler、queue consumer、webhook、filesystem watcher、startup/resume hook | 每个无人值守触发及其结果消费者 |

菜单与路由必须从注册源机械展开，不能只看截图、README 或渲染后的一个页面：

1. 找到应用 bootstrap 与路由/菜单/命令注册器；
2. 展开数组、对象、builder、插件贡献点和条件分支生成的全部静态可知叶子；
3. 沿本地化 key 找回展示标签，但不把同一个 action 的多语言副本重复计数；
4. 记录 feature flag、角色、平台、许可证、运行环境等可见条件；
5. 将每个叶子追到 handler、目标 route 或明确的 placeholder；
6. 再反查 route/handler registry，补上没有菜单的 deep link、API、IPC、后台和隐藏入口。

动态插件、服务端下发菜单或运行时注册项无法静态展开时，必须记录贡献协议、provider、枚举边界和 `dynamic-unresolved` 数量；不得挑当前 fixture 中几个实例冒充全集。

### 2. `business_entry` 必填字段

| 字段 | 内容 |
|---|---|
| `entry_id` | 本次源码快照内稳定唯一的 ID |
| `platform` | `web` / `desktop` / `mobile` / `cli` / `api` / `ipc` / `worker` / `external` / 当前仓库的其他真实平台 |
| `entry_kind` | menu、route、tab、button、toolbar、row-action、context-menu、form、shortcut、command、endpoint、message、trigger 等真实种类 |
| `container_path` | 完整层级，如“项目 / 知识 / 导入 / 从 URL”；非 UI 入口写注册层级 |
| 展示与触发 | label/localization key、method/path/command/event、输入 |
| 可见条件 | role、flag、platform、配置、状态前置条件；默认是否可见/可用 |
| 目标 | route、handler、IPC/HTTP method、job 或 external handoff |
| 结果 | 用户或下游实际观察到的状态、文件、消息、页面或副作用 |
| 证据 | 注册源、处理器与结果消费位置；相对路径、符号和行范围 |
| `surface_id` | 归并后所属产品表面；发现时可为空，发布前必须处置 |
| 状态 | `mapped` / `supporting` / `excluded` / `unresolved`，并写理由 |

### 3. 菜单与动作计数规则

- 菜单组、折叠标题和 layout 不是可执行叶子，不单独算业务功能；它们必须保留为 `container_path`，防止层级信息丢失。
- 同一 handler 的菜单、快捷键和 command palette 是三个 `entry_id`，可归入同一 `surface_id`；这样才能证明所有入口都被覆盖。
- 同一路由内产生不同业务结果的 tab、toolbar 或 row action 分别建项；不能用“页面已覆盖”吞掉页面里的执行、导入、导出、发布、取消等动作。
- 路由存在但不可从任何导航进入时仍建项，并标 `deep-link`、`internal` 或 `orphan-route`；后两者需要排除理由。
- 菜单指向 placeholder、disabled stub 或只有说明文字时仍建项，支持边界标 `catalog-only` 或 `declared-only`，不得写成已实现功能。
- CRUD 不自动升级为多个核心功能，但 create/edit/archive 等入口仍必须先逐项进入台账，再按同一领域旅程归并。

### 4. 业务入口计数

文件末尾按 `platform × entry_kind` 输出：`discovered`、`mapped`、`supporting`、`excluded`、`unresolved`。必须满足：

```text
discovered = mapped + supporting + excluded + unresolved
entry_id 全局唯一
unresolved = 0 才能 render
```

`excluded` 必须有源码事实和产品理由；“不重要”“数量太多”“属于设置页”不是理由。

## 系统核心能力台账

写 `stages/02-system-capabilities.md`。这份台账回答“产品靠哪些底层机制持续、正确、安全地运行”，不能由业务功能章顺带提到几个模块代替。

### 1. 固定审计轴，不固定项目功能

以下是跨仓库审计轴，不是要强行生成 18 个章节。每一轴都必须给出 `implemented`、`partial`、`declared-only`、`external`、`not-applicable` 或 `unresolved`；适用轴内的具体系统能力数量不限。

1. 启动、进程、生命周期、单实例与关闭；
2. 身份、登录、会话、设备与租户/工作区隔离；
3. 授权、权限决策、租约、审计与撤销；
4. 配置、feature flag、Secret、provider 与运行时装配；
5. 领域对象、状态机、不变量与状态转换；
6. 数据库、Schema、迁移、事务、一致性与删除；
7. 文件、工作区、Git、媒体与对象存储；
8. 队列、Worker、调度、定时器、后台与背压；
9. 并发、锁、租约、幂等、去重与顺序；
10. HTTP/RPC/IPC/WebSocket、事件与协议版本；
11. AI、模型、Agent、工具、Skill、插件与沙箱；
12. 搜索、索引、缓存、知识/记忆与失效；
13. 外部集成、webhook、同步、导入导出与离线；
14. 失败、超时、重试、取消、恢复与重启；
15. 安全隔离、网络出口、隐私、凭证与数据保留；
16. 日志、指标、Trace、健康、诊断与告警；
17. 构建、打包、升级、发布、部署与平台集成；
18. 测试策略、fixture、兼容性与生产验收门。

固定轴只强制提问，结论必须来自当前仓库。比如没有数据库的纯库项目可把第 6 轴标为 `not-applicable`，但要引用状态实际只存在内存/调用方的证据；不能因没看到数据库目录就跳过。

### 2. 机械发现系统入口

在一次产品读取中额外枚举：

- executable/library bootstrap、server/app factory、desktop/mobile host；
- schema、migration、durable object、enum、transition 与 transaction boundary；
- router、protocol/message registry、event producer/consumer；
- worker/scheduler/queue claim、lease、retry、cancel 与 recovery；
- config schema、environment loader、secret source、provider factory；
- filesystem/network/process/tool execution boundary 与 sandbox；
- logging/metrics/health/crash/update/deployment configuration；
- tests 中明确验证的异常、并发、重启和安全不变量。

先枚举注册点与状态载体，再用 CodeGraph 补调用、读写和消费者。只靠目录树或依赖名不能认定机制已经接线。

### 3. `system_capability` 必填字段

| 字段 | 内容 |
|---|---|
| `system_capability_id` | 稳定唯一 ID |
| 审计轴 | 上述 1–18 中的一项 |
| 系统责任 | 它保持哪条运行、不变量或平台能力 |
| 启动/触发 | bootstrap、request、event、timer、state transition 或 operator action |
| 控制规则 | 真正读取的字段、状态、顺序、锁或策略 |
| 状态载体 | 表、文件、内存、队列、句柄、token、checkpoint 等 |
| 消费者 | 哪些业务 surface/capability 或其他系统能力依赖它 |
| 失败与恢复 | fail-open/closed、retry、cancel、restart、repair 边界 |
| 运行边界 | process、thread、container、browser、device、external provider |
| 证据 | 注册、实现、状态和测试的相对路径、符号与行范围 |
| 支持状态 | `verified-runtime` / `verified-local` / `partial` / `declared-only` / `external` / `unknown` |
| 关联 | `surface_ids`、`capability_ids`、上游/下游 `system_capability_ids`；纯支撑机制可标 `platform-support` |

每个适用审计轴还要给出：具体能力数、已关联数、纯支撑数、未解析数、关键缺口。系统能力不得因为“不直接出现在菜单”而消失，也不得因为“是通用模块”而只列目录名。

## 产品表面与业务功能归并

### 六路 origin 并集

`stages/02-product-surfaces.md` 继续保存归并后的产品表面。它从以下六路 origin 取并集，其中用户动作一路必须引用 `entry_id`，系统机制一路必须引用 `system_capability_id`：

1. README、官方文档、manifest 与产品承诺；
2. `02-business-entries.md` 中的全部用户/调用方动作；
3. API、IPC、CLI、deep link 与自动入口；
4. 持久业务对象、状态机、消息、任务、产物与关系；
5. Worker、调度器、trigger、webhook 与无人值守结果；
6. 外部服务、协议、配置、Skill/插件/知识/权限及相关系统能力。

每个原始观测项分配 `origin_id`，保存类别、公开名称/动作、源码位置和归并理由；一个或多个 origin 才能归并成 `surface_id`。阶段末尾给出六路各自 `origin_count`、合计、已映射和未映射 ID。

### `product_surface` 必填字段

| 字段 | 内容 |
|---|---|
| `surface_id` | 稳定唯一 ID |
| `origin_ids` | 六路 origin 的非空 ID 集合 |
| `entry_ids` | 对应业务入口；没有直接入口时写原因 |
| 使用者与目标 | 谁为了什么结果使用它 |
| 用户动作与输入 | 用户/调用方真正提交什么 |
| 可见结果 | 用户或下游能观察到什么 |
| 业务状态 | 创建、修改或读取的对象/状态 |
| 入口证据 | 页面/API/命令/事件的路径、符号和行范围 |
| 执行闭环证据 | 执行器、状态提交、结果消费者的路径、符号和行范围 |
| 系统依赖 | 支撑它的 `system_capability_ids` |
| 支持边界 | `verified-runtime` / `verified-local` / `metadata-only` / `catalog-only` / `external` / `unknown` |

`verified-runtime` 要求入口、执行、状态和结果消费闭合。`verified-local` 表示仅当前本机/单进程闭合。`metadata-only` 表示字段可保存或展示但执行器未读取。`catalog-only` 表示只有目录、选项或空适配器。`external` 表示依赖仓库外实现。`unknown` 表示证据不足。

### 从表面归并业务功能

只有同一使用者目标、同一权威业务状态、同一结果消费者和同一失败边界共同闭合时，才能将多个 surface 归为一个 capability。满足任一条件时保留为独立功能或清晰子功能：

- 有独立用户动作和可见结果；
- 有独立持久对象、成员关系、生命周期或权限边界；
- 执行位置、协议、控制者或失败语义对技术选型产生实质影响；
- 是项目的主要采用理由，而不是只被另一功能内部调用。

核心功能必须同时满足：独立业务结果；公开触发到关键转换再到权威状态/外部副作用/消费者的闭环；属于主价值、完整领域生命周期、决定运行范式的控制机制或关键外部闭环；移除后会破坏主要旅程或采用理由。普通 CRUD、health、登录壳、导航、样式、通用表单、路由汇总、开发工具、example、测试和部署 helper 默认进入 `[支撑]` 或 `[排除]`，除非有上述证据。

`stages/02-capabilities.md` 每项必须列出 `surface_ids`、`entry_ids` 和 `system_capability_ids`，并先列核心准入证据。每个 surface 只能出现在 `[纳入]`、`[合并]`、`[支撑]`、`[排除]`、`[待核验]` 中一次。

## 双向闭包与发布门

在 `02-capabilities.md` 末尾输出三张反查表：

1. `entry_id → surface_id → capability_id/处置`；
2. `capability_id → surface_ids → system_capability_ids → evidence/chapter`；
3. `system_capability_id → consumers(capability/surface/platform-support) → engineering/chapter`。

必须同时满足：

```text
业务入口：每个 entry_id 恰好一个处置，unresolved = 0
产品表面：每个 surface_id 恰好一个处置，待核验的核心用户结果 = 0
业务章节：核心 capability 数 = evidence 数 = implementation 正文数
系统能力：每个适用 system_capability_id 至少一个 consumer 或明确 platform-support
系统审计轴：18 轴都有状态和证据，unresolved = 0
反向覆盖：每个核心 capability 至少依赖一个已验证 system capability
```

任一等式、唯一性或反向关系失败，停止在 capabilities；不得靠正文补写或继续 render。最终 Markdown/HTML 必须显示按平台/入口种类的业务覆盖和按审计轴的系统覆盖，不只在 manifest 中藏数字。

## 配置、协作与外部集成

对配置、模板、Skill、插件、知识、记忆、权限、模型或协议适配，evidence 必须追踪：

`UI/API 收集字段 → 校验/默认值 → 持久化 → runtime loader → executor 消费 → 可见行为`。

任一环没有证据就写“未证明”并降级，不能因为页面可保存、数据库有字段或仓库另处存在执行器就宣称已接线。

对群组、群聊、多 Agent、Worker 群、工作流协作或外部 IM，必须回答：成员与授权边界；无选择/单选/多选的执行者；串行、fan-out、DAG、动态规划或订阅语义；中间结果是否互见；聚合者；部分失败/取消/重试/幂等；真实外部 provider、身份、收发链和持久消息 ID。当前入口没有调用到某调度器或协议，就不能把同仓库的独立机制拼进因果链。

## Good / Bad

**Good**：Sidebar 有“项目 → 知识 → 导入”菜单，页面里又有“URL、文件、视频”三个 tab。台账保留一条菜单层级和三个动作叶子，并分别追到 handler；它们可归为同一“采集知识”功能，但不会因为页面名已覆盖而漏掉视频下载的独立 Worker/失败边界。

**Good**：系统台账发现会话鉴权、媒体 Worker、PostgreSQL 迁移、幂等队列和健康探针。即使其中只有媒体采集直接出现在业务章，其余仍在对应审计轴说明消费者、不变量、恢复和证据。

**Bad**：只从 README 生成五个功能，再用路由和 CodeGraph 为这五个功能找证据；候选之外的菜单和系统机制永远看不见。

**Bad**：看到一个 `Settings` 页面就写“设置功能已覆盖”，却没有枚举其中的 provider、权限、插件和网络动作，也没有检查这些配置是否被运行时读取。
