# SPEC #40 首批开发任务

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

本表记录依赖和范围；状态以各 Issue 与最终验收报告为准。SPEC #40 保持父规格，不在本轮关闭。后续普通网页和小红书单独接入，未在此提前宣称完成。
