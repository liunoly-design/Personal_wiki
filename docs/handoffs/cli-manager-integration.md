# Personal Wiki 接入 CLI 管理 App：开发交接

日期：2026-11-16。对象：负责 CLI 管理 App 的开发 session。
接口基线：Personal Wiki `distribution-v0.9.1`，提交 `09a7191700e3a0c03cfab00bbd69b9708f466a66`。本文是接入说明，**不代表管理 App 已实现集成**。

## 1. 本次要做什么

把 Personal Wiki 作为管理 App 的一个工具接入，管理安装信息、配置、健康、后台服务和摄取任务。通过已发布的可执行入口调用，业务处理留在 Personal Wiki；讨论、检索关联和知识组织仍由 LLM Wiki 提供。

管理首版建议完成：添加已有 CLI、版本/配置识别、分项诊断、自有服务状态与启停，再用合成转换证明可调用。安装升级和 skill 管理按 App 现有能力接入。业务任务表单与任务中心是可选扩展：若需要，复用本文第5—6节，不要求为管理 CLI 另做一套知识产品。实施顺序是建议，不是已有 App 的架构约定；先检查目标 App 的实际代码、进程执行层和凭据管理方式，再选择落点。

接入期间使用隔离配置和合成样本。已有生产实例先识别并展示；本任务不包含自动迁移 Vault、接管旧 worker、复制账号或改写其他个人 OS 项目。

## 2. 模块、主机与执行身份

| 模块/发行组件 | 入口 | 管理 App 的职责 |
| --- | --- | --- |
| 摄取 CLI / `cli` | `personal-wiki` | 提交、只转换、状态、待补、恢复、导出、入库 |
| Wiki 接入 / `wiki-bridge` | `wiki-bridge` | 接收已转换来源包、受保护入库和诊断；可独立安装 |
| Mini 服务 / `mini-media` | `personal-wiki-media` + HTTP API v1 | 网关配置、进程/launchd、鉴权健康；媒体业务通常交给摄取 CLI |
| LLM Wiki 引导 / `llm-wiki-setup` | `python3 llm-wiki-setup.py` | 固定官方应用下载/哈希/安装、配置诊断；不是知识引擎替代品 |
| 薄 skill | `personal-wiki/SKILL.md` | AI 调用指引；不是常驻进程 |

当前生产拓扑是 Air 执行摄取与 Wiki 写入，Mini 提供媒体转录。它是当前实例的部署信息，不是所有安装的固定拓扑。App 为每个实例记录执行主机、用户、可执行路径和配置路径，所有路径都相对于**执行主机**；不能把 Air 的绝对路径直接拿到 Mini 使用。

记录模式下，CLI/bridge 必须能访问目标 Vault，并以能读取 LLM Wiki 应用状态的同一用户运行。v0.9.1 接入器读取当前 HOME 的 `Library/Application Support/com.llmwiki.app/app-state.json`，匹配 Vault 注册项目，连接固定的 `http://127.0.0.1:19828`。目前没有通用远端 Wiki URL/跨用户凭据参数。仅连上 Mini 媒体地址不意味着 Mini 能直接写 Air 的 Wiki。

远端 CLI 的执行器可复用 App 已有的 SSH/主机代理，但要显式选择主机并可靠传输参数。远端执行与 Mini HTTP 是两件事；本项目没有可直接使用的“远程 CLI 管理 API”。

## 3. 发现安装与版本

由用户选择已有可执行文件，或通过 App 的安装流程得到路径。macOS GUI App 不应假定继承交互式终端 PATH；优先保存 Node、Python、Codex 与入口的绝对路径。调用 `--help` 确认可用入口，它返回普通文本。

v0.9.1 **没有 `--version`、`--json` 或能力发现命令**，不要把这些参数作为探测步骤。

安装器管理的 CLI/bridge 可读取这些安装元数据：

| 位置 | 用途 |
| --- | --- |
| `<prefix>/.installation.json` | `component`、`prefix`、`config`；安装归属，不是凭据 |
| `<prefix>/state/runtime/current` | 当前版本的 symlink |
| 当前版本目录的 `.distribution.json` | 语义版本 `version`、源码 `revision`、组件和文件哈希 |
| 当前版本目录的 `.release.json` | `version` 是源码提交标识，**不是语义版本号** |

