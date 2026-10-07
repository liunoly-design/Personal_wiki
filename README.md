# 个人 Wiki / Personal Wiki

2026-10-07：新增[局域网 Vault 备份与隔离恢复](docs/lan-backup.md)。支持挂载目录或现有 SSH 的不可变快照、目标哈希核验、缺失文件续传及恢复禁止覆盖；[SPEC](docs/specs/lan-backup.md)。已真实备份到 Mac mini `/Users/mac/Backups/Personal-Wiki`，1066 文件约375 MB；目标哈希核验、隔离恢复与原 Vault 完整比对通过，重复备份复用同一快照。见[真实验收记录](docs/research/lan-backup-acceptance-2026-10-07.md)，当前为手动版本。

2026-10-06：新增[独立安装、自检与配置回退入口](docs/independent-install.md)，[隔离验收报告](docs/research/independent-install-acceptance-2026-10-06.md)。支持自己的库、私有状态、账号范围与模型Agent，不依赖PGTD/Apple。真实OpenClaw CLI隔离安装/加载/重复/回退及校验失败保护通过；这是工具源码交付，不代表正式网关升级、新Mac或真实账号验收。

2026-10-04：0.7.0 抖音实现候选已本地开发，[使用与恢复](docs/douyin-v070.md)、[验收报告](docs/research/v0.7.0-acceptance-2026-10-04.md)。指定抖音公开下载受限；真实该来源发布/查询/飞书回执未完成，未部署生产。60秒分段云ASR已做非私人合成语音长音频试验；不能替代自然语音人工参考验收。

0.6.2 同议题持续记录：明确保存默认追加同一文档，显式新记录才另建；原回复保真、稳定D/K、历史与未知结果恢复。见[使用与验收](docs/v0.6.2-usage.md)、[SPEC](docs/specs/v0.6.2-continuous-topic.md)、[实际交付证据](docs/research/v0.6.2-acceptance-2026-10-03.md)。真实飞书体验仍需用户发起验收。

2026-10-03：**0.6.1 已本机部署**，修复直接回复 Wiki 讨论的续聊，新增回复“小婕 wk 保存”原样保存指定长回复。Node97/Python42及双轴复审通过，真实消息关系只读隔离回放通过；真实用户入站与保存仍需验收。见[使用与测试手册](docs/v0.6-usage.md)与[回复修复验收](docs/research/v0.6.1-replies-2026-10-03.md)。

本机已部署 Personal Wiki **0.6.2**，使用 nashsu 作为正式资料库。名词解释、全文中文翻译、图片和公开 X 视频下载、忠实 Markdown 整理均沿用已有采集链路。

- `raw/sources/`：原始文章；`raw/assets/`：图片、视频等原始附件。
- `wiki/sources/`：来源卡与完整中文阅读正文；`wiki/concepts/`、`wiki/entities/`：概念与实体。
- Agent 的任务和中间文件位于 Vault 外。通过 nashsu API 回读核验后清理；启动时恢复未完成任务。

0.4.1 支持公开博客、粘贴文本、多链接、独立个人背景、收集别名及显式重新收集。见[计划](docs/plans/v0.4.1.md)、[SPEC](docs/specs/v0.4.1.md) 和[验收报告](docs/research/v0.4.1-acceptance-2026-10-01.md)。历史迁移见[0.4 部署记录](docs/research/canonical-library-2026-10-01.md)。原有 `reading`、`raw/inputs`、`raw/sources/collected`、`glossary` 已迁入正式目录。

0.4.2 新增复杂 X 上下文、隔离登录恢复、逐项补附件与精确超限视频确认，保留正文部分完成及可恢复任务。见[计划](docs/plans/v0.4.2.md)、[SPEC](docs/specs/v0.4.2.md)和[验收/飞书操作步骤](docs/research/v0.4.2-acceptance-2026-10-01.md)。公开微信与本机部署核验通过；真实复杂 X、账号登录和飞书入站仍需用户验收。

