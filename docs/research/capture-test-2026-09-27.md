# 三个用户链接的抓取实测

日期：2026-09-27。测试运行在本机；结果保存在被 Git 忽略的 `.local/capture-test/results/`，未写入正式 Vault、未上传原文或附件、未发送飞书消息。视频未转录。

## 结果

| 输入 | 实测路径 | 结果 |
| --- | --- | --- |
| `https://mp.weixin.qq.com/s/5h-3nOxtudYfIMmDUZc5XQ` | MagicMD 0.7.15，显式 HTTP 模式，保存 debug HTML | 成功生成正文 Markdown、HTML、metadata 与 extraction report。标题《全国各地加快对接落地立项指南》，来源江苏医保。正文提取文字 2480 字符，Markdown 2664 字符；正文图片 1 张、封面与分享封面各 1 张。Markdown 的 2 个图片引用均存在，3 个图片文件均通过 Pillow 校验。 |
| `https://x.com/lemomo_ai/status/2103823847632060854?s=20` | 本机 HTTP 获取 HTML；测试脚本用 BeautifulSoup 选择目标 article，markdownify 转换并下载附件 | 保存长文章《开源了39种风格视频库后，我学会了如何用Opus5.5稳定出片》、原始 HTML、2 张内容图片、11 个视频。附件共 305440600 字节；11 个视频全部为 1920×1080，FFmpeg 全文件解码均退出 0，无解码错误。其他评论及头像不纳入派生 Markdown。 |
| `https://v.douyin.com/PscRgCCDvUE/` | 短链接解析；F2 单作品模式；yt-dlp 交叉测试 | 跳转到视频 ID `7685724544639765786`。F2 返回 HTTP 200 但响应为空，重试上限后退出 1；yt-dlp 返回 HTTP 403，提示需要 fresh cookies。未下载到视频，未验证标题、简介或画质。 |

微信单次成功不代表所有微信文章可抓取；X 本次仅验证该长文章页面，不代表串文遍历或引用帖补全已通过。X 页面中 11 个视频均属于本次目标文章，未扩展抓取其他帖子或仓库链接。

## 测试路径差异

- 微信首次 curl 请求拿到“环境异常”验证页；随后 MagicMD 自身的 HTTP 路径取得正文。尚未做受控重复实验定位差异原因。不能将首次验证页视为链接永久不可读，也不能把 HTTP 200 当成成功。
- X 网页搜索工具返回 403，但本机 HTTP 请求取得正文与媒体。本次保存用的是页面解析测试脚本；**没有实际执行宝玉工具的登录后 GraphQL 抓取**，不能宣称宝玉工具已通过本次测试。
- 用户已明确同意仅对指定 X 链接使用宝玉工具的非官方接口；本机该工具没有 cookie 缓存，OpenClaw 管理的浏览器没有目标平台 cookie。本次无需账号接口即可完成该页面保存，未创建全局长期同意记录。
- MagicMD 的 Camoufox 路径尚未验证；F2 的登录后路径尚未验证。

## 浏览器阻塞

OpenClaw 2026.9.6 的 managed Chrome 能启动，CDP ready，但三条链接的 `browser open` 均报 `browser navigation blocked by policy`。

只读检查显示：本机 `mp.weixin.qq.com`、`x.com`、`v.douyin.com` 分别解析到 `198.18.0.100`、`198.18.0.103`、`198.18.0.102`，浏览器未配置自定义 ssrfPolicy。结合地址段与导航错误，怀疑代理 Fake-IP 与导航安全检查冲突；尚未完成根因修复验证。没有放宽导航策略或修改共享 OpenClaw 配置。

抖音后续需要先解决浏览器访问与有效会话，再重测同一个 ID。认证、页面验证与提取器失效应分开定位，不能断言仅登录便能成功。

## 复现材料

- 隔离 Python 环境：`.local/capture-test/venv/`。
- MagicMD 源码：`78aa27f2ffb7d541a8f65508cf5e5bde43a636e4`。
- F2 源码：`c2c52a4da0cfe0ce646cc836738d7f1aca1308f8`（包版本 0.0.1.7）。
- 宝玉源码仅检查：`1567581c26ec29f4216c6e6835415bf30343b0e3`。
- yt-dlp：2026.08.19；imageio-ffmpeg：0.6.0。
- 微信配置：`.local/capture-test/wechat-http.toml`；产物位于 `results/wechat/`，检查结果为 `results/wechat-verification.json` 与 `results/wechat-images-verification.json`。
- X 保存脚本：`.local/capture-test/save_x.py`；媒体校验脚本：`.local/capture-test/verify_media.py`；产物与校验为 `results/x/article.md`、`raw.html`、`manifest.json`、`verification.json`。
- 抖音日志：`results/douyin-f2.log`、`results/douyin-ytdlp.log`；原始网页为 `results/douyin-http.html`。原始日志仅留本地。

## 对实现方案的影响

先保留可用的 HTTP 提取路径，按失败类型再决定是否升级到登录浏览器。微信优先继续验证 MagicMD；X 增加公开 HTML 提取候选，再测试需要登录和串文场景。抖音不能因为已有库而标记为可用。

统一归档仍须实现任务状态、原件保护、幂等与恢复。当前只是三个真实样本的测试，尚未接入飞书端到端流程。
