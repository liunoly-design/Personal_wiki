# Dots 真实调用与独立发行

状态：2026-11-16 用户确认开始。dots 实际触发验收 → 独立打包 → GitHub 发行。当前 CLI/媒体/Wiki 的既有真实验收不能替代 dots 入口验收。

## 已确认需求

1. 用户通过 dots 发链接、文字或可访问的本地音视频，返回持久任务 ID，并跟踪至 Wiki 可回读、可检索的 complete。
2. 独立交付摄取 CLI、Mini 转录服务、Wiki 接入模块及薄 skill；附安装、配置、升级和故障处理说明，安装包发布 GitHub。
3. 包含 LLM Wiki 本身的安装和配置流程。固定明确版本和完整性校验，保留来源及许可证；项目安装器与官方桌面应用分别标明。
4. 发布可用的配置模板与说明，实际令牌、账号、私人资料、会话、运行状态及模型权重不随代码和发行包发布。
5. 首轮继续 Air 上的 Wiki 正式写入端、Mini 媒体后端。全栈迁移 Mini 不作为默认副作用，不重放旧飞书队列。

## 实际接入闸门

当前全局 personal-wiki skill、launcher、worker 和 Mini 通用转录已启用。用户已从 dot 发起合成文字及公开 X 媒体任务，并提供 complete 回执；本会话按同一任务复核，原文标识、来源、Wiki回读和全文检索通过。真实触发依据是用户的 dots 回执，本机会话的 CLI 核验是补充证据。

公开视频命中已有完整快照，复用已有媒体、完整 ASR 与26段中文机器译文；本次没有重新下载或转写。两项入口验收通过，开始独立发行实施。原始回执和具体运行ID保留于私有验收空间，不进入代码仓库。

## 用户可直接发送的 dots 验收指令

在已连接的 MacBook Air 上创建本地任务，读取 `/Users/mac/.codex/skills/personal-wiki/SKILL.md`。

1. 执行 `/Users/mac/.local/bin/personal-wiki doctor`，核对主机、Wiki 和媒体就绪，不输出令牌。
2. 执行以下合成文字任务：

```sh
personal-wiki submit --text 'Dots 接入验收：这是一条合成测试资料，用于验证 dots 调用、持久任务和 Wiki 完整入库。验收标识 DOTS-WIKI-20261116。' --name dots-wiki-acceptance-20261116 --request-id dots-wiki-acceptance-20261116-v1
```

3. 保留返回 ID，使用 `status` 跟踪；必要时对同一 ID `run`。complete 后回传主机、任务 ID、Wiki 来源路径及实际核验结果。queued 只说明已登记。
4. 后续公开视频样本采用 `https://x.com/OpenAI/status/1993381101369458763`；复用同一来源名 `x-voice-mode-speech-transcript`，使用独立且稳定的 dots 请求 ID，报告成果复用与阶段证据。不要通过新请求 ID 绕过失败预算。
5. 云端附件必须先落到执行电脑的真实文件路径，再 `submit --file`，不能假定聊天附件已自动传到 Mini。

## 发行交付物与依赖

| 交付物 | 交付要求 | 阻塞 |
| --- | --- | --- |
| dots 入口验收 | 原始触发来源、主机、任务 ID、complete、来源回读和搜索证据，私有回执不入库代码 | 已验收 |
| 摄取 CLI 安装包 | 无开发 checkout 安装、配置初始化、doctor、worker 安装/卸载、只转换不依赖 Wiki；平台依赖明确 | dots 验收通过后实施 |
| Wiki 接入安装包 | 目标库身份校验、受保护发布/回读/检索，独立初始化与诊断；不绕过原件与人工内容保护 | dots 验收通过后实施 |
| Mini 转录服务安装包 | 包含完整可运行服务与依赖清单，不只打包当前扩展；复用单 worker、鉴权、持久恢复和来源证据 | dots 验收通过、核对完整服务源码/许可证 |
| LLM Wiki 安装与配置 | 官方固定版本下载/哈希、安装位置、项目注册、API、关闭重复自动摄取、模型选择、诊断和回滚；新库与已有库分开 | 与 Wiki 接入包一起验收 |
| skill 和安装说明 | 安装后可被相应环境发现，动态定位 CLI，不绑定开发者绝对路径，说明 dots/本地/云端附件区别 | 各安装入口实际存在 |
| GitHub Release | 明确版本的安装包、SHA256SUMS、配置样例、来源/许可证、变更说明、已验证平台与限制 | 各独立安装/真实调用验收通过 |

## 测试和发布边界

沿用 CLI、Mini HTTP、Wiki 发布和回读的公开接口；增加用户实际调用的安装器接口。以空目录/隔离 HOME 安装、卸载及升级验证，防止测试修改正式 Vault、生产配置或其他项目。

最小验收覆盖：从下载包安装、doctor、合成来源转换与入库、公开媒体接入、重复输入、失败续作、拒绝 symlink 与路径越界、配置凭据不进入包、旧配置/原件不被升级覆盖。Mac Apple Silicon 为已知环境；其他平台未经测试不标支持。模型下载、系统包管理器、应用权限和账号登录按实际环境处理，不内嵌现有账号或模型缓存。

配置模板分清 CLI、Wiki 连接、媒体服务、LLM Wiki 应用设置。配置中的路径、端口、Python/Node/Codex/FFmpeg 和模型位置可配置；私有令牌由本机文件引用或受控初始化生成。Wiki 的讨论和关联仍由 LLM Wiki 提供，不在 dots skill 复制知识引擎。

## 配置与上游依据

发行准备样例见 `config/examples/README.md`。LLM Wiki固定版本以 `upstream-nashsu.json` 为准，对照[官方 v0.6.11 Release](https://github.com/nashsu/llm_wiki/releases/tag/v0.6.11)，不随打包工作静默升级。dots的电脑访问和Codex连接是独立授权，参见[官方说明](https://learn.chatgpt.com/docs/dots/computers-and-apps)。

## 验收记录

- 既有公开样本和 Mini 服务：见 `generic-media-acceptance-2026-11-16.md`；属于前置基础能力。
- dots 真实发起：用户 dots 回执与本机同任务复核均通过（文字及公开视频复用）。
- 独立安装包、GitHub Release、LLM Wiki 新环境安装：尚未实施/验收。