0.5 新增带来源行号的知识查询、正文/原文分页阅读及明确待审动作；旧提案缺少可信基线时保守拒绝应用。见[计划](docs/plans/v0.5.md)、[SPEC](docs/specs/v0.5.md)、[验收与飞书步骤](docs/research/v0.5-acceptance-2026-10-02.md)。真实飞书入站仍待用户验收。

0.5.1 修复查询回执：Codex 先筛选相关候选再根据正文回答，默认仅显示答案与实际引用来源，隐藏未读候选清单及图谱内部信息；模型失败或证据不足明确反馈。见[修复规格](docs/specs/v0.5.1-query-receipt.md)与[验收](docs/research/v0.5.1-query-receipt-2026-10-03.md)。

0.5.2 修复飞书分页阅读：隐藏YAML和逐行L前缀，保留Markdown结构、原始行号及续读命令，正确处理网页/站内/库内链接。见[规格](docs/specs/v0.5.2-reading.md)与[验收](docs/research/v0.5.2-reading-2026-10-03.md)。

可用入口和验收范围见[当前用例清单](docs/current-capabilities.md)。Wiki Agent 的过期“Vault 未接入”说明已修正，见[状态说明修复](docs/research/wiki-agent-save-status-2026-10-03.md)。

共享 OpenClaw 已建立独立 `wiki` 运行 Agent，由飞书入口“小婕”调度；本项目插件已接入公开博客、X/微信、多链接及文本收集流程，查询和待审处理已接入，讨论已接入0.6。运行架构见上级 `OpenClaw/README.md`，当前接入范围见[飞书入口说明](docs/openclaw-wiki.md)。

- [需求文档](需求文档.md)：范围、已确认需求与验收目标。
- [架构与数据](架构与数据.md)：归档、知识层、Schema 与目录草案。
- [工作流与Review](工作流与Review.md)：摄取、整理和周期回顾。
- [待确认问题](待确认问题.md)：后续讨论入口。
- [功能与版本规划](docs/implementation-roadmap.md)：当前实现、建议交付版本、nashsu API 复用及讨论清单。
- [参考项目](参考项目.md)：历史资料包中的相关参考。

总体讨论位于上级 Personal OS 项目；共享约定见 [跨项目协议](../跨项目协议.md)。代码与设计文档在本仓库，实际 Obsidian Vault 为 `/Users/mac/Documents/Personal-Wiki-Vault`，已通过本机内容包导入测试。

## 开发准备

- GitHub 仓库：[Personal_wiki](https://github.com/liunoly-design/Personal_wiki)。
- 开发约定见 [AGENTS.md](AGENTS.md)。Matt Pocock 的 38 个 skills 已项目级安装在 `.agents/skills/`，安装来源记录在 `skills-lock.json`。
- 安装命令：`npx skills@latest add mattpocock/skills --agent codex --skill '*' --yes`。
- 已完成 `setup-matt-pocock-skills` 的项目配置：GitHub Issues、默认五个标签、单一上下文文档布局；配置见 `docs/agents/`。这里记录标签映射，尚未在远端创建标签。
- 后续按 `grill-with-docs → to-spec → to-tickets → implement` 推进功能。术语和设计决定在讨论中逐步写入 `CONTEXT.md` 和 `docs/adr/`。
- 本仓库不存放私人 Vault 和运行凭据。上级项目链接依赖 Personal OS 目录布局，独立克隆时需另行取得相关文档。

## 飞书 Wiki 插件

已安装收集插件到本机 OpenClaw，支持 `小婕收集：内容`、`小婕重新收集：链接`，兼容 `小婕 wk 记录：链接`；Agent 完成抓取、全文翻译、文章分析和名词解释，经受保护写入层发布，再用 nashsu API 核验。安装命令、模型费用和当前限制见 [飞书 Wiki 入口](docs/openclaw-wiki.md)。查询及待审处理见0.5，讨论与综合见0.6。安装与本地检查通过，真实飞书端到端验收仍待用户发送测试消息，见 [安装记录](docs/research/openclaw-install-2026-09-27.md)。

2026-10-01 修复 X 作者名大小写匹配与 Flash 代理连接，微信脚本模板不再被误判为待下载视频。详见[重跑记录](docs/research/retry-2026-10-01.md)。
