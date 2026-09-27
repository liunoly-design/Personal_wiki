# nashsu MCP、Agent 与文档加工能力映射

日期：2026-09-27。性质：源码核对与实施建议，不代表新功能已接通。本次没有读取令牌、私人 Vault 正文，也没有调用模型或修改应用配置。

## 版本与三层能力

- **已安装版本**：v0.6.11，提交 `e8082119649e6a8e1cf85eaf289adcabfdf39d4e`；与本地源码 `.local/research/nashsu` HEAD 一致。在线 [latest release](https://github.com/nashsu/llm_wiki/releases/latest) 本次仍指向 v0.6.11。
- **主分支**：在线 main 与本地 origin/main 核对为 `78e4b4071f68f4c581aa14cdf0d2e68b6435c162`，package 标记 0.6.12。该版本新增 MCP 页面写入、图谱分页、生成中断恢复等；不能把主分支能力当成已安装能力。[版本记录](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/src/lib/changelog.ts#L30)
- **MCP**：将桌面本地 HTTP API 包装成标准工具；应用需运行，开启 API 与 MCP，并遵守令牌和项目边界。[MCP 文档](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/README.md)
- **官方 Agent Skill**：给外部 Agent 的 HTTP 调用操作说明，主要是搜索、读页、引用回答、查图和扫描。它不是模型服务，也不是文档加工引擎；当前官方 Skill 的 `/chat` 仍标 501，已落后于 v0.6.11 源码。[官方 Skill](https://github.com/nashsu/llm_wiki_skill/blob/main/SKILL.md)
- **应用内 Agent**：具备检索、生成、受限写文件、加载项目 Skill 和经授权执行命令的运行时。另有前端摄取编译流水线，不能把“桌面摄取可用 Codex CLI”推导为“MCP chat 可用 Codex CLI”。[后端 Provider](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/provider.rs#L63)

## 已安装 MCP 的 11 个工具

| 工具 | 可直接复用的能力 | 边界 |
|---|---|---|
| `llm_wiki_status` | 健康与当前项目 | 诊断可用不等于其他工具可用 |
| `llm_wiki_projects` | 已登记项目列表 | 使用应用登记项目 |
| `llm_wiki_set_project` | 固定 MCP 进程项目 | 固定后拒绝跨项目调用 |
| `llm_wiki_files` | 文件列表 | 受 API 路径白名单限制 |
| `llm_wiki_read_file` | 文本文件内容 | 不负责把二进制原件转 Markdown |
| `llm_wiki_reviews` | 待审项与筛选 | 没有对应 MCP 应用待审工具 |
| `llm_wiki_search` | Wiki 关键词/向量搜索 | 向量配置与费用另计；当前保持关闭 |
| `llm_wiki_chat` | 问答、引用、使用量、工具事件 | 后端 HTTP 模型要求见下文 |
| `llm_wiki_graph` | 图谱节点与关联 | 图谱以 Wiki 页面为基础 |
| `llm_wiki_rescan_sources` | 扫描新增/变更来源 | 异步入队，不等于加工完成 |
| `llm_wiki_embed_page` | 页面向量索引 | 不是全文翻译或排版 |

以 [v0.6.11 工具注册源码](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/mcp-server/src/index.ts#L34) 为准。**main 0.6.12 另有第 12 个工具 `llm_wiki_write_page`**：仅允许 `wiki/` 下 Markdown，覆盖需显式参数，成功前校验实际持久化；本机尚无此工具。[主分支注册源码](https://github.com/nashsu/llm_wiki/blob/78e4b4071f68f4c581aa14cdf0d2e68b6435c162/mcp-server/src/index.ts#L190)

## 内置 Agent 的能力

[内置工具清单](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/tools.rs#L421) 注册 14 个工具：

| 分组 | 工具 | 实际意义 |
|---|---|---|
| 内部检索 | `wiki.search`、`wiki.read_page`、`source.search`、`graph.search` | 搜知识页、读页、搜来源片段与关联 |
| 扩展检索 | `web.search`、`anytxt.search`、`deep_research.run` | 需启用对应来源、服务与配置；MCP deep 不等于完整桌面深度研究流程 |
| 生成 | `llm.generate` | 基于上下文生成回答 |
| 写作 | `wiki.write_page`、`workspace.write_file`、`workspace.append_file` | 可写受限 Wiki 页或 agent-workspace 产物；Wiki 覆盖需要显式参数 |
| Skill | `skills.load`、`skill.read_file`、`shell.exec` | 加载说明/参考；shell 需活动 Skill 和命令审批 |

这些是 Agent 的内部工具，不是 14 个独立对外 MCP 工具。用 Prompt/Skill 可以要求中文翻译和整理，但工具清单里没有专门的“全文翻译”和“Markdown 排版”服务；结果完整性需要额外工作流与验收。shell 的活动 Skill 与审批检查见 [runtime](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/runtime.rs#L1908)。

## 与用户功能的映射

| 所需功能 | 现成能力 | 仍需补齐 |
|---|---|---|
| 来源进入知识库，生成来源卡、概念及关联 | Source Watch、ingest 编译、Schema、Review | 飞书入口、平台采集、任务幂等和回执仍由当前项目负责 |
| 搜索、读页、关联与讨论 | MCP search/read/graph 可复用 | 根目录 glossary 不在标准文件读取及 Wiki 索引范围；需适配 |
| 英文资料生成中文知识页 | 已有输出语言配置与语言约束 | 中文来源摘要不是完整中文译文 |
| 英文文章全文翻译 | 通用模型 + Prompt/Skill 可承担 | 独立译文文件、逐节完整性、术语一致性、代码/引用保留、长文失败恢复 |
| 原文件转 Markdown | 桌面文档解析支持多种格式 | 不存在通用 MCP 转换工具；还需选定对接入口并验收实际样本 |
| 转 Markdown 后排版 | 解析器保留部分结构，生成 Prompt 约束标题、frontmatter、表格、代码块 | 独立排版步骤、图文顺序、链接有效性、无删改正文等验收 |

转换实现：Office 类 `.doc/.docx/.docm`、PowerPoint 家族、Excel 家族、ODT/ODS/ODP/RTF 走 AnyDoc 与兼容解析；PDF 走 PDFium，可选 MinerU；电子书有 EPUB/MOBI；Org 有转换器。格式被代码列为支持不代表所有复杂版面都已在本机实测。[格式分派](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/fs.rs#L14)、[Office 转换](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/commands/fs.rs#L593)、[可选 MinerU](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src/lib/ingest.ts#L692)。

中文输出已有配置：`outputLanguage` 显式配置优先；auto 随来源语言。自然语言标题和正文可设中文，专有名词、标识符、URL 等按规则保留。摄取还有粗粒度语言检测，但按文字家族判断且只采样正文，不能当作全文翻译质量保证。[语言规则](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src/lib/output-language.ts#L11)、[语言检测](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src/lib/ingest.ts#L1472)。默认生成对象明确是来源摘要、实体/概念页和日志，并非原文全文复刻。[生成 Prompt](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src/lib/ingest.ts#L2241)

## 关键限制与建议

1. **问答模型链路需区分**：v0.6.11 后端明确排除 `codex-cli`/`claude-code`；仅有 CLI 配置时不能据此承诺 `/chat` 生成式讨论。可先让外部 Agent 调 MCP 检索并用其已有模型回答。[Provider](https://github.com/nashsu/llm_wiki/blob/e8082119649e6a8e1cf85eaf289adcabfdf39d4e/src-tauri/src/agent/provider.rs#L63)
2. **原件与阅读版分开**：建议保留原件和原始提取稿，另外产出排版阅读版；英文另产中文译文，再将这些派生物交给知识编译。目录及命名待用户讨论，不把建议写成已确认 Schema。
3. **先定义排版目标**：建议保留原文结构、列表、引文、图片位置、表格、代码与公式，清理抓取噪声和断行；重写标题、增加导读或重组章节应另行确认。
4. **既有实测不外推**：当前真实 X/微信归档和编译已通过，但没有据此证明全文翻译、通用 PDF/Office 高保真转换、查询讨论都已接通。[本机实测](nashsu-install-test-2026-09-27.md)、[既有 MCP 适配边界](nashsu-mcp-skill-reuse.md)。
