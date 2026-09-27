# 首版网页与媒体抓取方案调研

日期：2026-09-27。状态：实施建议，尚未选型或实测；不代表所有站点已可稳定抓取。本次仅查官方文档、项目源码和本机工具元信息，没有读取登录数据、运行资料抓取或修改运行配置。

## 结论

后续更新：[三个链接实测](capture-test-2026-09-27.md)已完成。微信 MagicMD HTTP 路径与 X 公开 HTML 路径成功；抖音 F2/yt-dlp 失败，登录浏览器被导航策略拦截。本文其余内容保留为测试前的方案比较。

补充：用户要求优先评估现有库。X 候选与源码缺口见 [X 库调研](x-libraries.md)，微信与抖音候选见 [微信及抖音库调研](wechat-douyin-libraries.md)。下文“平台脚本”优先指对现成项目的薄封装，是否另写提取逻辑由验证结果决定。

建议以**平台脚本为主、现有 OpenClaw 管理的本机浏览器补充登录与动态页面、Codex 处理少量异常**。浏览器控制与平台内容提取是两层：换浏览器不会自动获得完整正文、图片或可下载的视频。

成本判断是工程推断：固定脚本不需要为每次抓取调用模型，执行路径也容易测试；浏览器增加启动与页面等待成本；模型逐步操作浏览器增加推理消耗和执行时间。没有同批样本的成功率、耗时与用量记录前，不能断言哪个方案最便宜、最稳定，也不报具体金额。资料卡生成的模型用量另计。

## 平台差异

