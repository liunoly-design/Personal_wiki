# 用户指定的两个 LLM Wiki 项目：源码核查

调查日期：2026-09-27。只读 GitHub API、README 和浅克隆源码；未安装、运行测试、读取账号或向真实 Vault 写入。以下为选型建议，不代表已确认采用。

## 结论

**如果重点是复用完整知识编译产品，nashsu/llm_wiki 值得先做集成原型；如果重点是继续使用 OpenClaw + Codex 的现有运行方式，nvk/llm-wiki 的技能与本地工具更贴合。** 不能把前者误称为没有 API 的纯桌面软件，也不能把后者的 Agent 命令误称为现成无模型依赖的摄入服务。

两个项目均支持 Raw 与派生 Wiki 分离。当前验收需要来源摘要、概念/实体、主题/综合及交叉引用，不能用“生成单张资料卡”代替 Wiki 编译。

## 热度与时间快照

| 项目 | Stars | Forks | pushed_at（UTC） | 默认分支最新提交及日期 |
|---|---:|---:|---|---|
| nashsu/llm_wiki | 20,003 | 2,264 | 2026-09-27 09:31:44 | main，`78e4b4071f68f4c581aa14cdf0d2e68b6435c162`，2026-09-27 09:31:04 |
| nvk/llm-wiki | 1,349 | 128 | 2026-09-15 14:48:29 | master，`1224fbcdf3827f4ba56d225a9e359f5e8a5594e5`，2026-09-15 14:48:27 |

