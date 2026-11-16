# SPEC #40 摄取开发任务

来源：[三层资料摄取规格](../specs/three-layer-ingestion.md) / [SPEC #40](https://github.com/liunoly-design/Personal_wiki/issues/40)。用户已要求拆分并开始实现，优先 X、抖音、公众号。测试边界沿用已确认的记录、只转换及其任务恢复行为。

| 任务 | 交付 | 阻塞 |
| --- | --- | --- |
| [#41](https://github.com/liunoly-design/Personal_wiki/issues/41) | 统一 CLI、纯文字转换/入库、无 Flash 强制前置、保护与状态 | 无 |
| [#42](https://github.com/liunoly-design/Personal_wiki/issues/42) | X 目标/串文/引用、长文章全部正文、图片与 Wiki 核验 | #41 |
| [#43](https://github.com/liunoly-design/Personal_wiki/issues/43) | 公众号完整正文和图片、转换与 Wiki 核验 | #41 |
| [#44](https://github.com/liunoly-design/Personal_wiki/issues/44) | Mini 抖音持久作业、完整转录、只转换/入库与核验 | #41 |
| [#45](https://github.com/liunoly-design/Personal_wiki/issues/45) | 两轮待补、手工正文/截图补料、阶段续作和去重 | #42、#43、#44 |
| [#46](https://github.com/liunoly-design/Personal_wiki/issues/46) | Codex 开发 session 交接、回归、版本化启用、skill | #45 |
| [#47](https://github.com/liunoly-design/Personal_wiki/issues/47) | 三来源真实样本、回归、重启恢复与审查报告 | #42、#43、#44、#45、#46 |
| [#48](https://github.com/liunoly-design/Personal_wiki/issues/48) | 第二批：普通网页正式接入与独立验收 | #41、#45、#47 |
| [#49](https://github.com/liunoly-design/Personal_wiki/issues/49) | 第二批：小红书单笔记图文/视频接入 | #41、#45、#47 |
| [#50](https://github.com/liunoly-design/Personal_wiki/issues/50) | Mini 通用文件、小红书/X 视频持久转写接口 | #44、#47 |

本表记录依赖和范围；状态以各 Issue 与最终验收报告为准。SPEC #40 保持父规格，不在本轮关闭。第二批普通网页与小红书图文已独立真实验收并关闭 #48/#49；本轮 #50 接入通用媒体，小红书实况仍待补。

通用媒体规格及执行顺序见 [Mini 通用媒体](../specs/mini-generic-media.md)，任务状态与验收以 #50 和其报告为准。

首批实现及验证见 [三来源交付报告](../reviews/three-source-ingestion-acceptance-2026-11-16.md)。

第二批实现、真实入库、维护补跑和复审见 [网页与小红书交付报告](../reviews/web-xiaohongshu-ingestion-acceptance-2026-11-16.md)。
