# 本机 nashsu 运行说明

## 当前部署

2026-10-01：已部署 **0.4.1**，新增公开博客、文本、多链接、背景、别名和显式刷新；[验收报告](research/v0.4.1-acceptance-2026-10-01.md)。插件 loaded、网关健康、启动恢复与原生 API 验证通过。以下版本说明保留历史证据。

2026-10-01：插件已升级 **0.4.0-preview.2**。正式原文在 `raw/sources/`，来源卡与中文全文合并在 `wiki/sources/`；处理任务与临时文件移到 Vault 外。详见[本次迁移与部署](research/canonical-library-2026-10-01.md)。下文旧版记录仅供历史核对。

2026-10-01：插件已更新为 `0.3.0-preview.3`，修复 X 大小写匹配、Wiki Flash 代理及微信视频误报。详见[修复与重跑记录](research/retry-2026-10-01.md)。

2026-09-28：Personal Wiki 插件为 `0.3.0-preview.2`；nashsu 桌面保持 `0.6.11`。日常收集使用 `小婕 wk 记录：链接`，由受保护的编译流程处理。下方 `import_capture.py` 为早期桌面监听集成说明，不能替代当前插件入口。部署、备份与限制见[部署记录](research/deploy-2026-09-28.md)。

## 打开与检查

```sh
open '/Users/mac/Applications/LLM Wiki.app'
python3 scripts/wiki_status.py
```

实际知识库在 `/Users/mac/Documents/Personal-Wiki-Vault`，可用 nashsu 或 Obsidian 打开。`wiki/index.md` 是知识索引；原始资料在 `raw/`。应用已记住该 Vault，Codex 使用本机 ChatGPT 登录。

固定发布包及哈希见 `upstream-nashsu.json`。下载后核对哈希，解包至用户 Applications 目录即可；不要覆盖已经存在且版本不明的应用。配置位于系统 Application Support 的 `com.llmwiki.app/app-state.json`，包含本地接口令牌，不得提交或粘贴到聊天。

## 导入已有抓取内容包

这一步不负责网络抓取；内容包须已包含 `article.md`、原始 HTML 和附件。当前仅支持一条收集消息对应一个 X 或微信内容包。

```sh
python3 scripts/import_capture.py \
  --vault /Users/mac/Documents/Personal-Wiki-Vault \
  --snapshot /absolute/path/to/captured-package \
  --name readable-english-article-title \
  --message '小婕收集 https://x.com/author/status/123'
```

归档包只增不改，原始文件逐个记录哈希；适配后的 Markdown 放入上游监听的来源目录。nashsu 常驻时自动排队加工。返回 `archived` 只代表原件已保存，编译状态需另查。重复输入返回 `existing`；显式重新收集使用 `--refresh`，新内容保留新快照。

原文入口和来源卡使用可读的英文文件名。英文一级标题可自动转为短横线文件名；中文标题由调用方通过 `--name` 提供英文短标题。相同文件名出现新内容时追加 `--2`、`--3`，内部去重 ID 及附件包目录仍保留哈希。已有两份样本已迁移为 `wechat-medical-service-pricing-guidelines.md` 与 `x-39-video-styles-and-opus-workflow.md`，原始字节未改动。

初次编译可能产生错误的原件相对链接。验收发现这种问题时，可针对明确的初次生成来源卡执行：

```sh
python3 scripts/finalize_capture.py \
  --vault /Users/mac/Documents/Personal-Wiki-Vault \
  --source-id <import返回的name或来源卡文件名去掉md后缀>
```

脚本保留生成页修改前历史，不修改原件。不要把它作为长期手写笔记的自动编辑器。

## 开发验证

```sh
python3 -m unittest discover -s tests -v
git diff --check
```

真实抓取依赖及样本仍在本机忽略目录 `.local/capture-test/` 和 `.local/nashsu-test/`。正式平台采集命令、飞书连接和故障恢复尚需继续实现，详见[安装实测报告](research/nashsu-install-test-2026-09-27.md)。
