# 三来源实现前的运行环境核查

日期：2026-11-16。范围：只读系统、现有本机 API、Mini 已部署源码与认证健康检查；没有安装、改配置、提交处理任务、转录、发布或写入真实 Vault。本文不保存地址、账户、凭据值、真实来源链接或会话记录。

## 当前可用能力

| 对象 | 本次证据 | 实施含义 |
| --- | --- | --- |
| 本机 LLM Wiki | 认证前健康接口返回 200、running、版本 0.6.11；目标库唯一注册，API 启用且令牌存在 | 可以接入明确目标库，不需要先迁移生产主机 |
| 本机受保护发布准备 | `assertPublisherReady` 通过；配置为 autoIngest=false；原生监听 enabled=true | 当前满足受保护集成禁止重复自动编译的检查；监听开关不能与自动摄取混为一谈 |
| 本机读取/检索 | 通过现有 API 读取索引成功；无私人语义的探测搜索成功；向量功能关闭 | 可从现有程序完成发布后读回与关键词检索核验 |
| Mini 媒体网关 | 认证 health 返回 200、api_version=1、ready；runtime 返回版本 0.7.7 | 可复用现有后端，不等于本轮已转录或完成真实来源验收 |
| Mini 实际加载版本 | runtime 的 release_id 为 `0.7.7-2355e9f8365d`，加载版本化 API 与 pipeline | 当前服务端已具有部分本机旧客户端尚未封装的接口，必须依据实际源码核对 |
| Mini SSH | 默认身份尝试被拒绝；显式既有 Wiki 备份身份后 BatchMode 只读连接成功 | 自动化可以显式选择已有 SSH 身份，不能把默认身份失败当成 Mini 不可访问 |
| Mini Wiki 应用 | 两个标准应用位置及 app-state 均不存在；已迁入代码、采集虚拟环境存在 | Mini 当前可做媒体后端，尚不能据此认定 Wiki 正式写入已接管；本轮按主线程决定保留当前本机 Wiki 生产端 |

本机 Node 为 24.21.0，Codex CLI 为 0.169.0-alpha.11.1。Mini 的 Node 位于 Homebrew 标准安装路径，非交互 SSH 默认 PATH 未包含它，调用时应显式使用程序路径。

## 可复用配置与依赖

现有宿主 Wiki 插件的私有配置已包含目标 Vault、旧任务目录、Python、Codex 程序、编译模型、媒体服务地址和令牌文件位置。新 CLI 应只提取所需设置或使用独立配置，不整份复制宿主配置，不接管旧飞书状态或重放消息。

令牌只在现有配置和受保护令牌文件中由程序读取；本轮未打印令牌值。媒体令牌文件与已配置 LAN origin 搭配使用，不能擅自替换成回环地址。

| 本机采集依赖 | 本次读取的已安装版本 |
| --- | --- |
| MagicMD | 0.7.15 |
| httpx | 0.28.1 |
| beautifulsoup4 | 4.15.0 |
| markdownify | 1.2.3 |
| imageio-ffmpeg | 0.6.0 |
| yt-dlp | 2026.8.19 |
| readability-lxml | 0.8.4.1 |
| Playwright | 1.60.0 |

依赖来自既有本机项目虚拟环境，迁移工作区本身没有同名环境。实施时直接配置既有 Python 或建立明确的新环境，不根据当前工作区路径猜测环境存在。

本机 DNS 的 X 和对应视频域名本次得到公网地址；公众号与抖音短链本次命中基准测试网段假地址。这是查询时的状态，不代表永久故障或当前实际抓取已经失败。平台获取器需要使用已配置的安全代理/浏览器路径或经校验的公网解析方式；不能放宽非公网地址保护来绕过假地址问题。Mini 的安全网络实现已有固定公网 DoH 解析后连接已核验公网 IP 的实现，可作为调查参考。

## Mini 真实接口与恢复边界

以下来自实际加载 release 的 API 源码，不能仅依据历史 README 推断。

| 能力 | 实际接口与限制 |
| --- | --- |
| 提交 | 认证 POST `/v1/jobs`；必须有 Idempotency-Key；仅接受公开 HTTPS 抖音 URL，options 只接受 language=zh、max_height=1080；额外请求字段被拒绝 |
| 读状态和成果 | 认证 GET 原作业、manifest、Markdown；媒体读取与播放接口仍在；本轮只调用 health/runtime，未读取私人作业内容 |
| 原任务恢复 | 认证 POST `/v1/jobs/{jid}/resume`，保留原 job ID 与幂等关系；对 failed、partial_failed、waiting_login、waiting_confirmation 允许显式恢复；重新解析并绑定来源、检查详情后才改回 queued |
| 旧成功产物重核验 | 原任务为 succeeded 且指定 `reverify=true` 时，只有旧产物无法通过当前证据核验才进入兼容恢复；正常成功任务不能随意重排 |
| 超限批准 | 没有独立的批准请求字段或批准 API；pipeline 仍检查 30 分钟和 1 GB。resume 不是越过阈值的授权 |
| 文件/其他平台 | 没有上传文件、本地文件转录或 X 视频提交入口；URL 校验仅允许抖音。不能把 X 视频路径或伪造抖音 URL 送入当前公开 API |

当前本机媒体客户端尚未封装 resume；对恢复的支持应新增封装与行为测试，而不是重建作业或换幂等键。服务端重新解析来源失败会返回明确失败，客户端应保留原 jobId 并显示原因。

### 本地转录 provider 能力

实际后端存在可替换的转录 provider：`WhisperCpp.transcribe(audio_path)` 向本机回环 Whisper 服务发送音频，返回文本、语言与逐段时间信息；另有 `ready()` 检查。这个边界本身可复用，但不是已交付的远程文件 API。

将本机下载的 X 视频交给 Mini，需要新增真实文件接收/登记、原件哈希与来源绑定、受控队列及结果获取入口，或在另行实现的受控 SSH 作业桥接中完成同等保证。直接调用底层转录服务不会自动获得现有任务持久化、单 worker 编排、媒体证据和幂等，不能据此声称通用文件完整流程已实现。

## 原始证据位置

- 本机 [Wiki API 适配器](../../src/nashsu-api.js)：固定项目匹配、发布前检查、读回、搜索。
- 本机 [媒体客户端 CLI](../../scripts/media-service.mjs)与[媒体客户端](../../src/media-service-client.js)：受保护令牌文件加载和现有能力。
- 本机 [采集依赖清单](../../requirements-capture.txt)。
- [既有运行说明](../nashsu-local.md)及其[首版实测报告](nashsu-install-test-2026-09-27.md)仅作历史基线，本次实时检查分别记录。
- Mini `<SERVICE_ROOT>/api_v1.py` 指向当前 release 的 gateway；gateway 加载 `<ACTIVE_RELEASE>/backend/src/douyin2text`。
- Mini 当前 API 源码：`api.py` 第 244–309 行提交与身份关联、第 311–339 行恢复；`pipeline.py` 第 65–175 行来源、下载、音轨及限制核验；`providers/whisper_cpp.py` 第 11–78 行本地转录 provider。
- runtime 读取的 API 源码 SHA-256：`c53a192055b41e9da9212b6e2a42a6ec26972f857ffcb83beed309d232af0f18`；pipeline SHA-256：`4a3a10dcc8ca850b3804ed35092f3fc072440d53faec8cb210fec1b689e3f295`。实施恢复前应再核对，避免服务版本漂移。

本轮没有验证新任务完整下载/转录、实际重启恢复、文件上传、新来源适配或 Wiki 发布；这些仍需主线程按开发任务实测。
