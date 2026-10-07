# 局域网备份：隔离与真实 Mac mini 验收

日期：2026-10-07。分支：`codex/wiki-lan-backup`，基础提交：`bac6209fec8be40830c6afcbe27f4360129827d6`。

## 最初隔离阶段（历史记录）

最初仅使用合成 Vault 与本机临时仓库，没有读取/上传正式 Vault 私人原件，没有向真实 Mac mini 写入。22/445/8765 TCP 可达；`ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes ... mac@192.168.31.136 true` 的只读无交互认证探针返回 `Permission denied (publickey,password,keyboard-interactive)`（退出 255）。没有绕过主机校验或尝试交互密码。当时目标目录和公钥授权尚未完成，实机任务保持开放。后续按用户提供的信息完成下方真实验收。

SSH 协议替身启动与远端相同的真实 Python 程序；它证明序列化、流传输与哈希恢复行为，**不证明真实 SSH 登录或 SMB 文件系统能力**。

## 已运行行为

CLI 往返原件/隐藏历史/空目录，重复备份和多版本，损坏拒绝与旧快照不覆盖，pending 缺失文件续传，已有恢复目录保护，路径包含/符号链接拒绝，忙写锁，SSH 协议往返，未知 payload 拒绝，部分流传输保留并续传，清单路径逃逸拒绝，传输期间创建目录导致不提交，端点所有祖先路径的符号链接拒绝，SSH 大量诊断输出与 1.26 MB 数据传输不挂起。

## 最终测试

- 新增公共 CLI 验收：16/16 通过；标准库 Python 3.9 与项目 Python 3.12 均运行通过。新增指定独立密钥和带空格远端 Python 路径的往返回归。
- `npm test`：138/138 通过。
- 项目已有 Python 环境完整测试：81 项，78 通过、3 条件跳过。命令为 `PATH=/Users/mac/Documents/personal_OS/Personal-Wiki/.venv/bin:$PATH /Users/mac/Documents/personal_OS/Personal-Wiki/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`。
- `npm run plugin:validate`：隔离加载通过，`isolated=true, loaded=true, hook=reply_dispatch`。
- `git diff --cached --check`：通过。

系统默认 Python 缺少旧模块依赖 `bs4/httpx/playwright/imageio_ffmpeg`，第一次全套运行报导入错误；没有安装或变更系统依赖，改用项目既有虚拟环境后全套通过。

## 审查

以 `bac6209fec8be40830c6afcbe27f4360129827d6` 为固定点，对 staged diff 做 Standards 与 Spec 两轴独立审查。发现并修复端点祖先符号链接、失败建议不足、SSH 管道背压、SSH 远端路径错误套用本机包含检查，以及导出请求刚开始断管时的回执生命周期；补回归后再次复查。Spec 最终剩余阻塞 0；Standards 最终剩余阻塞 0。

审查者另做的合成探针证实：丢失 commit 回执后读回并核验成功，返回 `reconciled=true`；导出端早关闭 stdin 后给出结构化失败回执，不将二进制导出当 JSON 处理。

本轮连接参数变更相对 `bba0d3e` 再次进行了独立 Standards/Spec 两轴复查，均无实现阻塞。

## 真实 Mac mini 验收完成

用户明确授权目标目录及专用来源公钥，主机指纹经本机既有可信记录比对一致。连接使用 `BatchMode=yes`、`StrictHostKeyChecking=yes` 和显式专用密钥，不复用 GitHub 密钥。

- 目标：`mac@192.168.31.136:/Users/mac/Backups/Personal-Wiki`。
- 主机 ED25519 指纹：`SHA256:H8iiYqGs1M5u6Y1g05HmmvKTQGFhRzyx2P54Ni52+i8`。
- 远端 Python：`/opt/homebrew/opt/python@3.14/bin/python3.14`，实际返回 `3.14.3`。
- 目标初始目录存在、可写、为空；实测可用空间 `1,587,125,805,056` 字节。
- 源：`/Users/mac/Documents/Personal-Wiki-Vault`。
- 快照 ID：`e149feafb8198206690e8a1ab44f165fbdb1722c58f7918f91279c4baa7d3f0b`。
- 文件数：1066；目录数：101（不含根）；文件字节数：374,799,201（约375 MB）。

| 实际步骤 | 读回结果 |
| --- | --- |
| 正式 Vault 备份到 Mini | `status=committed`，1066 文件、374799201 字节 |
| Mini 完整逐文件 SHA-256 校验 | `status=verified`，相同 ID/文件数/字节数 |
| 从 Mini 下载并隔离恢复 | `status=restored`，相同 ID/文件数/字节数 |
| 独立扫描原 Vault 与恢复目录 | `sourceStable=true`、`restoreStable=true`、`byteAndDirectoryMatch=true`、`snapshotMatch=true` |
| 再次运行同一真实备份 | `status=existing`，复用相同 ID，没有新快照 |

隔离恢复目录保留于来源 Mac 的 `/Users/mac/.codex/worktrees/wiki-independent-install/Personal-Wiki/.local/wiki-restore-2026-10-07-e149feaf`。原 Vault 完整内容与目录结构匹配恢复清单，原件未覆盖。`.local/` 经 `git check-ignore` 确认忽略；真实资料与私钥不进入代码提交。

实际备份包括 Vault 隐藏知识数据和历史，排除受保护写锁文件；不备份宿主/浏览器运行账户或 Mini 上原有远程视频。没有调用模型、发送 Feishu、重启 Gateway、启用恢复任务、配置定时或删除旧备份。

端到端验收链路已全部完成，任务 #37 可按完成关闭；当前版本为手动备份。
