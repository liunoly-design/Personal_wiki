# AI 摄取 CLI 契约

适用：SPEC #40 的 X、公众号、Mini 抖音、纯文字，以及第二批普通网页和小红书单笔记。CLI 可由 Codex、dots 或其他能执行本机命令的 AI 调用；底层不要求飞书消息 ID。实际运行须 Node 24+、配置的 Python 和目标 Wiki API；Mini 媒体接口单独配置。

## 命令

命令以实际 `--help` 为准；项目内可用 `node scripts/wiki.mjs`，安装 launcher 后为 `personal-wiki`。

| 能力 | 调用 | 结果 |
| --- | --- | --- |
| 自检 | `personal-wiki doctor` | Wiki/媒体就绪、维护配置存在性，无凭据值 |
| 后台记录 | `personal-wiki submit '分享文案或链接'` | 持久任务；默认启动后台处理，可用配置关闭 |
| 保存文字 | `personal-wiki submit --text '原始文字'` | 保留用户原话，使用独立来源身份 |
| 只转换 | `personal-wiki convert '分享文案或链接'` | 完整转换包；不入 Wiki |
| 进度 | `personal-wiki status TASK_ID` | 当前阶段、产物与剩余缺口、维护状态 |
| 待补 | `personal-wiki pending` | 尚未完成的任务，包括等待入库/认证等 |
| 执行/续作 | `personal-wiki run TASK_ID` | 按原任务复用成功阶段；不自动刷新两轮预算 |
| 显式重试 | `personal-wiki retry TASK_ID` | 新恢复代次，保留此前轮次与错误；随后 run |
| 补料 | `personal-wiki supplement TASK_ID --file /absolute/file.md` | 接收并保留补料，排队沿原任务续作 |
| 转换包入库 | `personal-wiki ingest TASK_ID` | 复用包，受保护编译/发布和读回检索 |
| 项目维护 | `personal-wiki maintain TASK_ID` | 按既有维护请求交接 Codex session；可查询确认状态 |
| 后台 worker | `personal-wiki worker --watch` | 处理排队作业，定期检查；配置启动项后可重启恢复 |

`--name` 可指定可读英文短标题；`--background` 将用户说明与原文分开。`--request-id` 绑定一次调用的稳定身份，不同载荷不得共用。`--refresh` 明确重新采集并保留新版本。`--config` 指定真实私有配置。多来源提交返回任务数组；单来源返回任务对象。

## 配置和私有状态

默认读取 `~/.config/personal-wiki/ingest.json`，或 `WIKI_CONFIG`。需要绝对 `stateDir`；记录模式另需明确 `vault`、`python` 与实际 Codex 模型配置。媒体使用 `mediaServiceUrl`、`mediaServiceTokenFile`，令牌文件必须当前用户所有且 0600。程序内部读取令牌，回执不含凭据。

状态放入独立配置的私有目录，不接管旧飞书队列。正文不足时停留在该目录的待补任务和工作材料，LLM Wiki 来源监听不能扫描它。补充、转换、编译和发布按阶段保存，进程中断后查原任务。自动恢复最多两轮；网络失败操作沿用既有有限预算，不用重启刷新额度。

维护设置使用 `maintenance.project` 指向独立、干净的项目开发 checkout，`runtimeRoot` 指向本私有状态目录内的版本化执行目录。实际 CLI 在已核验 release 运行，Codex 只改开发 checkout；独立回归通过并提交后才原子启用新 release。运行中的 checkout 与开发 checkout相同时拒绝修复，避免未测试代码影响处理任务。错误修复不改变生产 Wiki 主机。

维护保存实际 session ID、私有事件和测试结果；session 未确认接收不得报告运行中。未通过回归的开发提交不会替换当前 release；失败材料留待补。新 release 下重新导入 CLI 后按原任务重试。项目开发 session 由 Codex CLI 持久会话承载，不假定创建侧边栏新聊天。

## 状态与完成

