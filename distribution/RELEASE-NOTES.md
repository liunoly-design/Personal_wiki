摄取 CLI、Wiki 桥接器、Mini 完整转录网关和 LLM Wiki 官方应用安装引导现可分别安装，不依赖开发 checkout。

下载所需 tar.gz 与 SHA256SUMS，核对后解压，阅读 independent-install.md 与 llm-wiki-install.md。配置样例随包/Release提供；不包含令牌、账号、私人资料、运行数据库、媒体或模型权重。包内 distribution.json 绑定源码提交和文件哈希。

已验证：macOS Apple Silicon、Node24、Python3.11/3.12；dots 文字及公开视频复用调用、隔离 CLI/桥接入库、Mini 独立依赖安装及实际音频转录、官方 LLM Wiki v0.6.11 校验安装。详细测试结果与限制见 independent-distribution-2026-11-16.md。

上游 LLM Wiki 应用由 bootstrap 从固定官方链接下载，不在本 Release 重打包。原生 whisper.cpp 服务器、模型和可选 MLX 翻译环境须按说明单独配置。当前 Air 为正式 Wiki 写入端，Mini 为媒体后端，不自动迁库。

0.9.1：独立 Wiki 桥接器的 doctor 只核对 Wiki 依赖，不因未配置 Mini 而显示 partial。0.9.0 下载包已通过外层/内部哈希、保留配置升级和同任务 Wiki 读回复核。