Mini 使用 `<prefix>/current` 与 `<prefix>/releases/...`，其版本目录同样有 `.distribution.json`。下载解压包的根文件则叫 `distribution.json`，不要混用这些位置。

旧部署可能只有自定义 launcher/config，没有上述安装归属文件。此时登记为“已有部署/版本未知或按实际元数据确认”，支持用户指定配置后的调用；新版 `manage.mjs` 不能直接接管它。安装新包时保留旧入口和配置，另建受管理安装并验证，再由用户明确切换。仅找到新版 GitHub Release 不代表本机已升级。

## 4. 配置模型

**已实现的读取顺序**：显式 `--config` > `WIKI_CONFIG` > 入口默认文件。发行 launcher 会设置自己的 `WIKI_CONFIG`；App 每次传明确的 `--config`，避免指向另一份任务状态。

| 情况 | 默认配置 |
| --- | --- |
| 原始 `scripts/wiki.mjs` /部分旧 launcher | `~/.config/personal-wiki/ingest.json`，旧 launcher 可能覆盖 |
| 独立 CLI 安装器 | `~/.config/personal-wiki/cli.json` |
| 独立 bridge | `~/.config/personal-wiki/wiki-bridge.json` |
| Mini 初始化 | `<mini-prefix>/data/state/config.json`，token 是同目录的 `api-token` |

CLI/bridge 主要字段：

| 字段 | 语义/编辑方式 |
| --- | --- |
| `stateDir` | 本实例持久任务与处理中资料目录；与 Vault 分开，安装器实例固定为 `<prefix>/state` |
| `runtimeRoot` | 安装器版本目录，等于 `stateDir/runtime`；App 作为只读归属字段 |
| `vault` | 执行主机可访问的目标库绝对路径 |
| `python` | 捕获/锁等使用的 Python；Python 可执行入口可能是正常 venv symlink，应保留其路径语义 |
| `codexBinary`、`compilerModel` | 知识编译入口/模型；账号登录由本机配置，App 不复制账号 |
| `mediaServiceUrl` | Mini 的 origin，如 `http://192.0.2.10:8765`；此 IP 只是文档示例 |
| `mediaServiceTokenFile` | CLI 所在主机的 token 文件，当前用户所有，0600；只存路径，不放入命令参数 |
| `autoStart` | `submit` 是否尝试派生后台 `run`；**新安装器默认 false**，不是自动启用 worker |
| `maintenance` | 可选的代码维护配置；需真实独立开发工作区，不能由管理 App 随手填写后假定已运行 |

安装器写出的私有配置是0600。常用字段通过保留解压包中的 `manage.mjs configure` 修改：

```text
node manage.mjs --prefix ABS_PREFIX configure --vault ABS_VAULT --python ABS_PYTHON --codex ABS_CODEX --media-url MINI_ORIGIN --media-token-file ABS_TOKEN_FILE
```

这是参数说明，不是可原样执行的 shell 命令。`configure` 尚没有 `compilerModel`、`autoStart`、maintenance 的专用参数，也没有清空字段的参数。高级编辑如确有需要，应是用户明确执行的私有 JSON 编辑，保留未知字段、0600、安装归属并原子保存；不要伪造 CLI 已支持的 setter。

LLM Wiki 的安装 profile 是要求说明，不能拿来覆盖原生 app-state。bootstrap入口为 `python3 llm-wiki-setup.py install --destination ABS_APPLICATIONS_DIRECTORY`，或 `doctor --vault ABS_VAULT`；支持用 `--archive ABS_ARCHIVE` 离线校验安装，遇到已有同名应用会保留并报错。上游应用语义版本读取安装后 `LLM Wiki.app/Contents/Info.plist`，不能拿bootstrap包的0.9.1当作上游版本（固定为0.6.11）。模型账号、项目注册/API在官方应用内设置，见 [LLM Wiki 安装配置](../llm-wiki-install.md)。

## 5. 调用协议与任务流程

使用 App 后端的进程执行能力；可执行文件与参数数组分离，`shell:false`。不要把用户分享文案拼成 shell、`bash -c` 或 AppleScript 字符串。URL 分享文案作为一个参数保留签名参数；正文参数值采用 `--text=...`，避免以连字符开头的内容被解释成选项。

