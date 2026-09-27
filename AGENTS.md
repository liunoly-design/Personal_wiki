# 个人 Wiki 工作约定

先读 README.md、需求文档.md、待确认问题.md；跨项目变更参考 ../跨项目协议.md。

本项目负责原始资料归档、来源卡、主题、概念、综合文章及知识 Review。原始资料不可被 AI 覆盖；派生知识保留来源引用。索引可重建，不替代 Markdown 和附件。

与 GTD 通过稳定 ID 和行动候选关联，不直接完成或删除 Apple 任务。用户已授权本机 nashsu 安装与指定 X、微信样本测试；私人账户及外部消息仍按具体授权处理。具体目录及 Schema 的草案需与已确认需求区分。

## 开发流程

- Matt Pocock skills 安装于 `.agents/skills/`，版本来源由 `skills-lock.json` 记录。使用某个 skill 前先读对应 `SKILL.md`；用户指令和本项目的数据边界优先。
- 首次工程配置使用 `setup-matt-pocock-skills`，确定任务跟踪位置、标签及领域文档约定。配置完成前，不把推荐选项当成已确认决定。
- 功能从 `grill-with-docs` 开始，结合已有需求明确范围、验收条件和失败行为；已确认内容无需重复询问。
- 跨多次会话的开发使用 `to-spec` 固化规格，再用 `to-tickets` 拆为可独立验证的端到端任务，记录依赖。
- 使用 `implement` 实现明确的任务，按 `tdd` 的红灯、绿灯、重构循环验证行为，提交前按 `code-review` 检查规格符合度和代码质量。
- 优先测试原件保护、重复投递、失败恢复及来源可追溯等外部行为；单纯文档变更检查内容和链接即可。
- 大范围且关键路径不清楚的工作可用 `wayfinder`；运行行为才能回答的问题可先用 `prototype` 验证。

## 仓库与数据边界

- 本仓库保存设计、代码、测试和开发 skills；实际 Obsidian Vault 使用 `/Users/mac/Documents/Personal-Wiki-Vault`。继续本机集成时先读 `docs/nashsu-local.md` 及其指向的实测报告，区分已验证链路和剩余规格。
- 凭据、私人原始资料、真实附件、会话记录及运行状态不得随代码提交。测试优先使用合成样本。
- 原件保护、幂等和并发写入由实现及测试保证，不能只依赖模型提示词。
- 本次已授权初始化 Git 并同步到 `https://github.com/liunoly-design/Personal_wiki.git`；这不改变部署、私人账户和外部消息的授权边界。
- `../` 指向 Personal OS 的相邻项目，独立克隆时可能不存在。跨项目工作若缺少协议，应取得对应文档，不能猜测契约或修改其他项目。
- 更新需求和架构文档时，明确区分已确认需求、实施建议与待决事项。

## Agent skills

### Issue tracker

规格与开发任务使用 `liunoly-design/Personal_wiki` 的 GitHub Issues。见 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个默认标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

采用单一上下文：根目录 `CONTEXT.md` 与 `docs/adr/`，按实际讨论结果逐步创建。见 `docs/agents/domain.md`。
