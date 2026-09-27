# 飞书 Wiki 记录入口

## 安装

这台 Mac 已有 OpenClaw 2026.9.6、飞书连接和 wiki Agent。安装本项目插件：

```sh
node "/Users/mac/Documents/personal_OS/Personal-Wiki/scripts/install-openclaw.mjs"
```

安装器创建 Python 虚拟环境、安装抓取依赖、备份 OpenClaw 配置、链接本项目、复用现有小婕的飞书用户及会话白名单，然后重启 Gateway。先打开 LLM Wiki.app 的 Personal-Wiki-Vault。可加 `--check` 只检查前置条件。

目前已验证隔离配置加载和安装前检查，尚未执行实际 Gateway 安装，也未发送真实飞书测试消息。

## 指令

```text
小婕 wk 记录：https://mp.weixin.qq.com/s/文章ID
小婕 wk 记录：https://x.com/作者/status/帖子ID
小婕 wk 查询：名词、话题、相关文章
小婕 wk 讨论：议题
```

仅“记录”实际处理，每条消息一个链接。“查询”和“讨论”返回暂未开放，不调用模型。其余聊天继续由现有 OpenClaw 路由处理。

## 处理顺序

1. 验证飞书原消息、发送者与会话；任务保存到本机后立即确认收到。
2. 已归档 URL 校验原始文件完整性并返回已有路径，不重复抓取或调用 Flash。
3. 抓取正文、图片和可用视频；保留原始提取结果。
4. Gemini Flash 从正文提取名词及所属领域，再只根据名词和领域生成基础解释、例子、歧义提示。
5. 先将解释保存到 Vault 的 `glossary/<english-term>.md`；已有基础页不覆盖。
6. 将原文与单独标注的基础解释交给 nashsu，再生成来源卡、概念、实体和关联；保留到基础页和原文的引用。
7. 完成后回复同一条飞书消息；失败保留已有文件并提示检查本机记录。

基础解释属于模型通用知识，标记为未经独立核实，不冒充文章原文。`raw/assets/` 保存不可变原件，`raw/sources/` 是供 nashsu 读取的适配文件，`glossary/` 保存基础解释，`wiki/` 保存文章派生知识。文件入口使用英文名，附件包仍使用稳定 ID。

## 模型与费用

Flash 复用 OpenClaw wiki Agent 已配置的 Google API 凭证，默认 `gemini-flash-latest`，会消耗该账户的 API 额度；无需另建一份密钥。nashsu 延用当前 Codex CLI 配置。调用记录只保存用量和模型版本，不保存密钥。模型别名实际指向可变化。

## 当前范围与限制

- 支持微信公众号和 X 的公开可读取页面；当前脚本没有接入登录浏览器，会话失效或受限页面需要后续处理。
- X 按目标帖子链接识别正文，保留已包含的引用内容；尚未实现自动展开全部同作者串文与远端引用帖。评论不采集。
- 视频不转录；最多 1080p，超过 30 分钟或 1 GB、无法验证的文件标记待处理。时长和分辨率在下载后检查。
- Flash 和直接 HTTP 瞬时错误最多尝试 5 次；MagicMD 的抓取和 nashsu 的内部重试尚未统一为 5 次。
- nashsu 桌面程序须保持运行并打开对应 Vault；最长等待约 20 分钟，超时保留归档，可在桌面队列继续处理。
- 基础解释用英文 slug 去重，不保证同义词自动合并或不同领域同名词自动区分。
- 任务目录为 `~/.openclaw/personal-wiki/jobs/`。中断中的任务重启后继续；损坏的 JSON 隔离为 `.corrupt`，不阻塞其他任务。没有完成分析的已有归档会提示检查桌面队列，不自动重新付费生成。
- 不含抖音、转录、主动查询、讨论，也没有修改 GTD 数据。

## 验证

```sh
node --test
.venv/bin/python -m unittest discover -s tests
node scripts/check-plugin.js
node scripts/install-openclaw.mjs --check
```

测试涵盖指令路由、原消息校验、重复消息/链接、Flash 先保存再编译、损坏任务恢复、X 目标与长评论/引用区分。插件加载测试使用隔离配置，不重启真实 Gateway。

### 2026-09-27 实测结果

使用此前指定的公众号链接，实际调用 Flash，先保存 34 个基础解释，再完成 nashsu 编译；4 个派生知识页包含基础解释链接。新归档附件完整，30 个原始文件校验通过，编译队列清空。再次提交同 URL 返回已有来源卡，未重新调用模型。X 目标识别使用此前保存的真实 HTML 验证，命中 6243 字符正文并排除评论；本轮未重新下载 X 视频。6 项 Node 测试、9 项 Python 测试及 OpenClaw 隔离加载检查通过。