以下是 **App 侧适配示意，不是新的 Personal Wiki API**。`launch()` 应接 App 自己的受控执行器；`operationId` 必须在首次执行前持久保存：

```js
const common = ['--config', configPath, '--request-id', operationId];
// launch(executablePath, argv, { shell: false, env: approvedHostEnvironment })
const submitText = ['submit', ...common, `--text=${originalText}`];
const submitShare = ['submit', ...common, '--', completeShareText];
const submitMedia = ['submit', ...common, `--file=${absoluteMediaPath}`];
const convertText = ['convert', ...common, `--text=${originalText}`];
const inspect = ['status', jobId, '--config', configPath];
const advance = ['run', jobId, '--config', configPath];
```

同一操作只传一种输入。`--file` 是本地音视频入口，不是任意 `.md/.pdf` 导入；正文没有 stdin/`--text-file` 接口。超长文字还受 OS 参数长度限制，App 应明确报输入过长，后续若需 stdin 能力另开开发任务。

### 操作对应关系

| App 操作 | 已有命令 | 关键行为 |
| --- | --- | --- |
| 环境诊断 | `doctor` | CLI 检查 Wiki/媒体；bridge 0.9.1 的媒体为 `not_required` |
| 提交归档 | `submit` + 一种输入 | 返回已登记任务；不是入库成功 |
| 只取 Markdown | `convert` + 一种输入 | 同步执行到本次可达到的状态，成功为 converted |
| 跟踪 | `status ID` | 读取持久任务，包含已有状态和可选阶段 |
| 执行/续作 | `run ID` | 复用成功阶段；遇到明确等待状态可能原样返回 |
| 列出未完成项 | `pending` | 排除 complete 和 converted，不是完整历史列表 |
| 显式新恢复代次 | `retry ID`，随后 `run ID` | 保留错误历史，重新打开恢复预算；不要后台无限调用 |
| 补料 | `supplement ID --file ABS_FILE`，随后按状态 `run ID` | 支持已有文档约定的正文、截图或音视频；保留用户提供的证据归属 |
| 将已转换任务入库 | `ingest ID` | 把同一任务切为 record 并执行，不必重新获取 |
| 导出来源包 | `export ID --output ABS_NEW_DIRECTORY` | 仅完整 converted/complete；目标必须是新目录 |
| 独立 bridge 入库 | `wiki-bridge ingest --bundle ABS_BUNDLE_JSON ...` | 提交后直接执行；通过桥接器自己的配置/任务 ID 跟踪 |
| 项目维护 | `maintain ID` | 要有真实维护请求/开发环境；首版建议只展示维护状态 |

`--name` 可选，最长100字符，匹配 `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`；不要把中文标题直接当该参数。`--background` 是独立用户说明，完整保留正文。`--refresh` 是明确重新获取/版本化操作，不是普通网络重试。

可携带来源包格式为 `personal-wiki-source-v1`；包含 `bundle.json` 与 `payload/article.md` 等有哈希的原件。导入上限250MiB/2048文件。让 CLI/bridge 校验路径、哈希和发布保护，App 不自行伪造 complete。详见 [CLI 契约](../contracts/ingestion-cli.md)。

### 返回、耗时和错误

普通业务命令通常在 stdout 输出一个 JSON 对象，提交多个链接时可能是任务数组；App 统一转成数组处理，同时校验每个元素。不要假设只会有一个任务。`--help` 返回文本；`worker --watch` 是常驻循环，**不是进度 JSON 流**，正常运行期间没有逐行进度事件。Mini 安装还可能输出依赖日志，不能对所有入口套用“整个 stdout 必为单个 JSON”的解析器。

未捕获命令错误一般退出1，并在 stderr 给出 `{"status":"error","message":"..."}`；JSON 协议尚无统一 schema_version/结构化错误码。程序可能以退出0返回 pending/waiting/partial，因此退出0只表示调用正常结束；以业务状态决定成功。未知状态和字段保留为原始诊断，不硬判 complete。

