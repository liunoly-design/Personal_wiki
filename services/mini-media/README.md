# Mini 通用文件转录扩展

`generic_media.py` 在现有 `douyin2text.api` 上注册鉴权 HTTP 接口，并对原 worker 的 process / evidence / snapshot 三个边界分派文件任务。数据库、OS worker 锁、ASR provider 和原抖音路由保持同一实现；通用资料不进入服务端可选 AI 文章增强，知识分析交由 Wiki。

基线为 Mini 已运行的 `0.7.7-2355e9f8365d`，gateway/API 实体位于服务的 versioned release；仓库不复制服务器配置、凭据或私人原件。`deploy.py` 校验当前 release 身份，复制新 release，校验集成点；显式 `--activate` 只在队列空闲时备份 SQLite 和入口并原子替换入口。替换后由已有 system LaunchDaemon 重启加载；先检查进程身份，使用原有用户进程或 launchd 控制。回滚恢复该次 backup 的入口和 active-release.json，不回滚或删除新原件/数据库。

端点：创建 `POST /v1/file-jobs`；流式 `PUT /v1/file-jobs/{id}/content`；显式失败恢复 `POST /v1/file-jobs/{id}/resume`；共用 `GET /v1/jobs/{id}` 状态；结果 `GET /v1/file-jobs/{id}/manifest|markdown`；带 Range 的 `GET|HEAD /v1/file-media/{id}/original|audio`。均要求 Bearer；token 只读取现有服务私有文件。服务不获取源站 URL，不返回服务文件系统路径。来源声明由客户端获取证据哈希绑定，不声称 Mini 独立向平台认证。

原件流式写入、核对 SHA/字节数后才排队。中断沿同一任务重新传完整文件；同键异请求冲突。解码与音轨/时长、ASR 首尾和段落检查成功才发布机器稿；转换及原始 ASR checkpoint 均绑定输入与模型哈希。支持的格式/限制以规格及程序校验为准；本轮没有越限审批。音频留在 LAN Mini 的 whisper.cpp，非中文稿使用已配置的本地 MLX 翻译。

合成 HTTP/proof 回归：在含 FastAPI / httpx 的隔离 Python 环境运行 `python -m unittest discover -s services/mini-media -p 'test_*.py'`。本机测试依赖 FastAPI 0.128.8/httpx 0.28.1；Mini 运行环境另外运行同一测试。实际转录、Wiki 入库和服务重启结果见 [验收报告](../../docs/reviews/generic-media-acceptance-2026-11-16.md)。