直接来源：[nashsu API](https://api.github.com/repos/nashsu/llm_wiki)、[其最新提交 API](https://api.github.com/repos/nashsu/llm_wiki/commits/main)、[nvk API](https://api.github.com/repos/nvk/llm-wiki)、[其最新提交 API](https://api.github.com/repos/nvk/llm-wiki/commits/master)。Stars 会变化；pushed_at 不能单独证明维护质量，也可能对应非默认分支。本次补查默认分支提交以避免这个误判。

## nashsu：完整桌面应用，可外部集成

- 产品形态为 Tauri/Rust + TypeScript 桌面应用，Markdown 存储、Wiki 检索和知识图谱都有实现；原件在 `raw/sources/`，编译页在 `wiki/`，包括来源、实体、概念等页面。规则与目的文档在 `wiki/schema.md`、`wiki/purpose.md`，三层是逻辑分工，未必对应三个顶层目录。[中文 README](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/README_CN.md)
- **已经存在本地 HTTP API 和 MCP**。API 的 `POST /projects/{project_id}/sources/rescan` 调用文件扫描；适合外部采集器写入来源后触发扫描，也可供 Agent 检索和读取知识。[API 路由和 rescan](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src-tauri/src/api_server.rs)
- **仍需验证后台运行**：摄入执行器 `autoIngest` 与队列位于 TypeScript 应用侧，`enqueueIngest` 要求活动项目匹配，另有非活动项目批量队列。存在 API 不等于已有独立 headless 编译 CLI。应在原型中验证应用常驻、窗口关闭、项目切换、崩溃重启时飞书任务的行为。[摄入队列](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/ingest-queue.ts)、[摄入实现](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/ingest.ts)
- 模型适配中有 Google 原生 `generateContent`/`streamGenerateContent`，以及 `codex-cli`。Rust 的 Codex transport 实际调用 `codex exec --json`，并非仅声称“兼容 Agent”。Gemini 日常处理、Codex 复杂任务在技术方向上可行，自动升级策略需我们补充。[模型实现](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/llm-providers.ts)、[Codex transport](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src-tauri/src/commands/codex_cli.rs)
- 原件保护已有实际代码：`isSafeIngestPath` 只允许生成到 `wiki/`，拒绝绝对路径、`..` 等；不是单靠提示词。`IngestCommitCoordinator` 按启动顺序串行提交；文件同步模块有队列锁和并发测试。不过通用 `write_file` 允许写绝对路径，不能声称整个应用对 Raw 的所有入口均实施不可变约束。还需检查外部导入覆盖、跨进程锁、宕机原子性。[摄入路径约束](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/ingest.ts)、[提交协调器](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/ingest-commit-coordinator.ts)、[文件命令](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src-tauri/src/commands/fs.rs)
- 测试文件包括摄入路径清理、源路径碰撞、队列集成、模型适配和 Rust 文件同步测试。本次仅确认存在与检查代码，未执行，不声称测试通过。[源码目录](https://github.com/nashsu/llm_wiki/tree/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib)
- LICENSE 正文为 **GNU GPL version 3**；GitHub API 识别为 `NOASSERTION`，不可将 API 的空判定当成没有许可证。[LICENSE](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/LICENSE)

## nvk：Agent 技能与确定性本地工具

- 提供 Claude、Codex、OpenCode 和便携 Agent 指令包；单个主题 Wiki 含 `raw/`、`wiki/concepts/`、`wiki/topics/`、`wiki/references/`、`output/`、`schema.md` 和索引。默认是 Hub 下多个独立主题 Wiki，和我们统一 Vault 的期望需要映射，不能直接照搬默认目录。[README](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/README.md)
- 不是完整常驻后台服务；`/wiki ingest`、`compile` 等核心流程由 Agent 按工作流执行。Python `scripts/llm-wiki` 则实装 lint、schema、archive、retract、adapter、specialist 和 checkpoint 等命令；CLI 参数中没有一个等同完整 LLM 摄入编译器的 `ingest` 子命令。[CLI 实现](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/scripts/llm-wiki)、[摄入指令](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/claude-plugin/skills/wiki-manager/references/ingestion.md)
- 原件不可变、同名追加后缀、修订写新原件是摄入指令要求；CLI 存在原子操作、检查和测试，不意味着所有 Agent 文件写入都被该 CLI 强制约束。外层仍须做原件只增不改、消息幂等、写入队列与恢复。[摄入指令](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/claude-plugin/skills/wiki-manager/references/ingestion.md)、[CLI](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/scripts/llm-wiki)
- 已有 Codex 专门打包和运行验证脚本。便携技能可以由既有 OpenClaw Wiki Agent 读取；Gemini 的实际编译质量和调用路径需要验证，不能将“任何 Agent”营销描述等同全部模型都经端到端测试。[运行与同步测试](https://github.com/nvk/llm-wiki/tree/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/tests)
- private adapter 注册与路由可用于接入我们已经验证的 X、微信公众号脚本，不必使用其默认网页抓取流程。现有库不等于已包含当前账号、微信文章或 X 视频的可靠抓取。[Adapter 协议](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/claude-plugin/skills/wiki-manager/references/adapters.md)
- MIT 许可证。[LICENSE](https://github.com/nvk/llm-wiki/blob/1224fbcdf3827f4ba56d225a9e359f5e8a5594e5/LICENSE)

## 引入建议与最小验证

这是建议，不是已经执行的迁移：

1. 保留 Personal-Wiki 现有 Git 历史、AGENTS、需求、Matt Pocock skills。上游应固定 commit 引入独立目录或单独 fork，记录升级来源；不要把下载上游 AGENTS 覆盖本仓库当成安装步骤。
2. 真实 Vault 使用用户确认的 `/Users/mac/Documents/Personal-Wiki-Vault`，与代码分离。先用合成样本临时 Vault 验证，禁止把真实原文、附件、模型密钥和运行状态提交代码仓库。
3. 若选 nashsu，先验证外部来源落盘 → rescan → 来源摘要 → 概念/主题与链接 → 可查询回执的全链路；失败时判断是小幅适配还是必须拆出 headless 核心，再决定是否 fork。
4. 若选 nvk，直接复用摄入、编译、lint 的工作流和工具，在现有 OpenClaw 调用链外加可靠写入边界。避免为追随上游默认 Hub 结构把个人知识过早切成隔离主题库。
5. 两者共同验收：原件哈希不变；重复消息不重复归档；重新处理同源保留新快照；Source→Raw、Concept/Topic→Source 链接可解析；中断可恢复；视频仅附件和元数据，未经转录不得编造内容摘要。

### 最终选型倾向：先选 nashsu 做唯一主底座原型

结合用户明确要“在已有库上迭代”，优先采用 nashsu：知识编译、模型适配、来源页、关联图谱和恢复队列已有实现，能减少重复建设。现有 Mac 本来承担 OpenClaw 常驻运行，可先接受桌面应用常驻这一约束。nvk 保留为对照资料，不建议同时维护两套编译协议。

关键限制已从代码证实：HTTP rescan → Rust 文件同步 → `file-sync://changed` 事件 → TypeScript `project-file-sync.ts` 判断配置并调用 `enqueueInactiveProjectBatch` → `ingest-queue.ts` 调用 `autoIngest`。**编译确实依赖应用的 TypeScript 运行环境，不是独立 Rust/HTTP 摄入 worker**。离线窗口关闭状态是否继续处理，必须原型测试；进程退出后必然不能靠独立 MCP 自动完成编译。若用户要求完全无桌面进程，才应改选 nvk Agent 流程或评估拆出 nashsu worker，不能先承诺免费获得 headless 能力。[事件到队列的关键源码](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/project-file-sync.ts)、[队列到编译器](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/ingest-queue.ts)