提交文件会先快照，不能保证毫秒级返回；`convert`、`run`、`ingest`、bridge ingest 可持续转录/模型处理较长时间。建议由后端异步管理进程，前端立即返回 App operation ID；拿到 CLI 任务 ID 后再轮询 `status`。进程没有输出不等于卡死。为诊断/查询设置单独的有限超时；长任务使用独立预算，不能套用几秒钟的 HTTP 超时。

响应丢失或超时时，App 记录“结果未知”，先查原任务。若提交尚未收到 ID，用**原 request-id 与原载荷**重放提交；不要生成新 request-id。进程超时不等于底层 ASR/子进程已经终止，不自动删除原件或改状态。

## 6. 状态展示与幂等

以下是 **App UI 映射建议**；事实源仍是 CLI 的 `status`，未知值应可显示。

| CLI 状态 | 展示与下一步 |
| --- | --- |
| `queued` | 已登记，等待执行；需明确当前由 App `run` 还是已有 worker 驱动 |
| `processing` / `publishing` | 处理中 / 正在入库；展示 `stage` 原值，不能伪造百分比 |
| `converted` | 转换成功；mode=convert 时完成本次目标，mode=record 时仍需入库 |
| `complete` | Wiki 入库及当时的核验已完成，可展示 `result.source` |
| `pending` | 自动轮次结束、材料待补；展示 failure、nextAction、maintenance |
| `waiting_access` / `waiting_login` | 公开访问受限 / 认证缺口；前者不能直接解释成必须登录 |
| `waiting_confirmation` | 触及确认边界；本版没有越限审批接口，App 不能强制放行 |
| `waiting_capacity` / `waiting_dependency` | 额度或依赖缺口；修复后再明确恢复 |
| `waiting_publication` / `waiting_verification` | 入库或核验缺口；保留已有成果，不能显示为已验证成功 |

任务 ID 是64个十六进制字符；Mini 远端任务 ID 是另一套标识，不能拿它调用 CLI `status`。App 任务主键建议使用 `(执行主机, 配置身份, CLI任务ID)`，bridge 的状态目录也单独区分。

App 在发出首次请求前保存稳定 request-id、输入/选项与目标实例。网络重发沿用原载荷；改变 name、background、模式、refresh 或输入后属于另一项明确操作，否则可能得到 `Request identity conflict`。多链接输入可能为每条 URL 形成带后缀的请求身份，使用返回 ID 跟踪，不自行推算哈希。

来源缓存仍会对不同请求做复用；UI应说“复用”而非“重新抓取/转写”。只转换→入库使用原任务 `ingest`。显式刷新要保存旧版本，不通过修改状态 JSON 或换请求ID绕过两轮预算。

`stage` 可能保留最后执行阶段，界面以 `status` 为主；complete 不因保留 translating 而仍显示“正在翻译”。

`status` 读取保存的状态，**不会在每次查询时重新检查 Wiki 正文和搜索**。如需“重新核验成果”按钮，可调用原任务 `run`；对 complete 任务会重新检查原件和 Wiki，失败可能转 waiting_verification。App 应区分“此前已完成”与“本次重新核验通过”。

没有取消、删除任务、完整历史列表、SSE/实时事件或分页接口。首版由 App 保存自己收到的任务 ID，并用 pending 补充未完成项；对 App 之外的已完成历史，不直接依赖扫描私有 jobs JSON 作为公共契约。停止 App 轮询只表示停止观察，不叫“任务已取消”。

## 7. worker、Mini 与服务归属

推荐首版采用一种明确的执行策略：App 提交后启动一次后台 `run`，或启用已有 CLI worker。安装器配置 `autoStart:false` 时只 submit 会一直排队；App必须提示所选策略。不要每次轮询都启动 `run`。即使实现有锁，并发“已在运行”也应转查状态，不能自动 retry 开新预算。

安装包的管理 helper **未安装为 PATH 命令**。App 应保留已校验解压目录及 `install.mjs/manage.mjs/install.py`，并记录 helper 路径；不能假定 `<prefix>/bin/manage.mjs` 存在。

