# 局域网备份实施任务

- 父规格：[#36](https://github.com/liunoly-design/Personal_wiki/issues/36)、[本地 SPEC](../specs/lan-backup.md)。
- 单一端到端任务：[#37](https://github.com/liunoly-design/Personal_wiki/issues/37)，手动备份、核验、隔离恢复；无代码任务依赖。
- 公共验收：CLI；先合成隔离测试，再在用户明确的 Mini 目录实测。
- 实机依赖：目标磁盘目录、现有连接方式；备份频率另待用户选择。
- 验收任务保持开放，不能用端口检查、SSH 协议替身或本机往返替代 Mini 成功及恢复比对。
