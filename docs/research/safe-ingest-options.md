# nashsu 安全编译集成核查

核查日期：2026-09-27。仅静态读取公开源码；未读私人 Vault、凭据或运行配置，也未触发扫描。

## 结论

建议固定 nashsu v0.6.11 的纯提示词与 FILE 解析逻辑，使用 Codex CLI 生成隔离候选，由本项目程序执行 create-only 新页提交；已有页面的候选更新全部进入待审。原件不得放进运行中桌面实例监听的 `raw/sources/`。这属于复用上游编译逻辑的适配，不应称为调用完整官方编译 API。

## 事实和来源

核查仓库：`/Users/mac/Documents/personal_OS/Personal-Wiki/.local/research/nashsu`；tag `v0.6.11`；commit `e8082119649e6a8e1cf85eaf289adcabfdf39d4e`。

- `src-tauri/src/api_server.rs:828` 的 `resolve_project` 接受已注册项目的 ID、路径或 current。`handle_rescan:2523` 可扫描非当前的已注册项目。
- 扫描由 `src-tauri/src/commands/file_sync.rs:330` 入队、处理文件变化并发事件；它不是独立 LLM 编译服务。
- `src/lib/project-file-sync.ts:49` 的事件监听忽略非当前项目；`:110` 的前端手动扫描也检查当前项目。`:260` 的 `enqueueRawSourceChanges` 才调用前端 ingest 队列。因此扫描隔离项目不保证编译，切换当前项目又会影响现有桌面状态。
- HTTP 路由表 `src-tauri/src/api_server.rs:341` 无独立候选生成/ingest 接口。`package.json` 无 headless ingest 命令。没有核实到可直接使用的官方无界面编译入口。

## 可提取依赖

- `buildAnalysisPrompt`：`src/lib/ingest.ts:2165`，依赖 `languageRule`。
- `buildGenerationPrompt`：同文件 `:2227`，依赖 `languageRule`、`currentWikiDate`（`:1822`，纯日期函数）、`GENERATION_WIKI_TYPES`（`src/lib/wiki-page-types.ts` 常量）。
- `parseFileBlocks`：同文件 `:460`，依赖 `OPENER_LINE`、`CLOSER_LINE`、`FENCE_LINE`、`isSafeIngestPath`、`isWindowsSafePathSegment` 和两个类型声明；这一组不需要桌面运行环境。保留 warnings 和 truncatedPaths，不能把截断当成成功。
- `languageRule` 转发到 `src/lib/output-language.ts` 的 `buildLanguageDirective`。原函数依赖 Zustand 的 `useWikiStore`、语言检测和语言名字映射。适配时将语言作为显式参数，使用已确认中文；保留其正文中文、专名标识符保留原文的规则。
- 不建议直接导入整个 `ingest.ts`：顶部依赖 Tauri 文件命令、多个状态 store、模型客户端、图像提取、缓存和写入模块。`autoIngest` 同时处理源文件、模型请求和实际文件修改，不提供返回候选而不提交的公开选项。`runCommit` 只是提交操作调度回调，仍包着实际写入，不是 dry-run 接口。

## 实现边界与验证

1. 建立带上游 commit 和许可证的固定 vendor 模块；以明确函数边界提取，避免运行时按行号切片。保留上游相关解析测试用例，增加中文提示词断言。
2. 两次 CLI 调用分别执行分析和生成，输出只写候选目录。模型进程不拥有真实 Vault 写权限，不能只用提示词约束。
3. 解析之后另做输出路径白名单、symlink 检查、原子 create-only 和并发保护。上游 `isSafeIngestPath` 是词法路径检查，不能替代这些文件系统保护。
4. 已存在页全部进入待审，直到能验证人工区块合并。来源引用与必需资料卡缺失、无文件块、截断和失败均应成为显式结果。
5. 不往桌面监听目录投递原件；API 搜索/读取可继续整合，但不以 rescan 作为保护边界。

## 许可注意

上游 `LICENSE` 为 GNU GPL v3，包含 Yong Su 版权声明。复制源码或派生模块须保留版权、许可及上游出处，发布时遵守其条款；不能将复制模块标成自有宽松许可。完整法律兼容性不是本次静态技术核查结论。

以上为实施建议及源码事实，不代表已完成运行验收。
