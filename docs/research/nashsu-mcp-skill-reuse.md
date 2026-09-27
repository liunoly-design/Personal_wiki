# nashsu MCP 与 Agent Skill 复用核对

日期：2026-09-27。范围：本地 v0.6.11 源码，提交 `e8082119649e6a8e1cf85eaf289adcabfdf39d4e`；官方 Skill 当日主分支。本文是实施建议，不代表查询、讨论已经接通。本次未读取凭证或调用模型。

## 结论

可以复用。MCP 是本地 HTTP API 的工具包装；Agent Skill 是指导 Agent 调用同一 API 的说明。它们不是另一套知识引擎，也不会替代微信/X 抓取、Flash 基础解释和飞书任务回执。应用必须运行，MCP 还需开启独立访问开关。[MCP 说明](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/README.md)

## MCP 的 11 个工具

| 工具 | 能力 |
|---|---|
| `llm_wiki_status` | 健康状态及当前项目概况 |
| `llm_wiki_projects` | 已登记项目列表 |
| `llm_wiki_set_project` | 将 MCP 进程固定到一个项目，防止跨项目访问 |
| `llm_wiki_files` | 列出允许访问的项目文件 |
| `llm_wiki_read_file` | 读取允许的文本文件 |
| `llm_wiki_reviews` | 查看待审项，可按状态和类型筛选 |
| `llm_wiki_search` | 复用关键词/向量搜索后端 |
| `llm_wiki_chat` | 调用后端 Agent，返回回答、引用、使用量及工具事件 |
| `llm_wiki_graph` | 查询节点与关联，可筛选 |
| `llm_wiki_rescan_sources` | 扫描来源文件并触发异步处理队列 |
| `llm_wiki_embed_page` | 为已有 Wiki Markdown 页建立或替换向量索引 |

以工具注册代码为准：README 只列了前十项，代码另有 `embed_page`。当前不建议开启向量索引，维持已有不新增嵌入费用的选择。MCP 未提供微信/X 抓取、任意写文件或应用 Review 的工具。[注册代码](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/src/index.ts)

## Agent Skill 可以复用什么

官方 Skill 指导 Agent 选择项目、检索、阅读命中页、引用来源回答、查看图谱及触发来源扫描。它直接使用 HTTP 工具，无需 MCP；鉴权与项目边界仍由桌面 API 执行。可复用这套“先搜索、再读页、最后引用回答”的查询流程。[官方 Skill](https://raw.githubusercontent.com/nashsu/llm_wiki_skill/main/SKILL.md)

存在版本差异：该 Skill 仍将 `/chat` 描述为未实现的 501；本地 v0.6.11 已有后端 Agent 实现，不能照抄这个限制，也不能因此推断当前 Codex 配置能生成讨论回答。[API 实现](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L1885)

## 两个必须补齐的边界

### 根目录 glossary 目前不在标准读取和索引范围

文件 API 允许 `purpose.md`、`schema.md`、`wiki/`、`raw/sources/`，不允许根目录 `glossary/`；`files?root=all` 也仅列这些范围。关键词索引和图谱扫描 `wiki/`。因此我们的基础解释虽已落盘，但不能直接通过标准 MCP 文件读取或成为独立搜索/图谱节点。文章中复制进去的解释可能被搜到，不等于基础页本身已接入。

来源：[文件白名单与根目录](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L1005)、[搜索扫描](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/search.rs#L349)、[图谱扫描](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/api_server.rs#L2411)。

建议第一步在我们这一层提供限定 `glossary/` 的只读查询，和 nashsu 结果合并。这样保留基础页不被编译覆盖的边界。统一进 nashsu 索引属于后续改造，需同时实现写保护；不应仅移动目录后假定原件保护仍成立。

### 后端 chat 不直接使用现有 Codex CLI

后端 HTTP 模型判断明确排除 `codex-cli` 和 `claude-code`。没有可用 HTTP 模型时，有检索引用则生成检索式结果，没有引用则报模型未配置；这不是通过 CLI 完成生成式讨论。桌面摄取使用 Codex CLI 已验证，并不能证明 `/chat` 的模型链路也已验证。[Provider 判断](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/provider.rs#L64)、[生成与降级分支](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/runtime.rs#L1175)。

## 建议分工

- **记录**：保留现有确定性脚本，负责归档、去重、附件、Flash 基础页和回执；继续复用 nashsu 来源扫描与编译。
- **查询**：复用 nashsu `search/read_file/graph`，按需加 `reviews`；我们补基础页只读检索与统一展示。
- **讨论**：先让 OpenClaw 调用上述检索能力后，用现有模型生成带引用回答；后续若要复用 nashsu `/chat`，单独验证模型、费用、会话及结果保存。
- **接口选择**：固定飞书插件调用可继续直连 HTTP；给不同 Agent 暴露标准工具时用 MCP。无需同时堆叠两套调用方式来完成一次操作。

这相当于在 nashsu 上增加“飞书入口＋平台采集＋基础概念＋任务可靠性”一层，继续复用底层 Markdown、编译、搜索和图谱。以上选择仍待用户讨论确认。
