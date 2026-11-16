# 0.9.1 独立发行验收（含0.9.0安装验证）

日期：2026-11-16。任务 [#51](https://github.com/liunoly-design/Personal_wiki/issues/51)，规格 `docs/specs/dots-independent-distribution.md`。

## 真实入口与独立包

- dots：用户从实际 dot 在 MacBook Air 发起文字与公开视频两次任务，并提供 complete 回执。本会话按同一任务复核原文完整性、Wiki 回读和全文检索。公开视频复用已有媒体、完整 ASR 和26段中文机器译文，本次没有重新下载/转写。原始回执、任务ID及状态保留于私有验收空间。
- CLI + Wiki bridge：从候选 tar.gz 解压到独立目录，无开发 checkout 依赖；CLI 文字转换、导出哈希来源包、另一个安装/独立状态目录的 bridge ingest 实际运行 Codex 与 LLM Wiki 后 complete，来源 `wiki/sources/distribution-wiki-acceptance-20261116.md`，完整合成正文和验收标识读回/检索通过。
- Mini：完整源码包安装到另一个目录；新建 Python3.11 venv，实际从固定 F2 提交与固定核心 requirements 安装成功。复用管理员已有、哈希校验的 Whisper 模型和原生 loopback whisper.cpp 服务器；不是重新编译/下载模型。MLX 翻译环境和模型是显式外部依赖。候选升级保留同一配置/令牌/任务状态，通过独立版本目录切换运行。
- 音频全链路：macOS say 合成中文音频，由独立 CLI 冻结、上传到独立 Mini 网关，经真实 FFmpeg/whisper.cpp 转写成完整时间戳 Markdown，随后 Codex/Wiki 入库 complete，来源 `wiki/sources/distribution-audio-acceptance-20261116.md`，读回及全文检索通过。机器转写未人工逐字校订。
- Mini HTTP：未授权提交401、同请求重用任务、上传哈希、原文件 Range 与转写 Markdown 哈希通过；停止并重启隔离网关后，同一任务与 Markdown 哈希不变，回执 reused=true。第二个网关竞争同一数据目录被 OS worker lock 拒绝。该重启验收验证已完成成果持久复用；不把它称为转写中途断电恢复实测。
- LLM Wiki：官方 v0.6.11 压缩包 SHA256与上游应用身份/版本检查通过，安装到隔离 Applications 目录；不替换当前正式应用。已有应用拒绝覆盖的合成测试通过；只读配置 doctor 核对正式库项目、API、自动摄取关闭及向量关闭通过。模型供应商/凭据必须在官方应用内配置，不发布或覆盖私人 app-state。未声称在全新账号下完成供应商登录。
- 英文补测：合成英文音频初次在翻译阶段失败，保留原音频/ASR；定位为初始化时解析 venv Python 的 symlink 导致丢失 MLX 环境。修复、回归后显式恢复同一任务，真实本地逐段译文5/5通过并达到 converted；原 ASR、译文和时间段齐全。本次不把 converted 称为新增 Wiki 入库。
- CLI worker：在当前用户 launchd 实际注册、观察 running 后卸载，正式 worker 未替换。

## 自动检查

候选阶段：Node170通过；Python91通过、3项环境依赖跳过；独立发行安装测试10项通过。覆盖无开发目录安装、文字转换、配置0600与重放保留、配置修改、skill实际路径/契约、卸载保留状态、上游应用哈希与拒绝覆盖、来源包跨实例入库、哈希篡改拒绝及同URL内容变化需显式refresh。

[双轴复审](independent-distribution-code-review-2026-11-16.md)阻塞问题已全部修复并复审通过。0.9.0 已由 GitHub Actions 成功构建并发布，16项自有资产下载、4包及内部文件哈希验证通过；下载包升级保留私有配置，既有 Wiki 任务仍 complete。读回时修复桥接器 doctor 不应要求 Mini 的诊断问题，0.9.1补丁通过回归，最终补丁下载校验在发布后补充。Release由 tag 的干净源码构建，source_dirty必须false；候选包带source_dirty=true，仅用于本次隔离试验，不发布为正式包。

## 交付范围与限制

已知平台为 macOS Apple Silicon、Node24、Python3.11/3.12。摄取 CLI、Wiki桥接、Mini网关、LLM Wiki bootstrap 是四个独立源码/引导包；上游官方应用、FFmpeg、原生whisper.cpp、模型、MLX运行时与平台会话按安装说明配置。安装器不打包现有二进制/模型/账号/数据库/私人原件。F2 Apache-2.0、whisper.cpp MIT、nashsu GPL-3.0保留来源与许可证。

当前正式 Wiki 仍在 Air，Mini 正式媒体服务未被候选安装替换。公开来源的既有真实验收见通用媒体/网页小红书报告；本轮新安装包的媒体实测是明确标注的合成音频，不能替代新的真实用户笔记验收。部分平台访问受限、其他语种/混合段落、超过30分钟/1GB等继续按原有待补规则；自动代码维护需另外配置实际开发工作区。
