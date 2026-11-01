# LLM Wiki 远程库与 Mac mini 部署核查

日期：2026-11-01。范围：只读源码与 OpenAI 官方文档核查；没有连接 Mac mini、启动服务、读取凭据或私人正文。本文证明代码能力，不证明目标电脑已经部署或接管。

## 结论

建议把 **LLM Wiki 桌面应用、正式 Vault、Personal Wiki 的运行状态和受保护写入程序放在 Mac mini 同机**。dots 连接 Mac mini 后调用该机 skill/CLI；本机或手机只是发起任务、阅读回执。这样对于使用者是“远程知识库”，对于 LLM Wiki 和文件写入程序仍是本地磁盘项目。

**不能说 LLM Wiki 完全不支持远程 API。** 核对的官方 v0.6.11 源码支持可选局域网监听，MCP 客户端也可指定 API 基址。但“其他程序访问 Mini 的 API”和“本机 LLM Wiki 桌面应用切换为 Mini 后端”是两种能力。后者在本次核查中没有找到已实现配置或验收依据。

## 核查基线与证据

本机参考克隆：`/Users/mac/Documents/personal_OS/Personal-Wiki/.local/research/nashsu`；origin 为 `https://github.com/nashsu/llm_wiki.git`。`git rev-parse HEAD` 为 `e8082119649e6a8e1cf85eaf289adcabfdf39d4e`，`git describe --tags --always` 为 `v0.6.11`，`package.json` 为 `0.6.11`。`git status --short` 为空；`server_bind.rs` 在 Git 跟踪中，`git show <commit>:src-tauri/src/server_bind.rs` 确认下述 LAN 能力已经提交，相关文件与 HEAD 无差异。没有校验本机或 Mini 已安装二进制是否来自这一 commit。

### 1. 桌面应用与文件 Vault

