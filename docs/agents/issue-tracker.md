# Issue tracker: GitHub

用户于 2026-09-27 确认：本项目的规格和开发任务放在 [GitHub Issues](https://github.com/liunoly-design/Personal_wiki/issues)。仓库为 `liunoly-design/Personal_wiki`。

## 操作约定

- 优先使用已授权的 GitHub 连接器；有可用且已登录的 `gh` CLI 时，也可使用 CLI。当前初始化环境没有 `gh`，Git HTTPS 推送也没有可用凭据，不能将连接器授权视为本地 Git 登录已完成。
- skill 要求“发布到 issue tracker”时，创建该仓库的 GitHub Issue；“读取任务”时读取该 Issue 的正文、标签和评论。
- 创建、评论、标签、指派及关闭操作使用对应 GitHub 工具；执行写入前核对仓库及 Issue 编号。
- 使用 CLI 时显式指定 `--repo liunoly-design/Personal_wiki`；多行正文先写入文件，再用 `--body-file` 传入，避免 shell 解释正文。
- 规格写清用户行为、验收条件、边界和待决事项。任务按端到端功能拆分，依赖明确后再实施。
- 普通项目讨论、初始化和代码同步不自动触发 Issue 或评论发布；用户明确要求发布或调用相应发布 skill 时再执行。

## Pull requests as a triage surface

**PRs as a request surface: no.**

## 依赖与大型规划

- `wayfinder` 的主规划 Issue 使用 `wayfinder:map`；子决策使用 `wayfinder:research`、`wayfinder:prototype`、`wayfinder:grilling` 或 `wayfinder:task`。
- 支持时用 GitHub sub-issues 关联父子任务；否则主 Issue 维护任务列表，子 Issue 标注 `Part of #<编号>`。
- 支持时用 GitHub 原生 issue dependencies 表达阻塞关系；工具不支持时在正文顶部写 `Blocked by: #<编号>`，逐一核查阻塞任务已关闭后再开工。
- 完成实际验收后才关闭任务。不要把 Wiki 开发 Issue 的状态与用户在 Apple 提醒事项中的个人任务状态混为一谈。
