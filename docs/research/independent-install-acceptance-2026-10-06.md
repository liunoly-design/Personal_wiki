# Wiki 独立安装、自检与配置回退：隔离验收

日期：2026-10-06（Asia/Shanghai）。任务 [#35](https://github.com/liunoly-design/Personal_wiki/issues/35)，规格 [#34](https://github.com/liunoly-design/Personal_wiki/issues/34)／[本地规格](../specs/independent-install.md)。

**结论：本任务限定的源码实现与本机隔离验收通过。正式Gateway未升级、模型认证/额度及新Mac验收未完成。**

## 交付
- 工作树：`/Users/mac/.codex/worktrees/wiki-independent-install/Personal-Wiki`，分支 `codex/wiki-independent-install`。
- 固定施工基线：`6c19880c206a4198993b42c8aa0ee99bda843091`；实现提交：`6f68e7df75c691dac118cfa5515f2acca157c0bc`。
- [使用手册](../independent-install.md)；入口 `node scripts/wiki-setup.mjs check|install|rollback --settings /private/settings.json`。
- 以0.7.6源码为基础新增安装工具，未冻结新产品发布版本。私有安装副本通过源码内容哈希辨识，不按版本号猜测一致。
- 所选库、私有状态、账号/用户/会话、Agent、Python、Codex和模型显式配置；不继承PGTD授权，不需要Apple。
- 复用nashsu API与知识处理，所选nashsu状态贯通文本/本地视频/远程视频。模型凭据由所选Wiki Agent读取，不复制凭据。
- 安装保存原宿主配置、暂存校验、原子替换、加载复核；失败回退、重复复用、后续编辑拒绝覆盖。回退不删除Vault/资料/状态/发布副本。
- 不自动安装依赖、下载模型、创建知识正文、登录、调用模型或重启服务；已有活动Wiki迁移另做。

## 验证与证据
| 检查 | 结果 | 证据边界 |
|---|---|---|
| Node最终全量 | 138/138通过，无跳过 | 合成业务回归；非真实模型语义 |
| Python全量 | 65项，62通过、3按既有条件跳过 | 跳过不算通过；本任务未改Python代码 |
| 安装专项 | 7/7通过 | 公共安装入口、CLI；依赖/宿主故障使用可执行替身 |
| 指定配置专项 | 6/6通过 | 所选Agent/状态与三类收集的发布守卫 |
| 既有讨论与回复 | 与配置专项合计30/30通过；最终全量包含 | 保留own-app消息身份与原回复保存 |
| 插件隔离检查 | loaded=true、reply_dispatch挂载 | 真实OpenClaw CLI，不启动Gateway |
| 真实CLI安装演练 | 安装/加载、重复existing、显式回退、无效宿主配置保持原字节均通过 | 真实OpenClaw/Python/Codex版本探测＋合成新库/账号 |
| 文档与diff | 链接/内容与diff --check通过 | 无正文生成或私人资料验收 |

真实CLI最终原始报告：
```json
{"realOpenClaw":true,"realPython":true,"isolatedCLI":true,"ownLibrary":true,"noPGTD":true,"loaded":true,"duplicateReused":true,"configurationRestored":true,"realValidationFailurePreserved":true,"originalUnchanged":true,"modelCalls":0,"feishuMessages":0,"gatewayRestarts":0}
```

最终隔离演练私有证据保留在本机 `/private/var/folders/nh/k0f6ksh108353ywdjzby7f8r0000gp/T/wiki-real-install-2MM3iB`。内容为合成资料、合成账号配置和安装凭据，不提交Git。临时目录可能由系统清理；复现脚本随源码交付。

## TDD及双轴审查
红灯→绿灯覆盖安装入口、缺依赖、校验/加载失败、显式回退、锁/后续编辑、符号链接、指定凭据/库、提交中外部编辑及错误输出脱敏。真实CLI首先暴露多Agent需显式ownership，已修正并实测。

按 [implement](../../.agents/skills/implement/SKILL.md)、[tdd](../../.agents/skills/tdd/SKILL.md)、[code-review](../../.agents/skills/code-review/SKILL.md)完成实现与两个独立审查。Standards最终0阻塞、无重大smell；Spec最终0阻塞。已修复指定库未贯通、默认账号凭据继承、配置替换前异步窗口、注入客户端的app身份丢失、渠道enabled/domain遗漏以及无效JSON错误片段泄漏；后两类有明确回归。

规格与单一端到端开发票按 [to-spec](../../.agents/skills/to-spec/SKILL.md)／[to-tickets](../../.agents/skills/to-tickets/SKILL.md)登记；用户先前确认的最高验收边界和单任务范围沿用，没有重复访谈。

## 保留边界与下一项
- 基础自检与Codex版本不能验证模型登录或额度；此次模型调用0次。
- nashsu注册信息来自合成隔离状态，新真实库API读回/读搜未实测。可选--api仅向本机读索引，不会创建知识。
- 合成飞书配置及插件加载不能替代真实账号/消息收集验收；没有发送消息。
- 其他宿主配置编辑器须在安装/回退时暂停或遵守同一把锁；同步基线检查消除已发现的await窗口，不能承诺排除不合作进程在系统调用间的竞争。
- 原注册目录及wiki-v03其他会话修改保留，正式Vault未写入，未合并当前主目录、未部署或重启正式网关。
- 本机Git提交完成，未推送远端源码；GitHub规格/任务登记不代表源码已同步。
- 资料备份与隔离恢复演练、朋友新Mac、模型认证、真实新库/飞书闭环作为后续独立任务。当前任务仅完成安装与宿主配置回退。
