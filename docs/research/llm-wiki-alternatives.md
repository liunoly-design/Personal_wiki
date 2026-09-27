# LLM Wiki 其他候选实现

调研日期：2026-09-27。这是选型建议，不是已确认架构；未安装运行、未接入账号、未替换当前仓库。与 nashsu、nvk 的比较由主调研汇总。

## GitHub 当前快照

数据来自各仓库 GitHub REST `repos/{owner}/{repo}` 和 `commits?per_page=1`；后续触发未认证 API 限流，未能完成按 stars 全局搜索。因此下表是有针对性的候选比较，不能宣称全 GitHub 排名。提交时间取默认分支 HEAD 的 committer 日期，未使用 pushed_at 代替。

| 仓库 | Stars | 默认分支 HEAD 日期（UTC） | 许可 | 形态 |
|---|---:|---|---|---|
| [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) | 3,581 | [2026-09-21](https://github.com/SamurAIGPT/llm-wiki-agent/commit/861c6ecb0a754841da6df635e9ae32d8474275e5) | MIT | Agent 规则＋Python 工具 |
| [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | 2,372 | [2026-07-23](https://github.com/Astro-Han/karpathy-llm-wiki/commit/eafcc77001e496cc43499e4923b663aec722c813) | MIT | Agent Skill＋证据检查脚本 |
| [atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler)（原 atomicmemory 路径跳转） | 2,138 | [2026-09-27](https://github.com/atomicstrata/llm-wiki-compiler/commit/98de6027eaf72e73fb44f537d74ab77133357725) | MIT | TypeScript CLI、SDK、MCP、只读 Viewer |
| [lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki) | 1,646 | [2026-08-09](https://github.com/lucasastorian/llmwiki/commit/aac3e6493306b7fff3b09cb181ca93918e93d0e6) | Apache-2.0 | Python API/MCP＋Next.js＋浏览器扩展 |

许可按 API license 字段核对；采用时应固定版本并保留对应 LICENSE。stars 与近期提交仅说明关注度和维护活动，不证明可靠性。

## 1. SamurAIGPT：结构最直接，自动运行还需工程封装

`raw/ → wiki/sources, entities, concepts, syntheses` 与本项目分层高度匹配；有索引、日志和概览，图谱区分显式链接与模型推断关系。提供 `AGENTS.md`、`GEMINI.md`，可由现有 Agent 读取工作规则。[README](https://github.com/SamurAIGPT/llm-wiki-agent/blob/main/README.md)

不是只有提示词：有摄取、图谱、lint 等 Python 工具。`lint.py` 做断链、孤页、稀疏链接和图谱检查；不过通用写入函数直接 `Path.write_text`，不能据此认为已有原件保护、锁或事务。README 还提供删除转换源文件的可选参数，与我们的永久保留原件边界不符，封装时不能暴露此选项。[摄取源码](https://github.com/SamurAIGPT/llm-wiki-agent/blob/main/tools/ingest.py)、[lint](https://github.com/SamurAIGPT/llm-wiki-agent/blob/main/tools/lint.py)、[写入工具](https://github.com/SamurAIGPT/llm-wiki-agent/blob/main/tools/_utils.py)

**适配判断：**适合想继续让 OpenClaw/Gemini 直接处理 Markdown 的轻量起点；平台抓取和安全归档仍须我们封装。README 的“各 Agent 可用”不等于所有独立 Python 运行路径均已验证 Gemini。

## 2. Astro-Han：适合作为加工规则，不适合作为完整后台

Raw 不可变、Wiki 按主题整理；摄取前判断新增/更新/争议/无新增，冲突和过时内容显式保留。来源引用、关联更新、问答保存、lint 的规则清楚；一份材料不必强制生成新文章。模板没有强制每份来源一张卡，需要补本项目 Source 资料卡要求。[SKILL](https://github.com/Astro-Han/karpathy-llm-wiki/blob/main/SKILL.md)

代码主要是证据核对脚本和测试，抓取、编译、串行执行由 Agent 工作流完成。项目明确不承担调度、MCP、UI、向量搜索、类型化关系或撤回机制。[README](https://github.com/Astro-Han/karpathy-llm-wiki/blob/main/README.md)、[证据检查](https://github.com/Astro-Han/karpathy-llm-wiki/blob/main/scripts/check_evidence.py)

**适配判断：**可直接移植 Skill 和检查器到 OpenClaw；需要一个真实运行底座时，它留下的任务队列、幂等、恢复等工作最多。

## 3. atomicstrata：最值得验证的工程底座

编译器将源文件生成带引用的概念/实体/比较/概览等 Markdown，提供 CLI、MCP、TypeScript SDK，支持增量编译、审查候选、lint、刷新与图关系。原料 `sources/`、知识 `wiki/`、运行状态 `.llmwiki/` 分离，可保持 Obsidian 文件阅读路径。[README](https://github.com/atomicstrata/llm-wiki-compiler/blob/main/README.md)

已检查 `src/review/policy.ts`：审核规则实际返回需暂存的原因，不只是让模型自觉检查。代码树有专用 ingest、provider、review 模块。仍须通过本项目测试验证原件只增不改、重复事件和并发失败恢复；项目的 `rm` 等能力不能无约束暴露给 Wiki Agent。[review 源码](https://github.com/atomicstrata/llm-wiki-compiler/blob/main/src/review/policy.ts)、[文件摄取](https://github.com/atomicstrata/llm-wiki-compiler/blob/main/src/ingest/file.ts)

**适配判断：**OpenClaw 可调用 CLI/MCP/SDK；当前公布的 provider 有 Anthropic、Codex Agent、OpenAI-compatible 等，没有明确 Gemini 专用 provider。Gemini 接入与 embedding 配置需要独立验证，不能把 OpenAI-compatible 当作已实测兼容。功能面广于首版，需要限定为“接收我们已经归档的 Markdown、编译、审核、查询”。[providers](https://github.com/atomicstrata/llm-wiki-compiler/blob/main/docs/configuration/providers.mdx)

**建议：**若目标是复用真实工程实现，优先做这个项目的隔离样本验证，再决定以固定版本 SDK 引入还是维护小规模 fork；不必先重写编译器。

## 4. lucasastorian：确实是 Markdown 本地模式，但 UI 负担偏大

本地文件是真实数据，SQLite/cache 为可重建索引；支持 MCP、引用关系、图视图、浏览器剪藏。它并非只能云端数据库运行。与此同时需要 Python、Node、API 和 Web 服务，与已有飞书＋Obsidian 功能有重叠。[README](https://github.com/lucasastorian/llmwiki/blob/master/README.md)

源码已有引用图、过时传播、断链/孤页/引用 lint；SQLite VaultFS 具有真实写文件和删文件实现。README 的 MCP `delete` 支持来源文件，所以“初始索引不改原文件”不等于后续 Agent 绝不能删除原件。接入时必须缩小写入权限。[VaultFS](https://github.com/lucasastorian/llmwiki/blob/master/mcp/vaultfs/sqlite.py)、[lint](https://github.com/lucasastorian/llmwiki/blob/master/mcp/tools/lint.py)

**适配判断：**若用户要独立网页产品、批注和剪藏器，这是候选；现在已有飞书入口和 Obsidian，作为主 fork 底座会维护更多无关组件。Gemini 经 OpenClaw 调 MCP 在结构上可行，尚未实测。

## 建议验证路线

1. 保留已成功的 X/微信抓取器；这些 wiki 库不替代专用平台抓取。
2. 使用合成或已授权公开材料，在隔离目录验证 compiler 的来源卡、跨来源概念合并、引用、重复输入、失败恢复、待审核行为。
3. 若 Gemini 接入或编译成本不合适，选 SamurAIGPT 的轻量规则＋工具作为备选；Astro-Han 的证据检查规则可借鉴，避免多套目录约定同时生效。
4. 比较中的每项“适配判断”为基于文档与源码的推断；本轮没有成本测量，也没有宣称已实现飞书或 OpenClaw 原生连接器。