| 管理动作 | 实际入口 |
| --- | --- |
| CLI worker 启用/停用 | 解压包中的 `node manage.mjs --prefix ABS_PREFIX worker-install` / `worker-uninstall` |
| CLI/bridge 卸载入口 | `node manage.mjs --prefix ABS_PREFIX uninstall` |
| skill 安装 | CLI 包 `node manage.mjs --prefix ABS_PREFIX skill-install [--skills-dir ABS_DIR]` |
| Mini worker 启用/停用 | 解压包 `python3 install.py --prefix ABS_PREFIX --action worker-install` / `worker-uninstall` |
| Mini 卸载入口 | `python3 install.py --prefix ABS_PREFIX --action uninstall` |

独立 bridge 不提供 worker-install，按 ingest/run 执行。CLI label 固定 `com.personal-wiki.distribution.cli`；Mini label 固定 `com.personal-wiki.distribution.mini-media`。均是当前用户 `~/Library/LaunchAgents` 的 launchd 项，要求用户登录，不等价于系统 LaunchDaemon；同主机同用户多个 prefix 不能同时抢同一个 label。App遇到其他安装归属应展示冲突，不强行覆盖 plist。旧生产 worker 的名称/启动方式可能不同，只在实际归属确认后管理。

`worker-uninstall` 会移除相应启动项，不是“保留启动项暂停”；可以通过 worker-install 再启用。helper 返回成功后，App 仍应通过当前用户 launchctl 的实际状态/启动日志核对，因为安装记录不等于进程当前活着。停用/卸载后同样核对启动项与进程，helper退出0本身不能替代停服验证。只读取归属于该实例的日志，日志属于私有数据。

Mini 的网关、原生 whisper.cpp 服务器、可选 MLX 翻译是不同依赖；安装网关 worker 不会代管 ASR 服务器启动。默认网关 loopback:8765，原生 ASR loopback:8767；局域网绑定按具体配置，不能硬写某台 Mini IP。

后端可在安全读取 token 文件后请求 Mini `GET /health`（Bearer 鉴权）。v1 成功包含 `api_version:"1"`、`status:"ready"`、`queue_depth`、`worker_count` 等；401是认证缺口，503是未就绪。health 不能证明任何媒体任务已完整转写。先通过 CLI 处理媒体，避免 App 重写上传、来源绑定和转写校验；确需直接接通用接口再读 [Mini 通用媒体规格](../specs/mini-generic-media.md)。

## 8. 安装、升级、卸载

