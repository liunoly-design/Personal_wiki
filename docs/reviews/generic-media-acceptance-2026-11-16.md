# Mini 通用媒体验收（2026-11-16）

任务 [#50](https://github.com/liunoly-design/Personal_wiki/issues/50)，基线 `d2da8753d8873d54cdab1331c215ad4dd9e914af`。规格见 [Mini 通用媒体](../specs/mini-generic-media.md)。代码开发 checkout 为 wiki-dots-migration；用户原 checkout 的历史改动未迁移覆盖。

## 实现与环境

客户端取得平台媒体并保留原始响应、规范来源、下载选择及哈希；Mini 接收真实文件，核对大小/哈希后排入现有持久队列，完整解码、本地 whisper.cpp 转写，英文使用现有本地 MLX 中文翻译。Wiki 仍在本机，Mini 不直接写 Vault；通用任务不触发媒体服务自己的可选 AI 知识增强。

新增显式 `submit/convert --file` 与音视频 supplement；提交时流式快照，原路径之后变化不会改变作业。共用现有两轮待补、代码维护桥接、来源锁、受保护发布和 Wiki 读回/检索。重传、恢复都保留原 Mini 作业，不伪造抖音链接。

Mini 通过版本化 additive adapter 扩展当前 gateway，保留抖音和管理路由；部署前备份 SQLite/入口并确认队列空闲。原件、凭据、状态与签名 URL 均不提交。

## 已完成真实验收

| 输入 | 实测媒体与文本 | Wiki |
| --- | --- | --- |
| 合成中文本地 AIFF | 552,388 bytes，12.432925秒，5段；首段“这是一条个人知识库转录测试”，尾段“全部内容已经处理完成” | `generic-local-voice`，complete、读回/全文检索通过 |
| X 官方 Voice 有声演示 | `OpenAI/status/1993381101369458763`，4,302,378 bytes，64.362667秒，26段；原始英文与本地中文26/26逐段时间戳一致，覆盖0至62秒（尾部容许静音） | `x-voice-mode-speech-transcript`，complete、读回/全文检索通过 |
| 合成中文本地 MP4 | 125,245 bytes，12.430023秒，5段；含视频和完整音轨 | `generic-local-video-aligned`，complete、读回/全文检索通过 |
| 公开小红书视频笔记 | note `6aa3d827000000002802c5c8`，14,612,161 bytes，281.866667秒，135段，原描述/封面OCR/视频稿；转写覆盖0至281.8秒 | `xiaohongshu-public-video-transcript`，complete、读回/全文检索通过 |

另外使用 Anthropic 32秒公开视频验证 X 来源链中的媒体位置、完整下载、原始 ASR 与本地中文翻译；实际音轨只有配乐，机器稿为音乐标签，因此该样本不能证明英文讲话全文。上表另用官方 Voice 演示完成真实英文讲话验收，不把配乐例子计作讲话成功。

所有语音/OCR/翻译均为机器输出，未经人工逐字校订。覆盖检查证明完整音轨已处理及首尾时间范围，不证明逐字正确。

## 拦截与恢复

- 最初合成 MP4 的容器16.8秒、音轨12.433秒，真实时长校验拒收并保留原作业/原件；没有把缺音轨的尾段算作转录成功。修正测试生成参数后，新文件以新 SHA 独立通过。原坏媒体与失败历史保留；随后通过 supplement 提供有效音视频，沿同一本地任务恢复，明确标记用户补料，最终入库/读回/检索通过，没有放宽时长规则或覆盖原件。
- 小红书平台返回 HTTP CDN URL，客户端仅对已允许的 CDN 升级 HTTPS；保留原平台响应，下载仍固定公网 IP。第一次材料未完整时未发布，修复后显式恢复原任务。
- 小红书 Wiki 候选包含中文实体文件名，被既有路径保护拒绝；不改原件或放宽发布规则，沿原转换包使用校验反馈重生成。
- 抖音旧成果接口在扩展服务上重新读取严格 manifest/Markdown，并对视频、完整音轨、封面逐项首中尾 Range 核验通过；未重跑已完成 ASR。
- Mini 在 `waiting_upload` 回执之后实际重启，核实 PID 已改变；同一作业重启后仍为 waiting_upload，重传后 succeeded、5段。具体回执和进程证据保留于私有验收目录。重启窗口的网络失败保留原回执，没有重复建任务。此次是服务进程重启，不是整机重启。

- X 英文样本修复本地翻译的人名、来源地名与明确发音拼写保护规则后，原 Mini 作业和原始 ASR 被复用；中文稿逐段26/26、全部时间戳对应，保留机器修订审计。知识候选中文路径被拦后，沿同一转换包重新生成，最终发布核验通过。

## 自动化与审查

Node 167个通过；Python 来源/保护回归91个（88通过、3个专用登录浏览器测试跳过）；通用服务 HTTP/proof 测试7个，在本机隔离环境及 Mini 环境验证。最终复测为上述数量，已全部完成。

### Standards

首轮与增量共发现4项：目录 symlink 可越界、非英文错误声明英文来源语种、合法标识片段被拒，以及隐式文字任务补媒体时的原文遗漏。已增加目录/叶文件保护、限制并校验源语种、与原ASR逐段核对的标识和发音字面量策略。两次定向复核确认原问题解决，无剩余 P1/P2。服务端修订保留本地模型原始输出，不冒充人工审校。

### Spec

发现3项：获取签名改变导致重复转录、混合语种被误称完整中文，以及文字任务补媒体时的原文遗漏。现以规范媒体身份及SHA/字节数复用首次输入和作业，追加获取证据；旧未知结果沿已存幂等键取回，旧序号显式迁移到真实media ID。双端逐段校验完整中文，英文缺口保留待补。独立 HTTP 复现确认签名、标题变化及别名迁移只有一次submit/upload。

显式 `--text` 与隐式位置参数文字补媒体均保留原文，英文原文字继续经过完整中文阅读流程；已增加HTTP验收。

Standards 4项、Spec 3项均已修复并复核；两轴原最高项分别是目录保护P1和恢复身份P1，最终无阻塞项。

## 边界

单文件1,000,000,000字节、30分钟；本轮没有越限审批入口。仅保留音轨转写，视频画面 OCR、Live Photo、无语音媒体、直播/DRM、Mini Wiki 接管和整机恢复未在此验收。后台模型与本地 ASR 就绪不替代具体作业成功。已有备份调度未改变。

## 最终部署与入口核验

Mini 最终版本 `0.8.0-file-b5e457ecb418`，服务版本0.8.0；generic模块、通用MLX adapter、共用策略文件与已提交源码逐项SHA-256相同。客户端核心修复提交 `7ce3869ad609e3b09e96e54ff262c445ccad81a7`；原文字补料保护已在执行代码提交 `51883b5d0632d93d6e33f2b3b8d3187736d29710` 中完成，并通过不可变 release 启用；之后的同步状态文档提交不改变执行代码。

全局 personal-wiki skill 已同步新文件能力；launcher/worker 指向版本化 current，实际 `--help` 展示 `--file`，doctor 为 Wiki/media ready。使用已部署 launcher 对上表4个任务重新 run，全部返回 complete；另有原任务音视频补料实测也已 complete（来源卡 `generic-local-video`），再次核验原件、Wiki 回读及全文检索。私有验收回执在本次开发 checkout 的 `.local/generic-media-live/`，不进入 Git。

当前完整交付中文与英文语音；其他语种、混合语音内未译英文整段、无语音及不完整稿保留待补。单文件限额和后续范围以规格为准。

## GitHub 同步（2026-11-16）

代码及报告已推送至 [codex/wiki-ingestion-cli](https://github.com/liunoly-design/Personal_wiki/tree/codex/wiki-ingestion-cli)，并设置远端跟踪。此前 HTTPS 缺少凭据的问题已解决：复用本机已有 SSH 密钥，确认账号为 `liunoly-design`，将本仓库 origin 切换至 `ssh://git@ssh.github.com:443/liunoly-design/Personal_wiki.git`，仓库级配置选用该密钥。

SSH 主机指纹已对照 [GitHub 官方公布值](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)，连接使用 [GitHub 官方 SSH 443 入口](https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port)。已成功 fetch 和普通 push；验收报告可从该分支直接读取。实际密钥、凭据、原始媒体和运行回执继续留在本机私有目录。

