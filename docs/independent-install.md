# 独立安装和 dots 调用

2026-11-17：其他 Mac 推荐使用[统一安装与每日空闲更新](mac-install.md)。下文保留组件级安装方式；统一入口在0.10.0新增。

面向 macOS Apple Silicon。Node 24+，Python 3.11+（摄取本身最低3.9），本机 Codex CLI。四个包分别安装，不需要开发 checkout。每个包有 `distribution.json` 记录来源提交和文件哈希；GitHub Release 提供 SHA256SUMS。下载完整发行文件后执行 `shasum -a 256 -c SHA256SUMS`；仅下载一个包时下载它同名的 `.sha256` 并对该文件执行 `shasum -a 256 -c 文件名.sha256`，再解压。下列 `/absolute/...` 均替换为本机真实路径。

## CLI

在 CLI 解压目录执行：

```sh
node install.mjs --prefix "$HOME/.local/share/personal-wiki-cli" --python /absolute/python3 --vault /absolute/Personal-Wiki-Vault --codex /absolute/codex
node manage.mjs --prefix "$HOME/.local/share/personal-wiki-cli" configure --media-url http://MINI_LAN_IP:8765 --media-token-file /absolute/private/mini-token
node manage.mjs --prefix "$HOME/.local/share/personal-wiki-cli" skill-install
```

把安装回执的 bin 目录加到 PATH；也可始终用回执中的绝对命令。令牌文件由 Mini 管理员安全传递，0600，勿放入聊天或仓库。初次配置保存在 `~/.config/personal-wiki/cli.json`；安装重放保留原配置，后续配置使用 `manage.mjs configure`。配置字段见包内 `runtime/config/examples/README.md`。

URL 获取依赖单独隔离安装：`/absolute/python3 -m venv /absolute/capture-venv`，然后 `/absolute/capture-venv/bin/python -m pip install -r runtime/requirements-capture.txt` 与 `/absolute/capture-venv/bin/python -m playwright install chromium`；把 configure 的 `--python` 指向此 Python。部分来源需要已授权浏览器会话、Apple Vision OCR 或平台许可，受限时进入待补。截图 OCR 需 macOS Swift/系统权限。仅 `convert --text` 无需网络、模型或 Wiki。

```sh
personal-wiki doctor
personal-wiki convert --text '这是一条完整的中文合成资料。'
personal-wiki submit 'https://example.org/article' --request-id stable-request-id
personal-wiki status TASK_ID
personal-wiki run TASK_ID
node manage.mjs --prefix "$HOME/.local/share/personal-wiki-cli" worker-install
```

worker 为 macOS 当前用户 launchd，须用户登录；运行时要保持 LLM Wiki 和所需 Codex/模型可用。默认安装不自动启用 worker。`worker-uninstall` 停止 worker；`uninstall` 只移除本安装器的入口和 worker，保留任务、原件、配置和版本。升级先用新包 `install.mjs` 安装同一 prefix/config，验证后切换 current；若需回滚，停 worker、保留当前链接目标，再把 current 原子切回以前的已验证 release。升级不会改写 Vault。

## Wiki 接入包

在 wiki-bridge 包中同样运行 `node install.mjs --prefix "$HOME/.local/share/personal-wiki-wiki-bridge" --vault /absolute/Personal-Wiki-Vault --python /absolute/python3 --codex /absolute/codex`。配置默认为 `~/.config/personal-wiki/wiki-bridge.json`。先按 [LLM Wiki 安装配置](llm-wiki-install.md) 注册同一个 Vault，再运行回执命令 `wiki-bridge doctor`。

```sh
personal-wiki export CONVERTED_TASK_ID --output /absolute/new-source-package
wiki-bridge ingest --bundle /absolute/new-source-package/bundle.json --name english-source-name --request-id stable-import-id
wiki-bridge status TASK_ID
wiki-bridge run TASK_ID
```

来源包带完整正文和附件哈希；当前上限250MiB/2048文件。桥接器冻结输入、保护原件，使用既有 Wiki 发布/回读/全文检索协议，只有 complete 才算入库。来源包由调用者提供，哈希不证明平台来源真实性；报告不得声称本次重新获取或转写。同 URL 内容变化要显式 `--refresh`，保留旧原件；人工编辑冲突保留待处理。讨论和知识关联仍由 LLM Wiki 完成。