发行页：[distribution-v0.9.1](https://github.com/liunoly-design/Personal_wiki/releases/tag/distribution-v0.9.1)。首版固定适配该版本，不把 GitHub latest 当成无条件兼容协议。

四个包名分别为 `personal-wiki-cli-0.9.1.tar.gz`、`personal-wiki-wiki-bridge-0.9.1.tar.gz`、`personal-wiki-mini-media-0.9.1.tar.gz`、`personal-wiki-llm-wiki-setup-0.9.1.tar.gz`。SHA256SUMS 及各 tar 的同名 `.sha256` 随 Release 提供。由 App 保存所采用的发布版本/摘要，校验下载件、拒绝路径越界的解压内容，再执行安装；同一来源的 checksum 是完整性校验，不是额外的签名背书。

CLI/bridge 安装使用解压包根目录的 `node install.mjs --prefix ABS_PREFIX --config ABS_CONFIG ...`。新安装器验证 Node24+/Python3.9+，推荐统一 Python3.11+，Mini 必须3.11+；已知原生验收平台为 macOS Apple Silicon。Python 捕获依赖、Chromium、Swift OCR、Codex账号、FFmpeg、原生ASR及模型各有配置要求，详见 [独立安装说明](../independent-install.md)。本次新文档不承诺 Windows/Linux 媒体服务或全自动装模型。

**CLI/bridge 升级会在安装成功时直接原子切换 current，并没有独立的 stage/activate/dry-run API。** App要在此之前完成包校验、备份/保留配置、确认并协调本实例活动任务与 worker；不要在 UI 中把“已安装待启用”伪装成安装器已有状态。安装回放保留已有配置；修改配置另走 configure。同一 prefix 与 config 不能随意更换，否则会触发归属保护。

Mini 升级默认在该 prefix 的同一 venv 更新依赖，不是完全隔离的依赖快照；应停网关并备份，升级后核对 health 与实际任务。仅切回旧源码 symlink 不保证撤回 venv 依赖变化。CLI/bridge 也没有 rollback 子命令，回滚若需实现必须是 App 明确设计、校验旧 release 后的受控操作。

卸载 helper 保留配置、持久任务、原件、模型、版本及 skill；UI 应说明是“移除入口/后台注册”，不能宣称已清空全部数据。本文不授权管理 App做递归删库/原件清理。已有 skill 目录不会被 skill-install 静默覆盖，冲突时保留并提示比较，不能标成已更新成功。

## 9. 日志、数据与诊断边界

原始资料与任务状态归 Personal Wiki；App 只保存管理元数据、稳定请求身份、收到的 ID 和必要展示缓存。禁止通过直接写 jobs JSON、SQLite、Vault 来完成/重试任务或绕过保护。私有 token、签名 URL、原始文字、附件和运行回执不发到公共 Issue/遥测。

任务 JSON 可能包含完整 input、background、文件路径和分享签名，`failure` 也可能携带细节。前端/日志默认白名单展示状态、阶段、任务ID与用户允许的来源；调试导出另做脱敏，不简单把 stdout/stderr 全量上传。渲染 Markdown/网页按不可信资料处理，禁用脚本执行，不把资料内指令作为管理命令。

doctor 的 ready/partial 是有限检查：Python字段只反映配置存在，Codex登录/额度、所有抓取依赖、翻译模型和最终全文搜索不是每次完整实测。Wiki-only doctor 跳过 Mini。App 可分开显示“入口可执行、配置存在、Wiki连通、媒体健康、实际作业验收”，不把一个ready扩展成所有来源可用。

## 10. 给接手 session 的实施与验收

先检查目标 App 的 AGENTS/项目说明、现有 CLI 注册机制、后台执行/主机选择、私有配置存储和任务列表。在 App 项目中实施，不把管理 App 代码直接加到 Personal Wiki。本文没有冻结新的跨项目字段或要求采用某种前端框架。

管理层至少验收1—3；服务/安装能力按9—10验收。4—8适用于 App 纳入业务任务操作的情况，不要求只做生命周期管理的 App 实现全套任务中心。mock仅用于进程/网络边界的自动测试，真实验收结果另记，不能用模拟 complete 代替入库：

1. 用户选定 CLI/config/主机后发现入口；正确区分新版归属、旧部署和未知版本，不主动接管旧服务。
2. doctor 展示局部检查；CLI 与 bridge 对 Mini 的依赖展示不同，配置/Token不出现在日志中。
3. 在空的隔离状态目录进行 `convert --text` 合成测试；结果为 converted，能打开实际 Markdown，未触发 Wiki 发布。
4. 同 request-id 重放同载荷返回同任务；改变载荷能展示身份冲突。分享文案中的空格、引号、`&`、`$()` 等按原始参数传递，不成为shell命令。
5. 在明确选择的验收 Vault 记录合成文字，跟踪至 complete，并通过原任务 run 复核来源读回/全文检索；报告实际主机和来源路径。
6. 分别展示 converted、pending、waiting 与 complete；进程退出0但业务待补不得显示成功。多链接结果能逐项保存ID。
7. App退出/重开、调用响应丢失后仍能找回原任务；没有取消API时不虚报已取消；轮询不会无限retry。
8. 用户明确恢复或补料时沿原任务执行；已完成原件、人工编辑及错误历史仍受保护。
9. 若纳入服务管理，测试自有 worker 启用、重复启用、停用、归属冲突；对其他实例/生产服务不产生副作用。
10. 若纳入安装升级，实际从发行包安装、保存helper、升级保留配置、元数据确认版本；卸载保留资料。Mini用独立数据/端口测健康与样本，原生ASR明确由谁管理。

交付时列明已实现功能、真实验收与模拟测试的区别、支持版本、剩余能力缺口。需要新 CLI 接口（版本、完整列表、取消、事件流、stdin等）时，作为独立需求提出，不在 App中伪造这些命令已存在。

进一步查证的源码：`scripts/wiki.mjs`、`scripts/wiki-bridge.mjs`、`src/ingestion.js`、`src/portable-bundle.js`、`distribution/install.mjs`、`distribution/manage.mjs`、`distribution/install-mini.py`、`services/mini-media/gateway.py`。对接以固定版本实际代码为准；状态/能力升级时同步更新本交接。
