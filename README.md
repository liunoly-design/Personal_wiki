# 个人 Wiki / Personal Wiki

本机已部署 Personal Wiki **0.4.2**，使用 nashsu 作为正式资料库。名词解释、全文中文翻译、图片和公开 X 视频下载、忠实 Markdown 整理均沿用已有采集链路。

- `raw/sources/`：原始文章；`raw/assets/`：图片、视频等原始附件。
- `wiki/sources/`：来源卡与完整中文阅读正文；`wiki/concepts/`、`wiki/entities/`：概念与实体。
- Agent 的任务和中间文件位于 Vault 外。通过 nashsu API 回读核验后清理；启动时恢复未完成任务。

0.4.1 支持公开博客、粘贴文本、多链接、独立个人背景、收集别名及显式重新收集。见[计划](docs/plans/v0.4.1.md)、[SPEC](docs/specs/v0.4.1.md) 和[验收报告](docs/research/v0.4.1-acceptance-2026-10-01.md)。历史迁移见[0.4 部署记录](docs/research/canonical-library-2026-10-01.md)。原有 `reading`、`raw/inputs`、`raw/sources/collected`、`glossary` 已迁入正式目录。

0.4.2 新增复杂 X 上下文、隔离登录恢复、逐项补附件与精确超限视频确认，保留正文部分完成及可恢复任务。见[计划](docs/plans/v0.4.2.md)、[SPEC](docs/specs/v0.4.2.md)和[验收/飞书操作步骤](docs/research/v0.4.2-acceptance-2026-10-01.md)。公开微信与本机部署核验通过；真实复杂 X、账号登录和飞书入站仍需用户验收。

可用入口和验收范围见[当前用例清单](docs/current-capabilities.md)。

共享 OpenClaw 已建立独立 `wiki` 运行 Agent，由飞书入口“小婕”调度；本项目插件已接入公开博客、X/微信、多链接及文本收集流程，查询与讨论仍为预留入口。运行架构见上级 `OpenClaw/README.md`，当前接入范围见[飞书入口说明](docs/openclaw-wiki.md)。

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

已安装收集插件到本机 OpenClaw，支持 `小婕收集：内容`、`小婕重新收集：链接`，兼容 `小婕 wk 记录：链接`；Agent 完成抓取、全文翻译、文章分析和名词解释，经受保护写入层发布，再用 nashsu API 核验。安装命令、模型费用和当前限制见 [飞书 Wiki 入口](docs/openclaw-wiki.md)。查询与讨论暂时预留。安装与本地检查通过，真实飞书端到端验收仍待用户发送测试消息，见 [安装记录](docs/research/openclaw-install-2026-09-27.md)。

2026-10-01 修复 X 作者名大小写匹配与 Flash 代理连接，微信脚本模板不再被误判为待下载视频。详见[重跑记录](docs/research/retry-2026-10-01.md)。
