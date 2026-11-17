0.10.0：新增其他 Mac 的统一安装入口与每日空闲更新。每台 Mac 使用本地 Pwiki/LLM Wiki/Vault，Mini仅复用媒体服务。下载 install-pwiki.sh 与同名.sha256，校验后按mac-install.md运行，提供Mini地址与本机私有令牌文件。

已有Homebrew时准备Node24/Python3.12/Chrome，自动建立抓取环境、安装CLI/skill和固定官方LLM Wiki。模型登录、API和库注册须在本机正常配置。当前用户launchd每日检查稳定发行，有运行/排队任务时延后，校验与中文转换预检后切换，入口失败恢复旧版。依赖/上游固定版本或major变化须人工更新，不自动升级LLM Wiki。配置、原件和旧版本保留。

摄取 CLI、Wiki 桥接器、Mini 完整转录网关和 LLM Wiki 官方应用安装引导仍可分别安装，不依赖开发 checkout。

下载所需 tar.gz 与 SHA256SUMS，核对后解压，阅读 independent-install.md 与 llm-wiki-install.md。配置样例随包/Release提供；不包含令牌、账号、私人资料、运行数据库、媒体或模型权重。包内 distribution.json 绑定源码提交和文件哈希。

已验证：macOS Apple Silicon、Node24、Python3.11/3.12；dots 文字及公开视频复用调用、隔离 CLI/桥接入库、Mini 独立依赖安装及实际音频转录、官方 LLM Wiki v0.6.11 校验安装。详细测试结果与限制见 independent-distribution-2026-11-16.md。

上游 LLM Wiki 应用由 bootstrap 从固定官方链接下载，不在本 Release 重打包。原生 whisper.cpp 服务器、模型和可选 MLX 翻译环境须按说明单独配置。当前 Air 为正式 Wiki 写入端，Mini 为媒体后端，不自动迁库。

0.9.1：独立 Wiki 桥接器的 doctor 只核对 Wiki 依赖，不因未配置 Mini 而显示 partial。0.9.0 下载包已通过外层/内部哈希、保留配置升级和同任务 Wiki 读回复核。