## Mini 转录包

在 Mini 包目录执行（Python 3.11+，Git/Xcode命令行工具，FFmpeg/FFprobe，CMake）：

```sh
python3 install.py --prefix "$HOME/.local/share/personal-wiki-mini" --python /absolute/python3
python3 runtime/distribution/native-whisper.py --destination /absolute/new-whisper-source
```

安装器建立独立 venv，安装固定核心版本和固定提交 F2（Apache-2.0），输出日志但不输出令牌。`--skip-dependencies --python /absolute/existing-venv/bin/python` 仅用于明确复用已有运行环境，会检查基础依赖。模型权重不随包分发；自行从官方 whisper.cpp 模型来源取得模型并核对可信 SHA256，传入对应文件与哈希。首次初始化：

```sh
/absolute/prefix/bin/personal-wiki-media init --model-file /absolute/ggml-medium.bin --model-sha256 VERIFIED_SHA256 --ffmpeg /absolute/ffmpeg --ffprobe /absolute/ffprobe
/absolute/whisper-source/build/bin/whisper-server --host 127.0.0.1 --port 8767 -m /absolute/prefix/data/models/ggml-medium.bin
/absolute/prefix/bin/personal-wiki-media serve
```

默认仅 loopback；局域网使用 init 的 `--bind MINI_LAN_IP --base-url http://MINI_LAN_IP:8765`，不要暴露公网。ASR 必须保持 loopback。配置、随机令牌位于 prefix/data/state；数据目录独占单 worker。令牌权限0600，health不能替代实际转录验收。原生 whisper-server 作为独立进程持续运行；可使用自己已有且模型一致的服务器。其启动和模型身份须管理员核对。

英语转中文还需 Apple Silicon MLX 环境与本地 Qwen 模型，见后续配置节；未配置时英文保留 ASR 并待补，不能冒报中文全文。中文语音可直接交付。其他语种/混合段落按原有完整性检查处理，可能待补。媒体限30分钟/1GB；超限没有自动放行入口。

`python3 install.py --prefix /absolute/prefix --action worker-install` 可将网关注册当前用户 launchd（原生 ASR 另行管理）。worker-uninstall/uninstall 保留数据、模型和配置；升级使用相同 prefix，依赖在同一 venv，建议停服务、备份后安装并复核。既有生产 Mini 不被安装器寻找或替换。

## dots

安装 skill 后，在 dots 连接**安装了 CLI 的电脑**，让其读取该电脑 `~/.codex/skills/personal-wiki/SKILL.md`，运行 doctor，然后发“用个人 Wiki 记录：完整链接或分享文案”。本轮 Air 是正式 Wiki 写入端，Mini 是媒体后端。保留稳定 request-id 和任务 ID，跟踪同一任务直至 complete；queued/converted 不是入库成功。云端聊天附件须先落到执行电脑的真实文件路径，再 `submit --file /absolute/file.mp4`。skill-install 保留已有 skill，已有安装需人工比较后更新，不静默覆盖。

若安装未就绪，先查 CLI doctor、Mini鉴权/ASR、Wiki应用和模型配置；平台访问失败按任务回执待补。两轮失败后的自动代码维护需要另外配置实际 Codex 开发工作区/维护桥接，不随纯运行包默认启用。

## Mini 英语译文配置

单独创建 MLX venv，安装 `runtime/services/mini-media/requirements-translation.txt`；从上述 Qwen 模型的固定 revision `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b` 下载完整模型目录（Apache-2.0），核对可信模型哈希。首次 init 加 `--translation-model-dir /absolute/model --translation-sha256 VERIFIED_SAFETENSORS_SHA256 --translation-python /absolute/mlx-venv/bin/python`。安装器绑定本地模型文件清单；启动检查模型哈希，英文逐段译文保留模型/原 ASR/时间段证据。未提供这些选项不会尝试联网补模型。若已有配置与 init 参数不同，工具保留原配置并报错，先备份再明确编辑或另用新 data 目录。