`queued/processing/publishing` 表示执行阶段；`converted` 仅表示所请求转换已完成；`complete` 表示目标 Wiki 已核验。`pending`、`waiting_access`、`waiting_login`、`waiting_confirmation`、`waiting_capacity`、`waiting_dependency`、`waiting_publication`、`waiting_verification` 均有明确缺口。`waiting_access` 表示公开页访问受限或分享参数被拒，不能仅凭登录重定向断言必须登录。回执包含原输入、规范 URL、来源、哈希、产物与状态；属于私有数据，不上传到公开 Issue。

正文或必需转录不完整不编译；原文完整而非正文附件、译文缺失的细分恢复仍沿用保护流程。查询完整记录完成状态会核验原件与目标 Wiki，人工知识段落继续保留。进程退出成功不替代回执的完成状态。

## 来源和当前边界

- X 优先 FxEmbed v2 的公开串文和完整长文章块；保留原始 JSON、作者/父子关系、图片和提供方边界，无法判断关系则待补。备用既有 HTML/媒体获取；不采集其他评论。
- 公众号使用现有 MagicMD 和可选专用浏览器获取；完整正文和图片分别核验。正文以图片承载时做本机文字识别。
- 图片在 macOS 使用 Apple Vision，本机识别，保留原始提取 Markdown、图片、识别 JSON 和机器文字；参考 [Apple 官方说明](https://developer.apple.com/documentation/vision/recognizing-text-in-images)。动图逐帧识别并保留帧记录，阅读稿去重且标首次出现帧；超过500帧或未知格式保留待补。识别结果未经人工校订，多栏顺序和识别准确性可有误。
- 抖音复用现有 Mini 后端。当前 Mini 无通用文件/X 视频上传接口：这些输入保留原件或已有材料、准确显示待补，不能冒称已完整转录。后台服务的 health 就绪不等于某任务成功。
- 完整中文阅读先逐段判断正文语种，引用地址和图片标识不计为英文正文，中文段落逐字保留；英文段由既定模型忠实翻译；英文碎片按ID批量处理并逐片段验证，重复片段复用一次结果，已成功片段与原始位置保留。标题、列表前缀、代码与链接等保留保护，结构不符时保存受保护诊断供续作，成功单元复用。机器翻译和OCR均需以原件核对。
- 普通网页先抓取公开静态 HTML；解析失败的第二轮用无账户的临时 Chrome 渲染，保留原始响应与渲染 DOM。各跳转及浏览器子请求均由固定公网 IP 的 HTTPS 获取器执行，拒绝内网、混合 DNS、非 HTTPS 和浏览器 WebSocket。正文、标题层级、表格、代码、图片与出处保留；明确截断、付费墙、加载空壳、缺图和未转录媒体留待补。需要 Chrome 和已固定的 Playwright 版本。
- 小红书仅单篇图文/视频笔记；支持长链接及 `xhslink.com` / `xhslink.cn` 短链。分享参数保留于私有获取记录，稳定的笔记 ID 用于去重；严格校验最终笔记 ID，读取桌面详情或移动页 `noteData.data.noteData`，不取 feed/OG/预加载卡片当正文。按数组顺序保存服务端图片（不声称无损原图）并本机 OCR。新签名的同笔记链接重新提交后更新获取地址，再显式重试原任务。图文真实可用性依赖当前分享 URL；视频/实况在 Mini 通用媒体接口接入前停在 `waiting_dependency`。现场验收以各任务报告为准。
- 本机 DNS 代理只返回 `198.18.0.0/15` FakeIP 时，可用固定 HTTPS DNS 查询校验后的公网地址，再固定连接；仍拒绝私网、混合结果及内网重定向。小红书首选阿里公共 DNS 保持大陆 CDN 地区，通用网页首选 Google 公共 DNS；仅在传输失败时尝试另一固定服务，私网或混合答案直接拒绝。不会连接 FakeIP。
- Wiki 仍使用此次核实可用的本机生产实例，Mini 仅做媒体后端。Mini Wiki 接管、生产切换与备份方向调整另作实测，不因 CLI 上线自动执行。
