# 局域网备份实施任务

- 父规格：[#36](https://github.com/liunoly-design/Personal_wiki/issues/36)、[本地 SPEC](../specs/lan-backup.md)。
- 单一端到端任务：[#37](https://github.com/liunoly-design/Personal_wiki/issues/37)，手动备份、核验、隔离恢复；无代码任务依赖。
- 公共验收：CLI；先合成隔离测试，再在用户明确的 Mini 目录实测。
- 实机连接已确认：`mac@192.168.31.136`，目标 `/Users/mac/Backups/Personal-Wiki`；独立公钥已授权。当前为手动运行。
- 2026-10-07 已完成 Mini 实际备份、目标完整哈希校验、隔离恢复与原 Vault 比对，以及真实重复备份复用同一快照；详见[验收记录](../research/lan-backup-acceptance-2026-10-07.md)。
