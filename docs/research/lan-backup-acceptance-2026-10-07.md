# 局域网备份隔离验收记录

日期：2026-10-07。分支：`codex/wiki-lan-backup`，基础提交：`bac6209fec8be40830c6afcbe27f4360129827d6`。

## 验收边界

仅使用合成 Vault 与本机临时仓库，没有读取/上传正式 Vault 私人原件，没有向真实 Mac mini 写入。22/445/8765 TCP 可达；`ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes ... mac@192.168.31.136 true` 的只读无交互认证探针返回 `Permission denied (publickey,password,keyboard-interactive)`（退出 255）。没有绕过主机校验或尝试交互密码。本机未挂载 SMB 分享。目标磁盘目录和可用认证入口待用户提供。无模型调用、Feishu 消息或正式 Gateway 重启。

SSH 协议替身启动与远端相同的真实 Python 程序；它证明序列化、流传输与哈希恢复行为，**不证明真实 SSH 登录或 SMB 文件系统能力**。

## 已运行行为

CLI 往返原件/隐藏历史/空目录，重复备份和多版本，损坏拒绝与旧快照不覆盖，pending 缺失文件续传，已有恢复目录保护，路径包含/符号链接拒绝，忙写锁，SSH 协议往返，未知 payload 拒绝，部分流传输保留并续传，清单路径逃逸拒绝，传输期间创建目录导致不提交，端点所有祖先路径的符号链接拒绝，SSH 大量诊断输出与 1.26 MB 数据传输不挂起。

## 最终测试

- 新增公共 CLI 验收：15/15 通过；标准库 Python 3.9 与项目 Python 3.12 均运行通过。
- `npm test`：138/138 通过。
- 项目已有 Python 环境完整测试：80 项，77 通过、3 条件跳过。命令为 `PATH=/Users/mac/Documents/personal_OS/Personal-Wiki/.venv/bin:$PATH /Users/mac/Documents/personal_OS/Personal-Wiki/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`。
- `npm run plugin:validate`：隔离加载通过，`isolated=true, loaded=true, hook=reply_dispatch`。
- `git diff --cached --check`：通过。

系统默认 Python 缺少旧模块依赖 `bs4/httpx/playwright/imageio_ffmpeg`，第一次全套运行报导入错误；没有安装或变更系统依赖，改用项目既有虚拟环境后全套通过。

## 审查

以 `bac6209fec8be40830c6afcbe27f4360129827d6` 为固定点，对 staged diff 做 Standards 与 Spec 两轴独立审查。发现并修复端点祖先符号链接、失败建议不足、SSH 管道背压、SSH 远端路径错误套用本机包含检查，以及导出请求刚开始断管时的回执生命周期；补回归后再次复查。Spec 最终剩余阻塞 0；Standards 最终剩余阻塞 0。

审查者另做的合成探针证实：丢失 commit 回执后读回并核验成功，返回 `reconciled=true`；导出端早关闭 stdin 后给出结构化失败回执，不将二进制导出当 JSON 处理。

## 实机仍需完成

用户明确的 Mini 专用目录 → 现有连接核验 → 正式 Vault 备份 → 目标端完整 SHA-256 核验 → 本机新目录隔离恢复与逐文件比对。任务 #37 保持开放，不能标记为真实验收完成。