- 已证实：`open_project` 接受文件系统路径，再检查目录、`schema.md` 和 `wiki/` 是否存在。此接口不是远程数据库连接串。[打开项目源码](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/project.rs#L244-L263)、[目录校验](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/project.rs#L342-L360)
- 已证实：关键词检索直接遍历 `wiki/*.md` 并读取文件；可选向量库路径为项目下 `.llm-wiki/lancedb`。Markdown 和附件是内容，向量数据是检索索引，不能以迁移向量库代替迁移正文、附件和业务状态。[全文读取](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/search.rs#L345-L367)、[向量路径](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/vectorstore.rs#L48-L59)
- 未证实：桌面应用存在“连接远程 LLM Wiki 后端”的客户端模式；SMB/NFS 挂载 Vault 后的监听、锁、向量库和中断恢复行为。操作系统挂载路径也许能被当成目录，但本项目没有共享盘行为验收，不能因此承诺可靠远程库支持。
- 建议：Mini 保存唯一正式可写 Vault；本机副本作回退或阅读用途。暂不采用两台桌面应用同时写一个网络挂载库。

### 2. HTTP API 和 MCP

- 已证实：默认绑定为 `127.0.0.1`；环境变量 `LLM_WIKI_BIND_HOST` 可覆盖；`apiConfig.allowLanAccess=true` 使默认改为 `0.0.0.0`，API 实际绑定读取这一逻辑。[绑定配置源码](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/server_bind.rs#L6-L29)、[LAN 配置读取](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/server_bind.rs#L56-L61)、[API 绑定](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L119-L124)
- 已证实：设置 UI 有 LAN 开关，提示重启后监听 `0.0.0.0`。同一 commit 的 README 仍称 `127.0.0.1-only`，与实现不一致；此处以源码与 UI 为依据。[LAN 设置](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src/components/settings/sections/api-server-section.tsx#L321-L338)、[README 旧说明](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/README.md#L440-L458)
- 已证实：MCP 的 API client 可取 `LLM_WIKI_API_BASE_URL`、`LLM_WIKI_API_TOKEN`，通过 HTTP 调用；它是 API 客户端，不是另一个 Vault 存储服务。[客户端配置](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/src/api-client.ts#L183-L191)、[HTTP 请求](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/src/api-client.ts#L338-L354)
- 已证实：API 包括项目、文件读取、Review、搜索、图谱、rescan、embed 和 chat；未见本项目受保护发布协议或视频上传路由。[路由表](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L342-L369)
- 未证实：Mini 的实际监听地址、鉴权、LAN 访问是否启用和可用。开启 LAN 也不会让 dots 云端自动进入私人局域网。
- 建议：本轮沿用 Mini 同机 `127.0.0.1` API；dots 通过已连接 Mini 执行本地 CLI。后续确有跨设备程序访问需求，再验证 LAN 或受保护隧道，无需先开公网服务。

### 3. 桌面进程与无头服务

已证实：二进制入口调用 Tauri `run()`；API 作为桌面 app setup 中的线程启动。MCP 出错提示也要求确认桌面 app 正在运行。[入口](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/main.rs#L4-L6)、[Tauri setup 与 API 启动](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/lib.rs#L551-L606)

未证实：独立脱离桌面应用的官方无头服务部署、注销后继续工作、系统重启后的完整业务恢复。不能把“API 写在 Rust 后端”说成“已验证无头 daemon”。本轮按 Mini 登录会话中常驻桌面 app 设计，系统启动与恢复另做实机验收。

### 4. 本项目集成的职责

| 组件 | 责任与边界 |
| --- | --- |
| LLM Wiki 桌面 app | 编辑、阅读、项目注册、原生 API、检索与图谱；API 随 app 运行。 |
| 正式 Vault | `raw/` 原件和附件、`wiki/` 派生正文、`.llm-wiki/` 原生状态、`.personal-wiki/` 发布历史和提案。隐含目录不能一概当缓存丢弃。 |
| Personal Wiki 受保护写入层 | 校验哈希与路径、文件锁、原件不可覆盖、同字节重放、历史及已有页面待审。 |
| Personal Wiki 任务运行目录 | `tasks/`、`completed/`、`work/`、来源去重记录和恢复进度；独立于正式知识正文，迁移时仍需保留。 |
| 媒体服务 | 下载视频、音轨、机器转写及来源/完整性证明；自身成功不代表 Wiki 已发布。 |
| dots 与 skill | 在连接的电脑上调用既有程序、组织任务和反馈结果；不能绕过写入保护。 |

本项目 [`src/nashsu-api.js`](../../src/nashsu-api.js) L10–17 从**执行电脑**的 app-state 读取按 Vault 路径注册的项目和 token，并固定请求 `127.0.0.1:19828`。因此现有适配器直接放在 Mini 同机执行最符合现状；把它留在 MacBook 并仅修改 Vault 路径不会自动连接 Mini API。

迁移需要保留 Vault 中稳定项目身份，再在 Mini 建立匹配其路径的本机注册并重新配置鉴权；不应整份复制 MacBook 的 app-state、token 或模型密钥。项目 UUID 与本机注册映射不能混淆：源码能从 `.llm-wiki/project.json` 读取项目 ID，但 `projectRegistry` 保存在本机 app-state 中且绑定路径。[注册读取](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L747-L772)、[稳定身份读取](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L851-L857)、[token 来源](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L597-L610)

原生 `sources/rescan` 只调用文件重扫及 Source Watch 配置，**不能作为受保护发布的替代品**。[原生 rescan](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L2523-L2536) 本项目的不可覆盖写入和锁见 [`scripts/protected_store.py`](../../scripts/protected_store.py) L27–112；正式 bundle 发布会先核对原件、保存发布计划、为冲突生成待审，再不可覆盖落盘，见 [`scripts/publish_bundle.py`](../../scripts/publish_bundle.py) L104–172。任务持久化和恢复见 [`src/task-queue.js`](../../src/task-queue.js) L30–70。这里核查的是实现；本轮未重跑测试，也未以此声明 Mini 的真实行为已通过。

### 5. 链接与直接视频文件是两个入口

已证实：现有媒体服务契约 `POST /v1/jobs` 接收 `url + options`，只接受单条公开抖音 URL；客户端也验证平台域名并发送 JSON，未实现文件上传。见 [`docs/contracts/media-service-v1.md`](../contracts/media-service-v1.md) L27–50 和 [`src/media-service-client.js`](../../src/media-service-client.js) L45–52。

因此可先交付“发抖音分享链接 → Mini 下载 → 转写 → 受保护入库”。不能承诺“给 dots 发送任意视频附件就能经现有接口入库”。直接文件入口需要另外定义附件如何落地 Mini、原件哈希和来源、转写调用、大小/时长确认、幂等与恢复；不能把文件伪装成 URL 绕过现有校验。

### 6. dots 调用位置的官方依据

OpenAI 官方说明：dots 可连接一台个人电脑，在其上建立本地 Work/Codex 任务；本地 skill 需要已连接电脑，电脑在线且 ChatGPT app 打开。手机仍可给同一 dot 发请求。由此推荐把 dots 的个人电脑连接选为 Mini，在 Mini 安装并实际调用 Wiki skill。该建议不等于本次已完成账号连接、skill 安装或真实调用。[OpenAI 官方：Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)

## 仍须验证的接管条件

1. Mini 上安装的 LLM Wiki 版本、Vault 路径注册及独立鉴权；自动摄取关闭，防止绕过受保护流程重复处理。
2. 正文、附件、历史、任务状态的一致性；原有未完成任务按原状态恢复，不自动重试未知写入。
3. dots 确实连接 Mini；一次真实 skill/CLI 调用能返回正确执行主机、任务 ID、文件位置和 API 读回证据。
4. 真实 X 和抖音链接端到端处理，以及缺正文、登录、超限和下载失败的暂停/续接。
5. 若需要直接视频附件，独立交付文件输入路径后再验收；桌面远程后端或网络共享盘仍不作为本轮依赖。
