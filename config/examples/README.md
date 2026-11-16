# 独立发行配置样例

状态：独立发行0.9.1已发布，见[安装说明](../../docs/independent-install.md)。字段中的占位路径、IP、模型哈希需要在目标机初始化，不能原样运行。当前正式配置不被这些文件改动。

- `ingest.example.json` 使用当前 CLI 已有字段。Python、Codex、Vault 和私有状态位置由目标机决定；`runtimeRoot` 必须等于 `stateDir/runtime`。`192.0.2.10` 是文档示例地址，须替换成真实 Mini 地址；令牌只引用本机私有0600文件。`autoStart:false` 让初次检查时不自行启动任务；正式 worker 安装应在环境核验后进行。
- `mini-media.example.json` 基于既有服务的配置样例，包含占位指纹。使用Mini安装包的gateway init核验模型、填写工具位置并生成配置，不直接套用占位指纹。默认 loopback 只用于同机检查；Air访问Mini须绑定经过确认的LAN地址，令牌和网络限制应同时生效。`translation.enabled:false` 表示尚未配置本地翻译，不能据此声称英文完整中文交付。
- `llm-wiki-install-profile.example.json` 是安装需求描述，**不是 LLM Wiki 原生 app-state.json**，也不是已经实现的安装器输入接口。官方应用版本和下载哈希来自根目录 `upstream-nashsu.json`；该哈希是项目记录的下载件校验值，不是上游签名。目标机的项目注册、API鉴权和模型登录需要单独初始化，不能把另一电脑的app-state整份覆盖过去。

由已发布安装入口填入目标机真实值并进行doctor，而不是把开发电脑路径写进发行包。与现有库连接时保留稳定项目身份、原件和人工内容；新库初始化与既有库接入分开验收。
