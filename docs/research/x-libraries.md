# X 抓取与归档复用候选

日期：2026-09-27。依据上游 README 与源码，尚未安装或用本机账号实测。优先复用现成提取器，再由 Wiki 的归档接口统一保存原件、附件、状态和来源引用。

## 优先验证：baoyu-danger-x-to-markdown

[JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills) 中的这个工具已实现推文/串文和 X Article 转 Markdown、JSON 结果、Chrome 登录及 cookie 缓存。CLI 的 `--download-media` 会下载图片、视频并重写为本地引用。仓库默认 MIT，个别第三方内容按其声明处理。[入口源码](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-danger-x-to-markdown/scripts/main.ts)、[README](https://github.com/JimLiu/baoyu-skills#disclaimer)。

适合先复用其脚本，通过固定版本和统一输出适配接入 Wiki。需要补齐或验证：

- 引用帖格式化目前取作者、URL 和文本，未在该函数内输出引用帖的图片和视频；不能据“支持引用”推定媒体完整。
- 视频按码率排序取最高项，尚未看到 1080p 上限，需增加选择或校验。
- 同作者串文边界、从串文中间链接开始时的完整性，需要样本验收。
- CLI 有复用、刷新并重写已有 Markdown 的行为，应在独立暂存目录运行，由 Wiki 生成不可覆盖的来源快照。
- 保留原始 API 内容证据、附件完整性、失败分类和恢复须由适配层验证，不能只看 Markdown 文件是否存在。

依据：[串文逻辑](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-danger-x-to-markdown/scripts/thread.ts)、[引用与视频选择](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-danger-x-to-markdown/scripts/thread-markdown.ts)、[媒体落盘](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-danger-x-to-markdown/scripts/media-localizer.ts)。

该工具使用非官方 X 接口；首次执行有自身的使用确认流程。当前仅研究代码，没有执行、导入 cookie 或写入其确认记录。

## 其他候选

| 项目 | 能复用什么 | 本项目适配判断 |
| --- | --- | --- |
| [vladkens/twscrape](https://github.com/vladkens/twscrape)（MIT） | Python API/CLI、cookie 会话、原始响应与解析数据、限流处理 | 若需要更直接地保留结构化原始响应，可作为提取层候选；仍需自己组装 Markdown 和附件归档。个人链接归档不需要启用其多账号工作流。 |
| [mikf/gallery-dl](https://github.com/mikf/gallery-dl)（GPL-2.0） | 媒体下载、cookie 认证、命名与下载配置 | 作为媒体补充候选，正文和串文语义需另外处理。官方 README 已声明活跃开发迁到 [Codeberg](https://codeberg.org/mikf/gallery-dl)，选版本时以实际上游为准。 |
| [CandyACE/x-downloader](https://github.com/CandyACE/x-downloader/blob/main/README.en.md) | cookie 登录、图片/GIF/视频、推文元数据及下载状态 | 当前模式把媒体存入 SQLite BLOB，普通附件文件需另行 export；与本项目 Markdown＋附件的直接落盘方式多一层转换，暂不优先。 |

## 最小验证

同一登录会话测试：普通图文、长正文、带视频推文、串文中间帖、含媒体的引用帖各一条。检查正文完整、仅同作者串文、引用媒体不漏、附件离线可读、视频高度不超过 1080、重复运行不覆盖原件。登录过期应产出可识别的认证失败，由 Wiki 通知用户处理。

尚未测量这些工具在本机的成功率、耗时或模型用量；上述推荐仅表示需求匹配程度。
