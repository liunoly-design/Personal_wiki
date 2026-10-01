# 个人 Wiki / Personal Wiki

独立项目；本机已部署 Personal Wiki 0.3.0-preview.4，提供名词解释、全文中文阅读、图片/公开 X 视频下载及忠实 Markdown 整理。

完整文章现发布到 `raw/sources/collected/`，可在 nashsu「原始资料」查看；`raw/inputs/` 是内部编译输入，`wiki/sources/` 是派生来源卡。见[原文可见性修复与验证](docs/research/source-publication-2026-10-01.md)。

2026-09-27 安装结果：nashsu 0.6.11＋Codex CLI 已在独立 Vault 中生成两份样本的来源卡、概念和实体。见[运行说明](docs/nashsu-local.md)及[实测报告](docs/research/nashsu-install-test-2026-09-27.md)。飞书记录插件已更新至 0.3.0-preview.4，299 份旧名词页已更新；见[本次部署与验证](docs/research/deploy-2026-09-28.md)。新版真实飞书入站验收仍待用户测试，完整规格见 [Issue #1](https://github.com/liunoly-design/Personal_wiki/issues/1)。

可用入口和验收范围见[当前用例清单](docs/current-capabilities.md)。

共享 OpenClaw 已建立独立 `wiki` 运行 Agent，由飞书入口“小婕”调度；本项目插件已接入单条 X/微信记录流程，查询与讨论仍为预留入口。运行架构见上级 `OpenClaw/README.md`，当前接入范围见[飞书入口说明](docs/openclaw-wiki.md)。

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

已安装 `小婕 wk 记录：链接` 插件到本机 OpenClaw；先用 Gemini Flash 保存名词基础解释，再交给 nashsu 分析文章关联。安装命令、模型费用和当前限制见 [飞书 Wiki 入口](docs/openclaw-wiki.md)。查询与讨论暂时预留。安装与本地检查通过，真实飞书端到端验收仍待用户发送测试消息，见 [安装记录](docs/research/openclaw-install-2026-09-27.md)。

2026-10-01 修复 X 作者名大小写匹配与 Flash 代理连接，微信脚本模板不再被误判为待下载视频。详见[重跑记录](docs/research/retry-2026-10-01.md)。
