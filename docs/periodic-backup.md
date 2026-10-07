# 每三天备份，失败飞书告警

用户确认：每三天备份一次，失败通知飞书，成功静默。规格及任务见 [SPEC](specs/periodic-backup.md) / [#38](https://github.com/liunoly-design/Personal_wiki/issues/38)。现有不可变备份协议、隔离恢复和范围见[备份说明](lan-backup.md)。

## 执行方式

通过当前聊天的 Codex 原生定时任务执行，上海时间每三天22:00，首次2026-10-10。来源 Mac 与 Codex 桌面应用必须运行，局域网 Mini 和飞书可达。关机或应用退出期间不能备份或当场告警；恢复运行后到期检查最多执行一次，不连续补跑旧周期。不会添加系统 cron/LaunchAgent，不修改 Gateway。

定时执行使用 `/Users/mac/.openclaw/personal-wiki/backups/runtime/<提交SHA>/` 固定代码副本，逐文件哈希核对后启用；不会依赖后续修改中的开发工作树。

专用配置及状态在代码仓库外：`/Users/mac/.openclaw/personal-wiki/backups/periodic-settings.json`、`/Users/mac/.openclaw/personal-wiki/backups/periodic/`。配置只存账号/允许的用户与私聊标识、路径和起始时间；飞书凭据沿用宿主已配置的指定 Wiki 账号，绝不复制到仓库。源、Mini、密钥及 Python 沿用已验收参数。

```bash
python3 scripts/wiki-backup-run.py status --settings /Users/mac/.openclaw/personal-wiki/backups/periodic-settings.json
python3 scripts/wiki-backup-run.py run --settings /Users/mac/.openclaw/personal-wiki/backups/periodic-settings.json
```

执行入口先判断 `nextDueAt`，未到期返回 `not_due`。到期 backup 后再次 verify，校验成功才记录 `lastSuccess`；成功或失败都进入下一个三天周期。`--force --run-id <新的唯一ID>` 用于明确手动验收/重试，不加入定时提示词。

## 失败和恢复

源、已提交快照及 pending 保留；失败通知只含安全归类原因、时间、最后成功时间和检查建议，不包含原件、凭据或子进程原始错误。先保存发送意图和稳定 UUID，再发送到当前唯一获准 Wiki 私聊。发送响应后读回消息，核对 ID、聊天、应用发送者和完整内容，`alert: verified` 才表示已确认送达。

- `unknown`：没有可靠发送 ID，可能已发送；保留意图，不自动重发。先在飞书及状态中核对。
- `readback_pending`：已有消息 ID，但读回未通过；使用同一 `--run-id` 只重试读回。
- 备份进程中断且没有完成回执：同一 runId 不重做备份，先用[手动 CLI](lan-backup.md)只读核实远端，再明确重试。
- 飞书也不可达时，备份任务返回失败并保留状态，由 Codex 失败通知渠道提醒；不会把未确认告警标记为送达。
- 并发调用拒绝第二个执行者；配置作用域变更、安全路径拒绝等前置失败由 Codex 失败渠道提示，不冒险用已变更账号发送。

通知测试使用 `run --test-alert --run-id <唯一ID>`，内容明确标注“告警测试”，不改变备份或下一到期时间；重复同一 ID 不重发。

## 验收记录

合成公开 CLI 验证成功静默、完整校验、损坏失败/原件保留、未知发送不重放、已知消息只读回、未到期不写、并发锁和符号链接拒绝。2026-10-07 真实验收：

- 22:19（上海）备份入口成功，Mini 快照 `e149feafb8198206690e8a1ab44f165fbdb1722c58f7918f91279c4baa7d3f0b`，1066文件、374,799,201字节，目标再次完整校验通过。成功路径未发飞书。
- 真实私聊“告警测试”发送及 API 读回核对均通过（`alert: verified`）；相同 runId 重复执行未重发。测试前后 lastSuccess 和 nextDue 一致。
- 原生 heartbeat `wiki` 已启用、绑定当前聊天、每三天22:00、仅失败显示通知；工具及保存配置读回确认 ACTIVE。执行状态 `nextDueAt=2026-10-10T14:00:00Z`，即首次10月10日22:00（上海）。这验证配置和手动同入口执行，未来定时触发尚未发生。
- 合成验收新增旧中断恢复跳过过期周期、旧run不能倒退新成功时间、宿主路径祖先切换仍读取原目录。真实配置、账号标识、回执和消息 ID 均留在专用私有状态目录，不随代码提交。

交付校验：Node 140/140；项目 Python 环境 92 项（89通过、3项条件跳过）；新增定时 CLI 11/11；隔离插件检查通过。Standards 与 Spec 两轴已复核，剩余阻断均为0。系统 Python 初次全量检查因缺少第三方依赖失败，改用已有项目虚拟环境后通过；备份入口自身只需标准库。
