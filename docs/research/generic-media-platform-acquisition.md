# Mini 通用媒体接入：X 与小红书视频来源研究

调查日期：2026-11-16。范围是公开视频的资源字段、来源绑定及短样本发现；不代表 Mini 转录或 Wiki 入库已经验收。没有读取私人账户，也没有下载完整音视频。

## X：沿用已取证的线程，逐条收集视频

FxEmbed 的 `/2/thread/{id}` 返回线程；公开 API 规格中 `media.videos[]` 包含 `id`、`type`、`url`、`duration`、`width`、`height`、`formats`，缩略图在 `thumbnail_url`。其中 `duration` 单位是秒：当前维护者源码由 X 的 `duration_millis / 1000` 生成。`formats[]` 的 `container` 可以是 `mp4`、`webm`、`m3u8`，有 `url`，其余 `codec`、`bitrate`、尺寸等字段不保证存在。实测样本 formats 内均没有宽高；不能要求它们齐全才承认视频。[维护者 OpenAPI](https://github.com/FxEmbed/FxEmbed/blob/main/docs/specs/fxtwitter-openapi.json)、[维护者媒体转换源码](https://github.com/FxEmbed/FxEmbed/blob/main/packages/atmosphere/src/helpers/media.ts)

维护者的 `url` 是按自身嵌入策略选出的资源；Wiki 应自己挑选受支持的直接 MP4，保留完整候选及选择理由。当前实现只需要完整有声视频；`gif` 与外部播放器不应自动当成可转录视频成功。X 的原始媒体 ID 与帖子 ID 是不同的，不能拿媒体 ID 替代来源帖子 ID。线程身份、同作者父子关系、引用上下文仍由现有严格解析器验证，然后对每个帖子的视频分别绑定帖子 ID、媒体 ID 和 provider 原始响应。[维护者媒体转换源码](https://github.com/FxEmbed/FxEmbed/blob/main/packages/atmosphere/src/helpers/media.ts)

以下 API 于调查时返回 code 200，原始 JSON 已保留到 ignored `.local/generic-media-research/`。这些是公开来源获取样本，语音内容还需实际听验或 ASR 后核验。

| 来源 | 首帖视频时长 | 线程结构 | 本地原始响应 |
| --- | ---: | --- | --- |
| [Anthropic：Claude for Chrome](https://x.com/AnthropicAI/status/1960417002469908903) | 32.041 秒 | 三帖同作者连续链，首帖有视频 | `1960417002469908903.json` |
| [法国瓜德罗普官方天气通报](https://x.com/Prefet971/status/910031516746514432) | 47.480 秒 | 单帖，非回复 | `910031516746514432.json` |
| [Claude：交互图表](https://x.com/claudeai/status/2032124273587077133) | 79.041 秒 | 单帖，非回复 | `2032124273587077133.json` |

来源发现用到 yt-dlp 自身测试集，再用 FxEmbed 当前公开 API 重新验证，没有把旧 fixture 当成实时可用证据。[yt-dlp X extractor 测试](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/twitter.py)

天气样本三个 MP4 对 `video.twimg.com` 的 TLS 固定公网地址 HEAD 都返回 200、`video/mp4`，Content-Length 分别为 1,106,987 / 2,840,084 / 7,761,912 字节。HEAD 只确认资源元信息，不证明完整解码、声音或转录范围。

### 讲话样本补充

后续 Mini 实跑发现上表 Anthropic 32 秒宣传片只有配乐，ASR 得到两段 `[音乐]`；它可验证视频获取与音乐标记，不能用来证明英文讲话全文。继续调查找到以下三个 ≤120 秒候选。人物讲话的判断来自公开原帖文案及直接引述；本研究没有下载完整媒体或听验，最终仍须 ASR 与范围核验。

| 候选 | 时长 | 讲话依据与线程 | 最低码率 MP4 HEAD |
| --- | ---: | --- | --- |
| [BBCBreaking：Boris Johnson 发言](https://x.com/BBCBreaking/status/971006632443260928) | 83.767 秒 | 官方文案直接引述发言；单帖、`replying_to=null` | 200，2,700,996 字节 |
| [Lis Power：Shep 主播评论](https://x.com/LisPower1/status/1001551623938805763) | 111.278 秒 | 文案明确主播两分钟评论并引述讲话；单帖、`replying_to=null` | 200，1,762,361 字节 |
| [OpenAI：Voice inline 演示](https://x.com/OpenAI/status/1993381101369458763) | 64.314 秒 | 官方语音产品操作演示；两帖连续链，仅首帖有视频，讲话确定性低于前两条 | 200，469,064 字节 |

三条原始响应分别保存在 `.local/generic-media-research/{post_id}.json`；`.local/generic-media-research/speech-candidates.json` 包含规范原帖、响应 SHA、媒体 ID、平台时长、原样 MP4 候选及 HEAD 结果。获取请求使用既有固定公网地址 TLS 连接，不读取账户。发现过程中的 `971006801343901697` 是转发身份，API 返回另一 ID，不能拿来绕过来源 ID 校验；BBC 候选采用重新请求并核验过的原帖 `971006632443260928`。[BBC 原帖](https://x.com/BBCBreaking/status/971006632443260928)、[Lis Power 原帖](https://x.com/LisPower1/status/1001551623938805763)、[OpenAI 原帖](https://x.com/OpenAI/status/1993381101369458763)

## 小红书：使用实际页面返回的资源，不猜原片地址

现有公开样本 `/explore/6aa3d827000000002802c5c8` 的手机页面原始 state 位于 `.local/second-sources/xhs-video-live/package/initial-state.json`。它的结构是 `noteData.data.noteData`；`video.media.stream` 的各个值为候选数组。本样本 h264/h265 两组有内容，h266/av1 为空。每条包含：

- `masterUrl`、`backupUrls`：平台返回的实际资源；本样本主域名为 `sns-video-v4.xhscdn.com`。
- `duration`、`videoDuration`、`audioDuration`：毫秒，约 281,867；`video.media.video.duration` 则是四舍五入后的秒数 282，`video.capa.duration` 为 281，不能混用这些字段判断截断。
- `size`：字节；h264 为 14,612,161，h265 为 18,843,736。两者均 1280×720，format 为 mp4。
- `videoCodec`、`audioCodec`、宽高、码率等辅助元信息。

同一个 `video.mediaV2` 是 JSON 字符串，使用 `master_url`、`backup_urls`、`video_duration`、`audio_duration` 等 snake_case 字段。`video_id` 在该 JSON 内是字符串 `138102968325026504`；外层 `media.videoId` 已表现为精度损失后的数字值。精确身份应取原始字符串，并同时绑定 noteId 与原始响应哈希；不能用 JavaScript number 重建长 ID。上述结论直接来自小红书返回的已保留页面 state，SHA-256 为 `41cfba9bb37f8c6bbed2db83ba5a70c4bbe0e0c578ca55fb46d9e759712bd103`。[公开笔记规范链接](https://www.xiaohongshu.com/explore/6aa3d827000000002802c5c8)

MediaCrawler 当前的媒体模块也明确说明分档可能改用 EF4、EF5、EF6 等内部名称，使用遍历所有数组的策略；它处理的 feed API 是 snake_case，而我们已捕获 HTML state 是 camelCase。因此应独立实现字段兼容，不写死 h264/h265。它的 `origin_video_key` 拼接固定域名是一种资源猜测策略，此轮不应把该猜测当作平台返回资源或来源证据。[MediaCrawler 媒体模块](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/media.py)

MediaCrawler 声明非商业学习许可 1.1，此研究仅参考字段事实，不建议复制其实现。实况图片另有自身 `imageList[].stream`，不能用笔记顶层视频替代每一张实况。签名分享链接、CDN 参数与原始 state 只在受保护运行目录保留，不写入 Git；可读文档仅保留规范笔记链接。[MediaCrawler 媒体模块与许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/media.py)

## 建议给实现的约束

这些是基于上述资源观察提出的实现建议，不增加已确认产品范围：固定平台 CDN allowlist、HTTPS 公网 DNS 解析并固定连接地址、逐跳检查 redirect、拒绝凭据和非标准端口；实际下载按流累计字节并计算 SHA-256；文件接收 API 绑定来源 ID、规范 URL、媒体 ID、原始响应 SHA 与文件 SHA/size。元信息的声明时长/size 只作比较依据，完整解码及提取音频后的实际时长另行记录。多个视频应全部完成或明确进入待补，不能因首条成功就把整篇标记为完整。

这次只验证了字段和资源元信息。完整流程验收还要包含原件留存、Mini 单 worker 转写、语音范围、Markdown 时间戳、服务重启恢复、同一任务幂等、Wiki 原件哈希与读回检索；不能用此研究代替这些验收结果。
