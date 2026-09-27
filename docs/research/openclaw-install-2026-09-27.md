# OpenClaw Wiki 安装与验收记录

日期：2026-09-27。代码基准 `4ce9a5c`，开始时 Git 工作区干净。

## 当前结论

已安装并启用 personal-wiki 0.2.0，真实 Gateway 的配置热加载成功，飞书连接正常。**尚未完成真实飞书端到端验收**：已请用户发送四条指定纯文本消息，目前尚无 Wiki 入站任务。下面区分本轮执行、本地模拟和此前已有证据，不以函数调用冒充入站事件。

## 安装与保留范围

- OpenClaw / 飞书插件 2026.9.6；Wiki 插件 0.2.0；原 GTD 插件 0.1.0。Wiki 与 GTD 均显示 loaded，注册 reply_dispatch hook 和各自 service。
- LLM Wiki.app 0.6.11 正在运行，本机 API 健康，当前 Vault 为 `/Users/mac/Documents/Personal-Wiki-Vault`，编译队列为空。
- 执行用户指定的 `node scripts/install-openclaw.mjs --check`，通过后执行正式安装命令。Python 依赖安装到项目 `.venv`，链接现有项目，没有重装 OpenClaw 或新建 Agent。
- 配置比较确认 agents、bindings、channels、tools、auth、models、原 GTD 插件配置及允许插件策略未变。Wiki 沿用同一授权用户与私聊，不记录真实 ID 到本报告。
- Flash 使用现有 wiki Agent 的 Google 凭据，已通过 SDK 解析验证，仅输出是否可用，没有复制或输出密钥。本轮没有新文章付费调用。
- 未创建系统定时任务；插件自身运行时的任务队列轮询为既有实现。没有修改其他项目数据、扩大浏览器权限、采集抖音或转录视频。

## 安装问题与处理

1. 安装器原逻辑会在宿主未设置 plugins.allow 时，新建仅包含 Wiki 的名单。修复为仅在已有显式名单时追加 Wiki，否则保留原策略；配置备份文件权限设为 0600。
2. 安装前 Gateway 报告 active tasks=0、queued system events=0。安装器完成依赖、链接和配置验证，但其重启客户端持续等待，期间其他 CLI 报告 state-lifecycle 被占用；退出卡住的重启客户端，使用原 launchd plist 重新加载服务后恢复监听，没有删除锁文件或重置数据库。
3. 后续热加载明确报告“Plugin source changed while preparing its reload”。停止在插件目录内写检查输出，诊断输出改到 `~/.openclaw/personal-wiki/installation/`，保持源码稳定后重新启用。20:40:25 的 Gateway 日志确认热加载成功，随后 runtime inspect 与飞书 probe 均通过。源变更与重启等待的全部内部因果尚未确定，不宣称已修复 OpenClaw 宿主实现。

## 验证结果

| 项目 | 状态及证据 |
| --- | --- |
| Node 测试 | 8/8，通过；包括记录流程顺序、查询/讨论不执行、失败回执、重复消息不重复处理、已有基础页字节保护 |
| Python 测试 | 9/9，通过，使用安装后的 `.venv/bin/python` |
| 隔离插件加载 | 通过，reply_dispatch 注册成功 |
| 实际网关与飞书 | Wiki/GTD 均 loaded；Feishu running=true、probe.ok=true |
| 原有 GTD 路由 | 配置未变；两个真实插件在离线宿主边界分别接管各自指令，无真实 GTD 写入 |
| 授权公众号与 X 重复 URL | 本地归档适配入口均返回 existing；Flash 替身设为调用即失败，实际调用数为 0；不是飞书端到端测试 |
| 原件完整性 | 30 个原始文件哈希通过；安装前后 91 个 Raw、基础页和 Wiki 文件均未变、未缺失 |
| 基础解释与顺序 | 34 页均标记 verified:false 和未经独立核实；保存时间早于对应文章来源卡。顺序测试在编译入口直接验证基础页已落盘 |
| 引用 | 检查到 7 处 Markdown 本地路径引用，其中 4 处基础页引用，均有效；不把此计数当作所有 wikilink 的全面验证 |
| 真实新文章全流程 | 本轮未重跑；此前公众号的 34 基础页及 nashsu 编译证据保留，未删除归档绕过去重 |
| 失败最终回执 | 本地故障测试通过，失败仅发一次结果回执且重复消息不重跑；真实故障注入未执行 |
| 真实飞书接收至最终回执 | **待用户发送测试消息** |

## 用户侧真实测试

在现有授权的小婕私聊逐条发送纯文本，每条等回执后再发下一条：

1. `小婕 wk 记录：https://mp.weixin.qq.com/s/5h-3nOxtudYfIMmDUZc5XQ`
2. `小婕 wk 记录：https://x.com/lemomo_ai/status/2103823847632060854?s=20`
3. `小婕 wk 查询：医疗服务定价`
4. `小婕 wk 讨论：知识归档`

前两条应先确认收到，再返回“已存在归档”；后两条应返回“暂未开放”。收到后须核对真实消息与任务关联、最终回执 ID、Flash 用量文件未增长、原件与基础页未改变。不得用直接调用 accept 或伪造入站消息替代此项。

## 备份、修改和回滚

原配置备份：`/Users/mac/.openclaw/openclaw.json.before-personal-wiki-2026-09-27T12-31-04.556Z`，权限 0600，含秘密，不提交。

修改文件：安装脚本、两个 Node 测试文件、README、入口说明和本报告。宿主仅新增 Wiki 插件安装/配置；项目新增忽略的 `.venv`、私有检查结果；Wiki 任务状态目录为 `~/.openclaw/personal-wiki/`。

回滚先核对没有正在处理的 Wiki 任务，再局部设 `plugins.entries.personal-wiki.enabled=false`，按正常管理流程热加载或重启。保留任务记录、Vault 和原件，不用整份旧配置覆盖后来变化，也不改 GTD。若需要撤销链接，仅移除 personal-wiki 对应安装项/路径；不要删除其他插件路径。

## 尚存限制

当前只开放记录；查询、讨论不调用模型。公开 X/微信抓取不覆盖全部页面结构或登录态，X 串文/远端引用展开仍有限制。真实失败回执、平台重复投递与中断恢复尚未故障注入；回执未知结果的自动重试仍依赖现有 uuid 处理，不能声称任意故障下恰好一次。新文章模型调用和 nashsu 编译沿用原配置；本轮重复链接验证不代表新增文章的所有场景已经复测。
