# 微信与抖音现成工具调研

日期：2026-09-27。范围：公开仓库 README、源码与许可证；未安装或运行候选，未读取本机登录会话。以下是实施建议，不是已确认选型。首版视频仍只下载并保存标题简介，转录为后续可选能力。

## 建议先验证

1. **微信公众号：MagicMD。** 输入单篇公开文章链接，输出 Markdown、本地图片、元数据和提取报告，接口最贴合当前需求。还需补原始响应保存、不可覆盖归档及失败状态。
2. **抖音：F2。** 已有 Python 下载器与单作品接口，源码明确区分图片和视频。先验证视频、图文、短链接、登录失效以及 1080p 上限。下列 douyin-downloader 系列存在上游已披露的请求验证阻断，不列为可直接运行的替代品。

这些工具可被平台脚本调用，不必重新实现整套抓取。成本及稳定性须用样本实测，不能由 README 或星数得出。

## 候选对比

| 项目 | 第一手资料已支持的能力 | 接入判断及缺口 |
|---|---|---|
| [didilili/MagicMD](https://github.com/didilili/MagicMD) | 微信文章转 Markdown，下载图片，输出 `metadata.json`、`extraction-report.json`；CLI 与 Python API。源码通过 `#js_content` 提取正文。MIT。 | 优先候选，预计适配较少。面向公开文章；不能据此承诺复用当前个人浏览器登录。须验证复杂排版、图片顺序和受限页面。 |
| [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) | README 列出 `fetch_one_video` 支持单视频和图集；下载源码有图片、视频、简介分别保存的路径；支持 Cookie 配置。Apache-2.0。 | 适合脚本封装，预计适配中等。需要统一 Markdown、原始数据快照、错误状态及清晰度选择。当前默认分支为 `v0.0.1.8-pw3`，采用时应锁定验证过的提交。 |
| [JoeanAmier/TikTokDownloader（DouK）](https://github.com/JoeanAmier/TikTokDownloader) | 抖音视频/图集下载、数据采集、Cookie 配置。GPL-3.0。 | 成熟功能候选，但当前 README 概览与具体登录章节不一致：概览仍列浏览器读取 Cookie，操作章节已标记弃用。因此不能把自动复用浏览器 Cookie 当成已验证能力。可评估独立进程调用，暂不直接复制代码。 |
| [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) | MIT；抖音视频/图文 CLI、Cookie 获取、可选转录。当前 README 明确单视频/图文等 CLI 下载受请求验证阻断，换 Cookie 或重试不能修复，主页浏览器兜底也不保证成功。 | 不作为当前单链接首选。README 推荐的 Douzy 桌面应用与 Python CLI 是不同能力边界，不能把桌面能力当作可复用开源脚本能力。 |
| [Mintnoii/douyin-downloader](https://github.com/Mintnoii/douyin-downloader) | README 宣称单视频、`/note/` 与 `/gallery/` 图文、浏览器登录；可选 faster-whisper 本地转录或 OpenAI API，输出 TXT/JSON；源码存在转录和 Cookie 获取实现。MIT。 | README 克隆命令指向上述 jiji262 仓库。保留为转录实现参考，不能因 README 没有阻断警告就推断其已解决上游问题。浏览器兜底主要验证 `post` 分页；首版关闭转录。 |
| [wechat-article/wechat-article-exporter](https://github.com/wechat-article/wechat-article-exporter) | 曾支持 HTML/Markdown 等多格式导出，HTML 打包图片与样式。MIT。 | **不建议作为新项目主方案。** 当前 README 宣布 2026-07-30 停止维护，公众号批量同步依赖的上游接口关闭，公开 API 已下线。现存格式转换代码可供参考；不能把历史功能描述视为可用承诺。 |

## 源码与许可核查入口

- MagicMD：[微信解析器](https://github.com/didilili/MagicMD/blob/main/src/magicmd/platforms/wechat.py)、[许可证](https://github.com/didilili/MagicMD/blob/main/LICENSE)。README 的 Python API 返回本地图片路径，便于 Wiki 迁入自己的附件目录后改写 Markdown 引用。
- F2：[抖音下载器](https://github.com/Johnserf-Seed/f2/blob/v0.0.1.8-pw3/f2/apps/douyin/dl.py)、[许可证](https://github.com/Johnserf-Seed/f2/blob/v0.0.1.8-pw3/LICENSE)。`download_media` 根据图片列表或视频地址选择处理，`download_desc` 保存简介；这尚不等于完整 Wiki 归档格式。
- DouK：[README 的 Cookie 操作说明](https://github.com/JoeanAmier/TikTokDownloader#readme)、[许可证](https://github.com/JoeanAmier/TikTokDownloader/blob/master/LICENSE)。采用前应把所选版本的授权文件与发布说明一起固定。
- Mintnoii：[转录实现](https://github.com/Mintnoii/douyin-downloader/blob/master/core/transcript_manager.py)、[登录 Cookie 获取](https://github.com/Mintnoii/douyin-downloader/blob/master/tools/cookie_fetcher.py)、[许可证](https://github.com/Mintnoii/douyin-downloader/blob/master/LICENSE)。本地实现显式选择 CPU 或 CUDA；不能据此声称利用这台 Mac 的 Apple GPU。
- 微信 exporter：[停止维护说明及现有功能](https://github.com/wechat-article/wechat-article-exporter#readme)、[许可证](https://github.com/wechat-article/wechat-article-exporter/blob/master/LICENSE)。此前候选拼写 `jooooock/wechat-article-exporter` 本轮返回 404，不作为另一独立可用项目推荐。

## 原型验收建议

- 微信：一篇纯文本、一篇多图/代码文章、一篇受限或失效文章；验证正文完整、图片本地化、失败可辨认。
- 抖音：一个视频、一个图文、一个分享短链接；只处理目标作品，不自动扩展主页/合集。
- 视频：优先选择不超过 1080p 的源；本轮资料尚不足以确认各工具能直接设定这一上限，需检查解析结果和下载器配置。
- 登录：由用户授权的专用会话提供 Cookie；模拟失效时明确暂停并返回需人工处理状态，再验证恢复。
- 归档：保存取得的原始响应和媒体，Markdown 与资料卡另存；重复投递和中断恢复由 Wiki 自己验证，不仅依赖第三方下载记录。
