# 在其他 Mac 安装 Pwiki

适用：macOS Apple Silicon（M 系列）。每台 Mac 使用自己的 Pwiki、LLM Wiki、Vault 和模型账号；局域网 Mini 仅共用媒体下载与转录。无需克隆仓库或安装 OpenClaw/GTD。

## 首次准备

1. 安装 [Homebrew](https://brew.sh)。如 macOS 提示安装 Xcode 命令行工具，完成后再运行安装脚本。
2. 从 Mini 管理员取得该服务的局域网地址和令牌文件。将令牌安全保存到**新 Mac**，例如 `~/.config/personal-wiki/mini-token`，执行 `chmod 600 ~/.config/personal-wiki/mini-token`。不要把令牌粘到命令、聊天或 GitHub。
3. 在下面命令中替换 `MINI_LAN_IP`。8765 是服务示例端口，以 Mini 的实际配置为准。新 Mac 和 Mini 须相互可达。

从 [GitHub Releases](https://github.com/liunoly-design/Personal_wiki/releases/latest) 下载 `install-pwiki.sh` 与同名 `.sha256`。在下载目录执行：

```sh
shasum -a 256 -c install-pwiki.sh.sha256
bash install-pwiki.sh \
  --media-url http://MINI_LAN_IP:8765 \
  --media-token-file "$HOME/.config/personal-wiki/mini-token"
```

安装脚本自动通过已有 Homebrew 准备 Node24、Python3.12 与 Chrome；建立独立 Python 环境，安装抓取依赖/Playwright，缺少 Codex CLI 时在本安装的 tools 目录安装；安装 Pwiki CLI 和薄 skill，并从固定官方地址下载、校验和安装 LLM Wiki v0.6.11。不在客户端重复安装 FFmpeg/Whisper服务或转录模型，Mini 服务无需重装。

默认 CLI 位置 `~/.local/share/pwiki/bin/personal-wiki`，配置 `~/.config/personal-wiki/cli.json`，Vault 位置 `~/Documents/Personal-Wiki-Vault`。可通过 `--prefix`、`--config`、`--vault` 显式设置；同一用户的多个安装须用不同 config 和 Vault。安装路径和配置输出在最终 JSON 回执中，保留它。

已存在的 LLM Wiki 应用、skill、配置、账号和库均保留。重复运行保留已有配置与 Python 环境；修改 Mini 地址等配置应使用发行包 `manage.mjs configure`，不要将另一台电脑的配置覆盖过来。Homebrew 本身须先安装，系统许可与账号不会自动代填。

## 完成一次本机配置

1. 打开 `~/Applications/LLM Wiki.app`（已有系统安装则打开原应用），创建或打开本机 Vault，与安装回执中的路径一致。已有库保留原件、项目 ID 和历史，不重新初始化。
2. 配置模型供应商/账号，并在应用内验证连接。当前 CLI 的知识加工还需要本机 Codex 登录；运行安装回执/配置所指向的 Codex 的登录入口，保留你自己的账号，不复制别人的凭据。
3. 启用本地 API，关闭该库的自动摄取 `autoIngest`，关闭 embedding/向量搜索，防止重复加工。见 [LLM Wiki 配置](llm-wiki-install.md)。
4. 将 CLI 的 bin 目录加入终端 PATH，或直接使用绝对路径：

```sh
"$HOME/.local/share/pwiki/bin/personal-wiki" doctor
"$HOME/.local/share/pwiki/bin/personal-wiki" convert --text '这是一条安装自检资料。'
```

doctor 仅说明分项配置/连通性，converted 仅说明转换。正式使用前通过一条合成资料验证入库 complete、读回和检索。平台登录受限时按任务回执补充，不会复制旧电脑的浏览器 Cookie。

默认不启动摄取 worker。配置及验收后，可用 CLI 发行包的 `manage.mjs worker-install` 启用；dots/AI 也可显式 submit/run。安装时 `--worker` 是已配置环境的可选入口。

## 每日自动更新

统一安装默认注册**当前用户**的 launchd 检查，须保持用户登录、Mac 唤醒且可访问 GitHub；不依赖 Codex 聊天或另建聊天自动化。每小时唤醒，距上次成功检查24小时后查询一次稳定 Pwiki 发行；发现新版本但忙碌时每小时等待空闲。

- 排队、处理中、发布中任务，或正在运行的 CLI 命令，都会让切换延后。启用代码自动维护的实例交由人工协调，不让两个版本管理器同时切换运行版本。
- 只自动更新 Pwiki。同 major、抓取依赖和 LLM Wiki 固定清单不变时才自动激活；依赖、上游应用固定版本或 major 改变，记录 `manual_update_required` 并保留旧版，需要重新核验环境。
- 下载校验外层 SHA256、发行身份与内部文件哈希，通过隔离中文纯文字转换后才激活。校验或预检失败不切换；激活后入口失败恢复旧链接。中断事务在下一次更新检查前恢复。旧版本、配置、任务、Vault 和原件保留。
- 不自动升级 LLM Wiki，不运行模型验收，不覆盖已有全局 skill。原 skill 指向稳定 CLI 路径；其内容更新发生冲突时需要比较后处理。

可立即检查：

```sh
"$HOME/.local/share/pwiki/bin/pwiki-update"
```

状态文件为 `<prefix>/state/update-status.json`，检查输出为 `update.log`，系统错误为 `update-error.log`。`deferred` 表示等待空闲；`up_to_date` 表示无新版；`updated` 表示已完成本次切换。日志和任务属于本机私人状态，不上传 GitHub。

停止/恢复每日检查：

```sh
"$HOME/.local/share/pwiki/capture-venv/bin/python" \
  "$HOME/.local/share/pwiki/state/runtime/current/distribution/pwiki-setup.py" \
  schedule --prefix "$HOME/.local/share/pwiki" --remove

"$HOME/.local/share/pwiki/capture-venv/bin/python" \
  "$HOME/.local/share/pwiki/state/runtime/current/distribution/pwiki-setup.py" \
  schedule --prefix "$HOME/.local/share/pwiki"
```

高级选项 `--skip-dependencies` 只用于已经准备好的 Python/Node/Codex/Chrome 环境；`--no-schedule` 不注册定时更新。`--release-dir` 接受用户明确指定的离线发行目录（release.json、所需 tar.gz 与同名校验文件），不从该目录中的 URL 下载。

## 边界

SHA256 用于下载与文件完整性检查，同一发行源的校验文件不等于独立签名。新 Mac 的实际账号、网络、平台抓取、模型入库仍需该机验收。本次安装不会修改 Mini、其他 Mac 或原电脑的生产服务。
