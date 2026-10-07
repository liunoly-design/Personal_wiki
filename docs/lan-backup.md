# 手动备份到 Mac mini

本版本备份完整 Vault 的文件字节、隐藏知识记录和空目录，提供哈希核验与隔离恢复。入口为 `scripts/wiki-backup.py`，本机与 SSH 远端均只需 Python 3.9+ 标准库；支持 macOS，Linux 需有 `renameat2`。

## 选择目标

使用 Mini 上一个**专用备份目录**，目录必须已存在，路径每一层都需为真实目录，不得经过符号链接（例如 macOS 应使用 `/private/tmp` 而非 `/tmp`）。用户已确认目录为 `/Users/mac/Backups/Personal-Wiki`，当前机器使用下面的独立密钥及远端 Python。SSH 需要事先完成用户管理的密钥登录和主机身份验证；脚本会拒绝密码交互或未知主机密钥。不要把密码、私钥或登录资料写入命令和本仓库。

```sh
python3 scripts/wiki-backup.py backup \
  --vault /Users/mac/Documents/Personal-Wiki-Vault \
  --ssh mac@192.168.31.136 \
  --identity /Users/mac/.ssh/id_ed25519_wiki_backup \
  --remote-python /opt/homebrew/opt/python@3.14/bin/python3.14 \
  --repository /Users/mac/Backups/Personal-Wiki
```

挂载 SMB 后可省略 `--ssh`，将 `--repository` 替换成本机已挂载共享盘中的专用目录。源和目标不可包含彼此。SMB 必须在实际共享盘验收原子重命名、fsync 和文件锁；不支持时应使用 SSH 到 Mini 本地磁盘。

SSH 请求只传路径与备份资料到用户目标机器，不调用模型、不发送 Feishu、不重启 Gateway。源存在受保护写锁且忙时立即失败；可以在 Wiki 空闲时重试。nashsu 或 Obsidian 修改也会被全树变化检查拦截，长时间备份时应暂停编辑，减少重试。

指定独立 SSH 密钥可加 `--identity /Users/mac/.ssh/id_ed25519_wiki_backup`（只把路径交给 SSH，不读取或记录私钥内容）。远端非交互 PATH 不一定包含 Homebrew，可加 `--remote-python /opt/homebrew/opt/python@3.14/bin/python3.14` 指定用户提供的解释器。备份、列表、核验与恢复均使用相同连接参数。

## 校验与恢复

从成功 JSON 回执取 `snapshot`，将下面的 `SNAPSHOT_ID` 替换为该值：

```sh
python3 scripts/wiki-backup.py list --ssh mac@192.168.31.136 --identity /Users/mac/.ssh/id_ed25519_wiki_backup --remote-python /opt/homebrew/opt/python@3.14/bin/python3.14 --repository /Users/mac/Backups/Personal-Wiki
python3 scripts/wiki-backup.py verify --ssh mac@192.168.31.136 --identity /Users/mac/.ssh/id_ed25519_wiki_backup --remote-python /opt/homebrew/opt/python@3.14/bin/python3.14 --repository /Users/mac/Backups/Personal-Wiki --snapshot SNAPSHOT_ID
python3 scripts/wiki-backup.py restore --ssh mac@192.168.31.136 --identity /Users/mac/.ssh/id_ed25519_wiki_backup --remote-python /opt/homebrew/opt/python@3.14/bin/python3.14 --repository /Users/mac/Backups/Personal-Wiki --snapshot SNAPSHOT_ID --destination /Users/mac/Documents/Wiki-Restore-Check
```

恢复目录必须不存在，其父目录必须存在。不能填写当前 Vault，也不能恢复到本机备份仓库内部。恢复结果逐文件校验后才以新目录出现；不启用 nashsu、不重放任务。接管到生产 Vault 属于后续人工确认的恢复步骤。

仓库结构为 `pending/<ID>/{manifest.json,data/}` 与 `snapshots/<ID>/{manifest.json,data/}`；清单 ID 是规范 JSON 的 SHA-256。成功回执只包含 ID、范围、文件数和字节数，不打印私有正文或文件名。`list` 读取清单身份；只有 `verify` 逐文件读取数据。

## 失败与续传

- 断开连接、退出或磁盘满：原 Vault 与已提交快照保留，重跑同一备份命令会核验并续传缺失文件。
- 源发生修改：不会提交混合快照。待数据稳定后重跑；新内容会得到新 ID，旧 pending 保留。
- 数据或清单损坏：不会覆盖修复旧成果。先确认目标磁盘与已有快照；使用未损坏副本恢复。若需处置 pending，先人工核对，不自动删除。
- 提交回执未知：命令会尝试读回已提交快照核验；连接仍失败时，恢复连接后先 `list` 和 `verify` 再决定重试。
- 忙锁：等待现有写入/备份结束后重试，不删除锁文件、不强制解锁。
- 中断恢复：目标目录不发布；父目录中的 `.wiki-restore-*` 暂存目录保留供核对，重试应使用新目标目录。上传中断的 `.upload-*` 文件可能保留在仓库根目录，不能当作完成快照；本版本不自动清理。

v1 **不包含**运行账户/浏览器/宿主凭据，不保存 POSIX 元数据、扩展属性及 Finder 标签；文件恢复为 0600、目录为 0700。Mini 上远程视频不因本机备份而获得第二份媒体副本。不同版本为完整数据副本，没有跨版本空间去重或自动删除。每三天自动执行和失败飞书告警由独立[定时入口](periodic-backup.md)提供。

本机隔离与真实 Mini 验收见 [报告](research/lan-backup-acceptance-2026-10-07.md)。真实验收须同时有目标端核验和隔离恢复比对；连接配置完成不能替代这些证据。
