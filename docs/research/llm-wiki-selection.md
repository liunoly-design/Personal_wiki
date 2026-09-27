# LLM Wiki 底座选型

调研日期：2026-09-27。以下为建议，尚未确定采用、安装运行或验证编译成本。

用户后续反馈：接受桌面应用常驻，可以考虑基于 nashsu 迭代；正在确认外部服务接入及费用。此反馈不代表已选定模型付费方式，也未明确回答首版自动知识加工范围。

## 建议

**优先用 nashsu/llm_wiki 做主底座原型**：用户希望复用完整项目，并已有本机常驻运行的方向；它已有知识编译、模型接入、图谱和摄入队列，Google 与 Codex CLI 都有实际实现。我们保留平台采集脚本，补飞书触发、回执及归档可靠性。

关键取舍是桌面应用常驻：HTTP rescan 经文件事件进入 TypeScript 摄入队列，不是独立后台编译服务。若用户要求不依赖桌面应用，则优先验证 atomicstrata/llm-wiki-compiler。后者已有 CLI/SDK/MCP，但 Gemini 路径尚未验证。两者都没有经过本项目端到端验收，不能据源码断言稳定性或成本。

## Karpathy 原始模式

[原文](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)区分三个逻辑层：

1. **Raw**：保存原始材料，不被后续 AI 加工覆盖。
2. **Wiki**：模型维护来源摘要、实体、概念、比较与综合页面，并建立交叉引用。
3. **Schema**：规定组织方式及摄入、查询、检查的规则。

摘要、概念、综合属于 Wiki 内部页面类型，不是原文所称三个层级。查询成果可以回写 Wiki；检查用于发现断链、孤页及内容矛盾。

本项目建议的关系是：原件及附件 → 来源卡 → 概念/实体与主题 → 跨来源综合；所有派生判断可追溯来源。目录名遵循选定上游，再映射稳定 ID 和本项目约束，不先重写一套目录协议。

## 候选比较

Stars 为调查时 GitHub API 快照；时间为默认分支最新提交日期。搜索受未认证 API 限流影响，以下不是全 GitHub 排名。

| 项目 | Stars | 最近提交 | 许可 | 对本项目的适配判断 |
|---|---:|---|---|---|
| [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) | 20,003 | 09-27 | GPL-3.0 | 首选完整应用；须验证常驻与外部摄入 |
| [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) | 3,581 | 09-21 | MIT | Agent 规则与工具，可靠队列仍需补充 |
| [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | 2,372 | 07-23 | MIT | 适合借鉴证据规则，后台能力较少 |
| [atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler) | 2,138 | 09-27 | MIT | 后台首选备选；模型兼容性需验证 |
| [lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki) | 1,646 | 08-09 | Apache-2.0 | API/MCP/Web，维护组件较多 |
| [nvk/llm-wiki](https://github.com/nvk/llm-wiki) | 1,349 | 09-15 | MIT | Agent 工作流与检查器，编译依赖 Agent 执行 |

具体版本、API 快照来源及源码依据见[指定项目核查](llm-wiki-named-projects.md)和[其他候选核查](llm-wiki-alternatives.md)。热度与提交日期不能替代可靠性测试。

## 引入与验收路线

1. 保留当前 Personal-Wiki Git 历史、需求和 Matt Pocock skills；固定上游 commit，以独立目录或 fork 引入，保留许可证与升级来源。
2. 首轮使用隔离 Vault 和已授权的公开样本；实际 Vault 为 `/Users/mac/Documents/Personal-Wiki-Vault`，原件、附件、密钥不进入代码仓库。
3. 复用已验证的 X、微信公众号采集方式，将原始内容及附件归档，再交底座生成来源卡、概念/实体与引用。当前不处理抖音，不对未转录视频编造摘要。
4. 验证外部导入至完成回执全链路；核对原件哈希、链接可解析、概念合并、重复消息、进程中断恢复、部分失败，以及关闭窗口/切换项目后的处理行为。
5. 实测模型调用量、时间及失败率后再确定默认模型与升级条件。目前没有成本比较结论。

## 下一轮设计决策

- 是否接受 nashsu 桌面应用常驻，从而优先复用完整应用；否则采用后台编译器方向。
- 首版是否扩展为自动来源卡、概念/实体及已有页面关联；跨来源综合与大范围重构先作为待审候选。

上述决策未确认前，不将选型建议写成已采用架构。
