# 来源转换库候选：有界调研

日期：2026-11-16。状态：讨论阶段候选，未最终选型。

本轮只读取项目官方 README、支持清单、文档和许可证。未安装、未运行平台抓取、未使用账户或用户样本；官方声明不等于本项目已取得全文或通过端到端验收。以下链接对应可变化的上游页面，实施时需固定版本并重新核验。

## 候选与可复用位置

| 候选 | 官方资料能确认的能力 | 依赖、限制与待实测项 |
| --- | --- | --- |
| [MagicMD](https://github.com/didilili/MagicMD) | 官方将公众号列为主要验证目标；生成正文 Markdown、来源元数据、图片与提取报告。通用网页为尽力支持，掘金/CSDN 为实验支持。[支持矩阵](https://github.com/didilili/MagicMD/blob/main/docs/supported-sites.md)、[产物说明](https://github.com/didilili/MagicMD#magicmd-会生成什么) | 默认公众号抓取使用 Camoufox；Python ≥3.11，浏览器依赖另行安装。仅支持公开文章，不处理登录、付费墙、验证码或 App-only 页面。需测试完整正文、长文截断、图片和代码块，不能仅凭生成 article.md 判定成功。[依赖](https://github.com/didilili/MagicMD/blob/main/pyproject.toml)、[限制](https://github.com/didilili/MagicMD/blob/main/docs/supported-sites.md) |
| [Twikit](https://github.com/d60/twikit) | X/Twitter 的 Python 客户端，无需官方 API key；官方文档提供按 ID 取帖、full_text 字段、媒体信息及视频流下载接口。[读取接口](https://twikit.readthedocs.io/en/latest/twikit.html#twikit.client.client.Client.get_tweet_by_id)、[全文字段](https://twikit.readthedocs.io/en/latest/twikit.html#twikit.tweet.Tweet.full_text) | 文档提供账户登录与 Cookie 加载，不能将“无 API key”理解为“无需登录”。返回字段存在不保证当前平台接口可用；需测试长帖、目标身份、同作者串文、引用帖与附件完整性。仅使用读取能力。[认证与 Cookie](https://twikit.readthedocs.io/en/latest/twikit.html#twikit.client.client.Client.login)、[媒体接口](https://twikit.readthedocs.io/en/latest/twikit.html#twikit.media.Video) |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 音视频下载器；官方提取器清单包含 Douyin、twitter、YouTube、Bilibili 等，可作为多个平台共用的媒体获取候选。[支持清单](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) | 官方明确清单内站点也可能失效，可靠判断需要实际尝试。支持从浏览器加载 Cookie；FFmpeg/FFprobe 用于音视频合流与后处理。它负责获取媒体，不能单独完成全文语音转录或 X 串文整理。[依赖与选项](https://github.com/yt-dlp/yt-dlp#dependencies)、[Cookie 选项](https://github.com/yt-dlp/yt-dlp#filesystem-options) |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 官方声明支持小红书、抖音、快手、B站等指定帖子详情采集；可下载图文图片与视频，默认媒体下载关闭。基于 Playwright，并支持浏览器登录态复用。[官方 README](https://github.com/NanmiCoder/MediaCrawler) | 需 Python/Node 与浏览器环境；下载失败可能只记日志而不中断采集，本项目必须另验附件。上游为“非商业学习使用许可证 1.1”，用途条件需匹配后才纳入依赖，不能视为普通宽松许可证库。[许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE) |

## 对本项目的建议，尚未确认

- 公众号和普通网页先评估 MagicMD；X 正文评估 Twikit，媒体下载单独评估 yt-dlp；抖音评估 yt-dlp 或 MediaCrawler 与现有 Mini 媒体服务的接合。小红书/快手可复用 MediaCrawler 的指定帖子与媒体能力，但仍需逐个平台验收。
- 获取器输出统一的原始包、Markdown/待转录媒体、来源身份、完整性与错误记录。语音转录、图片文字识别、待补管理和 LLM Wiki 交接由本项目的共享流程处理。
- 库调用失败后，可切换另一个已配置获取器或进入已授权的 Codex session/浏览器自动化；登录或验证码需要用户处理时准确暂停。候选方法不等于已授权读取任意账户。
- 每个候选先在隔离环境固定版本，用合成样本验证产物协议，再使用获授权的单条平台样本核验全文和附件。失败保留材料进入待补；工具退出成功、正文文件存在或下载 URL 存在均不足以判定入库完成。

本轮未调研语音识别与 OCR 库，不改变既有本地转录、原件保护和费用边界，也未操作 Mac mini 服务。
