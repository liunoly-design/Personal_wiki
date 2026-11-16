# 小红书单笔记采集方案调研

调研日期：2026-11-16。范围：为三层收集器的第二层选择单笔记正文与有序图片获取方式。本文是实施建议与现场证据，不新增已确认需求。仅调查三个候选；未安装工具、读取账户 Cookie、登录、触发验证码处理、写入真实 Wiki 或创建采集作业。

## 结论

建议独立实现小范围的公开 HTML 初始状态读取器，主要参考 Apache-2.0 的 `tamnd/xiaohongshu-cli` 对状态对象的安全扫描和字段定义。第一条路径只请求用户提供的单笔记分享链接，保留访问参数，不引入其搜索、签名 API、账户会话、广度爬取功能。[状态提取器](https://github.com/tamnd/xiaohongshu-cli/blob/main/pkg/xhshtml/state.go)、[笔记模型及读取](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[许可证](https://github.com/tamnd/xiaohongshu-cli/blob/main/LICENSE)。

这条路径的代码可行性有一手来源支持，但本机本次没有取得真实小红书笔记全文：官方仓库公开示例及官网探索页均重定向到登录页。因此不能把「实现解析器」写成「真实小红书链路已跑通」，也不能把该响应直接判为用户必须登录。

## 三个候选

| 候选 | 可复用部分 | 依赖和边界 | 建议 |
| --- | --- | --- | --- |
| [tamnd/xiaohongshu-cli](https://github.com/tamnd/xiaohongshu-cli) | 公开 HTML 的 `__INITIAL_STATE__` 提取、单笔记字段、URL token 识别 | Go；Apache-2.0。完整 CLI 还管理匿名会话、签名 API、搜索和采集队列 | 优先参考小模块并自行实现项目所需最小路径，直接引用代码时遵循许可 |
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | HTML 详情路径、图片顺序、实况及视频字段的交叉核对 | 当前代码头和根许可证为非商业学习许可证 1.1；完整项目还有浏览器会话和大批量采集能力 | 只作字段核对，不直接复制或增加为运行依赖 |
| [jackwener/xhs-cli](https://github.com/jackwener/xhs-cli) | 浏览器页面中读取同一详情状态对象 | README 明确默认读取已存 Cookie 或从本机 Chrome 提取，浏览器使用 camoufox；还含互动和发布命令 | 当前不运行。将来若已有单独授权的浏览器读取，可仅参考状态路径，不接入其账户读取和写操作 |

上述依赖与许可来自各项目自身的 [tamnd README](https://github.com/tamnd/xiaohongshu-cli/blob/main/README.md)、[MediaCrawler 许可证](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)、[jackwener README](https://github.com/jackwener/xhs-cli/blob/main/README.md)。本次未运行三个项目，不能核实其 README 的可用性承诺。

## HTML 与 JSON 字段

公开笔记 HTML 的入口是赋值给 `window.__INITIAL_STATE__` 的对象。对象位置为 `note.noteDetailMap[目标 noteId].note`。HTML 使用 camelCase，签名 API 的 `note_card` 则主要使用 snake_case，不能混用。[tamnd 笔记模型](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[MediaCrawler 提取器](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/extractor.py)。

建议读取并校验：

| 内容 | HTML 字段 | 处理要求 |
| --- | --- | --- |
| 笔记身份 | `noteId`，详情 map 的 key | 必须与链接中的目标 ID 一致。不能在目标不存在时取 map 的第一项 |
| 类型 | `type` | 区分普通图文与 `video`，未知类型保留为待补 |
| 标题、正文 | `title`、`desc` | `desc` 是正文候选；不能以 feed 的 `displayTitle`、OG description、标题或可见摘要代替全文 |
| 作者 | `user.userId`、`user.nickname` / `user.nickName` | 保留来源作者，不要求额外访问个人主页 |
| 时间 | `time`、`lastUpdateTime` | 模型按毫秒时间戳处理；保留原始值和提取时间 |
| 图片 | `imageList` | 严格按数组顺序保存，不能按 URL 或字典 key 排序 |
| 话题 | `tagList` | 保留原始标签；不扩展检索 |

字段依据：[笔记模型与转换](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[共享作者模型](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/ssr.go)。两种候选 CLI 都存在「找不到目标时取首项」的实现；该容错不适合本项目的原件来源校验。[tamnd 读取实现](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[jackwener 读取实现](https://github.com/jackwener/xhs-cli/blob/main/xhs_cli/client.py)。

状态对象可能含不符合 JSON 的裸 `undefined`、`NaN`、`Infinity`。应扫描匹配大括号并识别字符串、转义，只在字符串外处理这些裸值，然后用 JSON 解析；不要执行页面 JavaScript，也不要全局替换字符串中的 `undefined`。后者会损坏笔记原文。参考实现的测试方法可借鉴，但异常/截断状态需要本项目测试覆盖。[tamnd 状态扫描](https://github.com/tamnd/xiaohongshu-cli/blob/main/pkg/xhshtml/state.go)。

## 链接身份与访问参数

长链接常见路径为 `/explore/<id>` 或 `/discovery/item/<id>`；URL 解析器识别 `explore`、`item` 后的笔记 ID，并单独保留 `xsec_token` 与 `xsec_source`。[tamnd URL 解析器](https://github.com/tamnd/xiaohongshu-cli/blob/main/pkg/xhsurl/url.go)。MediaCrawler 的官方配置说明指定笔记 URL 必须携带 token。[官方样例配置](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/xhs_config.py)。

建议将去重身份（平台 + 笔记 ID）与获取 URL 分开：前者稳定，后者必须保留原分享 URL、解析后的 URL、跳转链及安全访问参数。通用网页的「删跟踪参数」不可无差别应用到小红书。短链接需要真实 HTTP 跳转解析；本次没有成功的小红书短链接现场样本，因此不能据本报告声称短链接链路已验证。

token 缺失和登录不足也应分开。该项目维护者的现场记录称，无 token 可重定向到带 `error_code=300031` 的 `/404/sec_...`；而 `/login` 也可能是地址限流结果，并不唯一表示需要账户。[维护者现场记录 #18](https://github.com/tamnd/xiaohongshu-cli/issues/18)、[分类规格 #7](https://github.com/tamnd/xiaohongshu-cli/issues/7)。这是上游维护者的实测，不是本项目已复现的所有响应。

## 图片、原图与视频边界

图片逐项读取 `imageList[i].urlDefault`，缺失时再取 `url`；同时保留 `width`、`height`、`traceId`、`livePhoto` 和完整媒体字段。两个已核对实现使用的是服务端提供的默认图片 URL，不能因此称为「无损原图」。本次没有证据证明 `infoList` 的某个场景固定代表原图，也不建议从 `fileId` 自行拼接 CDN 或删除变换参数来冒充原图。[tamnd 图像模型](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[MediaCrawler 图片提取](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/media.py)。

图文正文是否完整，还取决于图中的文字。图片本身与 OCR 派生文字应分开存证，OCR 按图片顺序并标明机器识别。缺少任意必要图片或 OCR 时，不应仅因 `desc` 存在就把含文字图集标为全部完成。这是依据本项目全文要求提出的验收建议，不是上游 CLI 提供了 OCR 的声明。

视频流入口为 `video.media.stream`，分组内候选包含 `masterUrl`、宽高；还可能有备用地址。近期 MediaCrawler 代码指出分组名字还可能是 `EF4` 等，因此可遍历其中列表，不只写死 `h264` / `h265`。实况照片的媒体在该图片项自己的 `stream` 下，应与顶层视频区分。视频笔记的 `imageList` 可能只是封面，描述加封面不等于视频全文。[tamnd 视频模型](https://github.com/tamnd/xiaohongshu-cli/blob/main/xiaohongshu/note.go)、[MediaCrawler 视频与实况处理](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/media.py)。

本次不验证视频下载、无水印地址拼接、OCR 或转写。现有后端若未接通小红书媒体，应真实进入待补，保留已获取的说明和媒体元数据，不能把其声明为完整转写。

## 公开样本的本机只读调查

样本选择：MediaCrawler 官方 `config/xhs_config.py` 中 `XHS_SPECIFIED_NOTE_URL_LIST` 的首项，链接带完整公开 token 与 source；可从上述官方文件复核。本文不复制 token 或笔记正文，避免将公共演示访问参数固化成项目测试凭据。

2026-11-16 本机使用 Python 标准库 HTTPS GET、桌面 UA、无 Cookie、无 Referer，停止在登录/错误重定向：

| 请求 | 实际结果 |
| --- | --- |
| 官方示例笔记长链接 | HTTP 302，目标路径 `/login` |
| 官网 `/` | HTTP 302，目标路径 `/explore` |
| 官网 `/explore` | HTTP 302，目标路径 `/login` |
| 浏览工具直接打开同一公开示例 | 工具返回无法访问，未提供正文 |

上述结果只证明当前环境没拿到笔记 HTML。探索页也被重定向，与「整站公开页受墙」相符；本次无法区分限流、访问环境与访客策略，不能据此断言必须登录、样本已删除、token 已过期或公开 HTML 路径失效。未尝试账户、代理切换、验证码处理或反复重试。

实际已验证范围：三个官方仓库的代码/许可和字段；一个官方公开示例的拒绝行为。**尚未验证：可访问的真实正文、目标 ID、描述长度、图片数量与下载、图片 OCR、视频转写、真实 Wiki 发布。** 成功验收仍需要一个在授权环境可读取的真实单笔记分享样本。

## 对当前实现的建议

1. 封装专用小红书 adapter，公开 HTML → 严格目标 ID 校验 → 正文及有序图片 → Markdown；沿用已有原件保护与受保护 Wiki 发布。
2. 用合成 fixture 测试有序多图、字符串内 `undefined`、正文换行、目标缺失/错配、截断状态、仅 OG 预览、登录重定向、错误 token；合成通过和真实验收分开记录。
3. 失败原因写明「token 不足」「公开页受墙」「目标不匹配」「图像/OCR 未齐」「视频转写未接通」，按已确认的重试/待补规则处理。公开获取失败不自动读取账户会话。
4. 单个真实图文样本完成原 HTML/状态存证、正文核对、有序图片与 OCR、Wiki 读回之后，才将小红书图文链路列为现场跑通；视频和实况继续单独验收。

## 实施时补充的现场证据

初查结果只适用于当时的桌面请求。后续移动 UA + 大陆 CDN 地址的公开 GET 已取得官方示例视频笔记，严格目标 ID 一致。移动页真实字段为 `noteData.data.noteData`（`noteData.hasError=false`），包含 `desc`、有序 `imageList`、作者、时间、视频媒体；预加载 `normalNotePreloadData` 不等于详情。此为原站实测，不能泛化成所有分享 URL 可用。该视频说明和一张图片已保留，完整视频转录仍缺通用 Mini 接口，返回 partial，未当全文发布。

本机 FakeIP 经 Google DNS 定位到境外 CDN，会触发小红书/Rednote 跳转循环；阿里 HTTPS DNS 的已校验公网地址能取得该样本移动详情。两条路径都未读取账户 Cookie；实现只对 FakeIP 做固定 HTTPS DNS 替代，内网及混合解析继续拒绝。[阿里 DoH 官方文档](https://www.alibabacloud.com/help/en/dns/httpdns-doh-json-api)、[Google DoH 官方文档](https://developers.google.com/speed/public-dns/docs/doh/json)。

状态扫描/桌面字段参考固定在 [tamnd/xiaohongshu-cli b60f9a3](https://github.com/tamnd/xiaohongshu-cli/tree/b60f9a384ed32d002aaacbbff95fedb2bdc96682)（Apache-2.0），本项目独立实现 Python adapter，没有加入该 CLI 或 MediaCrawler 的签名、搜索、账户、爬虫依赖。移动详情字段由本机保存的原站响应验证；报告不提交原响应或访问参数。实际全文、OCR、Wiki 读回验收另外记入交付报告。
