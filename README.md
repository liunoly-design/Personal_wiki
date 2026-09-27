# 个人 Wiki / Personal Wiki

独立项目，当前处于需求与设计阶段。

2026-09-27：共享 OpenClaw 已建立独立 `wiki` 运行 Agent，由飞书入口“小婕”调度；当前仅支持对明确提供的资料生成整理草稿，实际 Vault 和归档工具尚未接入。运行架构见上级 `OpenClaw/README.md`。

- [需求文档](需求文档.md)：范围、已确认需求与验收目标。
- [架构与数据](架构与数据.md)：归档、知识层、Schema 与目录草案。
- [工作流与Review](工作流与Review.md)：摄取、整理和周期回顾。
- [待确认问题](待确认问题.md)：后续讨论入口。
- [参考项目](参考项目.md)：历史资料包中的相关参考。

总体讨论位于上级 Personal OS 项目；共享约定见 [跨项目协议](../跨项目协议.md)。本目录用于设计与后续实现，实际 Obsidian Vault 路径尚未确定。

## 开发准备

- GitHub 仓库：[Personal_wiki](https://github.com/liunoly-design/Personal_wiki)。
- 开发约定见 [AGENTS.md](AGENTS.md)。Matt Pocock 的 38 个 skills 已项目级安装在 `.agents/skills/`，安装来源记录在 `skills-lock.json`。
- 安装命令：`npx skills@latest add mattpocock/skills --agent codex --skill '*' --yes`。
- 已完成 `setup-matt-pocock-skills` 的项目配置：GitHub Issues、默认五个标签、单一上下文文档布局；配置见 `docs/agents/`。这里记录标签映射，尚未在远端创建标签。
- 后续按 `grill-with-docs → to-spec → to-tickets → implement` 推进功能。术语和设计决定在讨论中逐步写入 `CONTEXT.md` 和 `docs/adr/`。
- 本仓库不存放私人 Vault 和运行凭据。上级项目链接依赖 Personal OS 目录布局，独立克隆时需另行取得相关文档。
