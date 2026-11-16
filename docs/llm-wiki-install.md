# LLM Wiki 安装和配置

本项目接入上游 nashsu/llm_wiki，固定 v0.6.11，GPL-3.0。详见包内 upstream-nashsu.json：官方 Apple Silicon 应用压缩包及本项目记录的 SHA256；哈希用于复现，不代替上游签名。项目 bootstrap 不包含官方二进制，也不更改官方应用代码。

在 llm-wiki-setup 包中运行：

```sh
python3 llm-wiki-setup.py install --destination "$HOME/Applications"
```

也可先从 manifest 的官方 asset 链接下载，用 `--archive /absolute/LLM.Wiki_aarch64.app.tar.gz` 离线安装。安装器检查哈希、应用身份和版本，仅安装到空位置，拒绝已有 LLM Wiki.app；升级先用另一个目录验收，保留旧应用和完整 Vault 备份。正常双击启动并按 macOS 许可流程操作，不关闭系统安全检查。

## 首次使用新库

1. 在 LLM Wiki 桌面应用创建/选择一个空的独立 Vault，记录它的实际绝对路径。不要选择代码仓库作为资料库。
2. 在应用中配置能用的模型供应商、端点、模型与凭据，先完成应用自身的模型连接验证。凭据由用户在本机填写；本项目不提供或复制账号。
3. 在应用设置启用本地 API。固定版本默认地址 `http://127.0.0.1:19828`，token 保存在当前用户的应用状态中，接入器本机读取，不输出到日志。
4. 为由 CLI 管理的目标库关闭重复自动摄取 `autoIngest`。文件监视是否开启按使用方式选择；迁移旧原件另需关闭监视并清空原生队列，这不由普通安装自动执行。
5. 关闭向量/embedding检索，让接入验收使用全文搜索。应用项目注册必须指向和 CLI/bridge 配置相同的 Vault。

配置样例 `runtime/config/examples/llm-wiki-install-profile.example.json` 是上述要求的说明，**不是**可覆盖 app-state.json 的原生配置。不要用示例替换现有 app-state，否则会丢失项目与账号设置。

```sh
python3 llm-wiki-setup.py doctor --vault /absolute/Personal-Wiki-Vault
wiki-bridge doctor
```

第一条只读核对项目身份/API开关/自动摄取/向量设置，不打印令牌；第二条检查接入层的 Wiki/媒体连通；模型能否实际编译以入库任务为准。最后必须实际导入一条合成中文来源，再验证任务 complete、来源读回及全文检索，诊断就绪本身不算入库验收。

## 已有库

保留现有路径、项目 ID、原件和人工编辑，不重新初始化。先备份 Vault、应用和私有 app-state；在应用内核对设置，桥接器指向已有路径。发布冲突不会通过覆盖人工内容解决。回滚应用时也保留升级前的 app-state 与 Vault 备份，不能假定降级兼容。当前生产仍在 Air，本安装流程不会迁移 Mini 或重放旧飞书任务。