| 平台 | 建议实现 | 已核实的限制与待验证点 |
| --- | --- | --- |
| X | 专用脚本保存正文、图片、Markdown；视频交给 yt-dlp 候选实现；需要时使用登录浏览器 | yt-dlp 有 Twitter/X 提取器，但媒体处理过滤普通照片，不能替代图文归档。单帖、长正文、混合媒体分别验收。用户已确认同作者串文和引用帖，适配器需单独验证边界，不采集其他评论。[源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/twitter.py) |
| 微信公众号文章 | 专用脚本提取文章正文与图片；HTTP 获取失败或正文依赖页面行为时尝试本机浏览器 | yt-dlp 支持清单没有 WeChat/Weixin 文章提取器；其通用媒体提取不能等同完整文章支持。正文容器、延迟加载图片与异常页面识别需要样本验证。[支持清单](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) |
| 抖音视频 | 专用链接解析与元信息脚本，评估 yt-dlp 下载；登录浏览器作为补充 | 当前 DouyinIE 匹配 `/video/<id>`，源码明确有需要新鲜 cookies 的失败分支。短链接解析与本机成功率需验证。[源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py) |
| 抖音图文 | 单独实现图文适配器，保留文案、图片顺序与原始响应 | 上述 DouyinIE 的 URL 匹配不覆盖 `/note/`，不能因清单出现 Douyin 就承诺图文支持；需要通过实际页面或响应验证。[源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py) |
| YouTube | yt-dlp 下载单个视频和标题、简介；最高 1080p，首版不转录 | 有专用提取器；官方文档说明部分格式或功能可能需要外部 PO Token，完整支持还涉及 JS runtime/EJS。登录会话不是解决所有失败的手段。[提取器说明](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube)、[EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS) |
| OpenAI、Anthropic 等公开博客 | 通用文章脚本为基础，必要时按域名单独修正；保存 HTML、正文 Markdown、图片 | 可评估 Mozilla Readability 提取正文，再转换 Markdown；这是实现建议，尚未验证这些博客的表格、代码、脚注和嵌入内容。yt-dlp 不承担博客全文归档。[Readability](https://github.com/mozilla/readability) |

yt-dlp 官方明确提醒：列入支持清单不保证当前可用，网站变化会使提取失效。应固定经过验证的版本，并用样本回归决定升级。[官方说明](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 浏览器与 Codex 的分工

| 候选 | 文档支持的能力 | 本项目判断 |
| --- | --- | --- |
| OpenClaw managed browser / 原始 CDP | 独立浏览器数据目录；支持页面操作、响应读取和下载拦截。existing-session 可操作用户已有 Chrome 会话，但响应读取、下载拦截等能力仍需 managed/raw CDP。[浏览器文档](https://docs.openclaw.ai/tools/browser)、[CLI 限制](https://docs.openclaw.ai/cli/browser) | 优先验证专用持久 profile，由用户在该窗口登录。是否复用日常浏览器或按域导入会话再决定；不能假定日常 Chrome 登录已自动继承。 |
| Vercel Labs agent-browser | CLI 控制浏览器，支持持久 profile 和会话保存，也支持复用 Chrome profile。[官方首页](https://agent-browser.dev/)、[会话文档](https://agent-browser.dev/sessions) | 适合作为独立脚本驱动候选；并不自带各平台归档逻辑。先比较现有 OpenClaw 能否满足需求，再决定是否增加依赖。 |
| Clawbrowser | 本次核实的 `clawbrowser/clawbrowser` 提供 Chromium runtime、独立 profile、CDP 与远程查看；官方明确不保证通过所有验证码或访问所有网站，安装流程需要其 API key。[项目](https://github.com/clawbrowser/clawbrowser) | 仅列候选。还有 [OpenKrab/ClawBrowser](https://github.com/openkrab/ClawBrowser) 和 [eveiljuice/clawbrowser](https://github.com/eveiljuice/clawbrowser) 等同名项目，不能混为 OpenClaw 自带浏览器。用户尚未指定仓库，不以某一实现为既定选型。 |
| Codex CLI | 官方支持用 `codex exec` 集成脚本流程，输出 JSONL 或按 schema 输出结果，并设置运行权限。[OpenAI 官方文档](https://developers.openai.com/codex/noninteractive/) | 可用于异常分类、修复提取脚本或受限的浏览器兜底；仍需已接好的浏览器工具。建议限制调用次数、运行时间和权限，不能把模型返回的“成功”当作附件完整性证明。 |

## 本机观察

主任务于本日只读检查发现：已安装 Google Chrome、Safari、Obsidian、UURemote；PATH 中有 `openclaw`、`codex`，未找到 `yt-dlp`、`ffmpeg`。未找到命令不等于其他目录一定未安装。

`openclaw browser --help` 报告版本 2026.9.6，列出 managed Chrome/Chromium、`cookie-sync`、`import-profile`、`download`、`responsebody`、`evaluate`、`doctor` 等能力；尚未启动浏览器验证。上级 `OpenClaw/install-local.mjs` 中 Wiki Agent 工具目前只有 `read`、`session_status`，因此“本机有工具”不等于“Wiki Agent 已能调用”，需要后续实现运行接入。本文不修改上级项目。

## 建议的执行与恢复方式

1. 飞书收到资料后创建稳定任务 ID；按 URL 路由平台脚本，并保存输入。
2. 能直接获取的页面走脚本；需要动态内容或登录时调用专用浏览器 profile。视频下载与正文提取分别记录结果。
3. 内容快照与 Markdown 分开保存，图片和视频写入附件；校验文件完整性后再标记对应部分成功。原始响应只保存内容证据，不收集 cookie、认证头或整个浏览器状态。
4. 会话失效、验证挑战、解析失败、网络失败分别记录；认证问题暂停该平台的相关任务，合并通知，提示用户远程处理。
5. 用户修复会话后重试同一任务，补充新快照或缺失附件，保留原件和既有成功结果。视频失败时回执明确“部分完成”，不能整体报成功。

这些是建议的状态和实现方式。未来飞书故障通知符合用户提出的产品需求；本次调研不实际发送外部消息或访问私人会话。浏览器 profile、cookies、运行状态和真实附件均置于仓库之外。

## 开发前最小验证

- 每种平台/类型至少一个正常样本；补充 X 混合媒体、抖音图文顺序、YouTube 视频、博客代码/表格样本。
- 在同一批样本记录：完整抓取率、耗时、人工介入次数、模型用量与附件大小；区分未登录、已登录和登录失效。
- 验证下载中断、附件缺失、重复投递和恢复；证明原件不会覆盖、不会重复通知、不会在漏图漏视频时误报完整。
- 验证用户能远程看到正确浏览器窗口、完成登录，并让原任务继续。UURemote 已安装不等于该流程已验证。
- 先在临时目录和合成样本中验证归档契约；涉及真实会话的测试待具体实施边界确定后开展。

已确认视频最高 1080p、只下载单个视频并保留标题简介，首版不转录；X 包括同作者串文和引用帖。仍待用户决定：资料卡内容、Vault 与大附件位置；仍待技术验证：各平台浏览器选择、会话稳定性和媒体下载成功率。
