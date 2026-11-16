# Mini 完整转录服务独立发行调查

2026-11-16；为 #51 独立安装包准备。此处是源码与部署依赖调查，不是独立包已安装验收。本次仅只读核对 Mini 既有服务，没有修改生产、重启服务、读取令牌/运行配置/数据库或下载模型和真实媒体。

## 结论

当前 `services/mini-media/` 是既有服务上的通用文件扩展，不是完整服务器发行包。完整可运行包至少需要 `douyin2text` 核心 API/队列/制品/抖音与 ASR provider、通用文件扩展、通用翻译 adapter、受控的本地翻译实现及其 QA，以及启动与初始化入口。不能只压缩扩展目录就声称新机器可运行。[当前扩展说明](../../services/mini-media/README.md)、[现有通用转录实现](../../services/mini-media/generic_media.py)、[现有翻译 adapter](../../services/mini-media/translate_generic.py)

本机为发行准备保留了经过白名单筛选的源码副本：`.local/mini-distribution-source/`（忽略目录）。包含 active release 的 `backend/src/douyin2text`、`pyproject.toml`、官方样例配置；服务根目录共享翻译/QA源码与依赖清单；F2 和 whisper.cpp 的 LICENSE。仅23个代码/样例/清单文件；同目录 `source-inventory.json` 记录逐项 SHA-256。没有复制实际 `config.json`、api-token、SQLite、生产数据、模型和会话。副本可供实现使用，真正发行前还须明确纳入 Git 跟踪并检查来源/许可证。

## 当前完整依赖

只读核对的生产 active release 是 `0.8.0-file-b5e457ecb418`。核心 backend 与本仓库通用扩展分开安装，现 gateway 负责把两者组合起来。

| 层 | 实体与依赖 | 可独立发行的处理 |
| --- | --- | --- |
| 核心 API | `backend/src/douyin2text/{api,runtime,pipeline,artifacts,markdown,verification,safe_network}.py`、providers目录；Python >=3.11，FastAPI/Uvicorn/HTTPX/httpcore/Pydantic/psutil | 必须连同完整 package 交付，不能复制旧的3行 api_v1 wrapper |
| 通用媒体 | 本仓库 `generic_media.py`、`translate_generic.py`、`transcript-identifiers.json` | 在核心模块导入后、worker 启动前 register；保留同一 jobs 表与 OS worker 锁 |
| 抖音来源 | `douyin2text.providers.f2.F2Source` 动态导入 F2；source 解析、metadata、1080p候选选择与下载绑定由此提供 | F2 是原抖音 URL route 所需依赖；不能仅因文件上传无需 F2 就漏掉全部抖音能力 |
| ASR | `douyin2text.providers.whisper_cpp.WhisperCpp` 连接回环 whisper-server `/health`、`/inference`，multipart WAV，verbose_json，language auto、temperature 0 | whisper-server 必须另行安装/构建并启动；不是 Python wheel 自带的推理引擎 |
| 解码/提取 | FFmpeg/FFprobe；当前生产二者9.0.2 | 作为显式工具依赖解析，记录版本；不直接复制开发机二进制当作通用可移植发行 |
| 本地中文翻译 | 现有 `translate_segments_mlx.py` 依赖 `mlx_lm`、`make_sampler`、`artifacts.atomic_json/digest`、`segment_delivery.validate_segments`、`translation_qa.stray_words` | 共享源文件一同交付并去除绝对路径；单独 MLX Python 环境；不把现有账号或模型缓存装入包 |
| 模型 | multilingual ggml-medium；MLX Qwen3-4B-Instruct-2507 4bit | 模型下载与文件校验单独初始化，保留模型来源、revision和SHA；安装包不夹带生产模型目录 |
| 旧管理 UI | 当前 gateway 还 import `dashboard_api`、`settings_api`、`ai_articles`，后者继续 import `control_state/ai_engine` 和服务根 artifacts | 独立版建议新建精简 gateway，只组装 core API + generic；旧管理 UI不是#51要求，不把其未审查运行状态/账号配置一并复制 |

上表源码依据为白名单副本（具体字节见 source-inventory）以及本仓库扩展。core API 的既有 HTTP、来源和媒体严格契约在 [media-service-v1](../contracts/media-service-v1.md)；新通用接口契约在 [Mini 通用媒体规格](../specs/mini-generic-media.md)。

## 必须去掉的主机绑定

1. `runtime.py` 已支持 `DOUYIN2TEXT_DATA_DIR`、`DOUYIN2TEXT_CONFIG`，但默认数据根仍是开发者的 `/Users/mac/...`。发行启动器必须在导入 `douyin2text.api` 前设置目标机路径；该模块导入时就读取 `DATA/state/api-token`。
2. 核心 `pipeline.py` 的 probe、全量 decode、extract 和 WAV 转换多处硬编码 `/opt/homebrew/bin/ffmpeg|ffprobe`。需要统一读取经过校验的配置/可执行位置；本仓库 generic 分支虽然允许 `generic_ffmpeg/generic_ffprobe`，其默认值仍是 Homebrew路径。[generic当前工具选择](../../services/mini-media/generic_media.py)
3. 共享 `artifacts.py` 的 DATA 固定为开发者媒体目录；共享 translator 的 modeldir 固定为该目录内 Qwen 模型。二者需要从与 core 一致的环境/安装配置取值，不能只改 gateway。
4. core markdown 的本地翻译 Python/script 有 package 内默认路径，但那里没有完整 MLX环境和脚本。新配置必须显式填入实际翻译环境和可分发共享脚本。
5. 生产 `requirements.lock` 中 F2 是绝对 `file:///Users/mac/.../vendor/f2` 引用，不能当可安装锁文件发行。应改用已核对 commit 的源码依赖或 vendored source（保留 LICENSE），并在新环境解析/验证锁定依赖。现有锁文件仅证明生产环境的依赖记录，未证明 fresh install 全部版本可从当前索引解析。
6. 生产 gateway 的 SERVICE、config路径和端口写死；直接复制会连接错误的服务根目录。精简 gateway 应以安装包相对位置加载代码，以参数/环境配置数据与监听端口，保留 authenticated API及单worker。
7. core health 检查模型时使用 `DATA/models/Path(model.path).name` 并经过 safe_path；模型安装布局要与该约束一致，不能只把 whisper-server 指向数据根外的任意模型后声称 doctor 可用。

## 初始化和服务边界

安装器应只初始化自己的目标私有数据目录，创建0700目录以及0600 token/配置；原件与既有状态禁止覆盖。至少涉及 state、models、metadata、transcripts、tmp、video、audio、file-jobs。`state/api-token` 在 import 前必须存在；SQLite和表由既有 API 初始化，不复制生产数据库来模拟新安装。核心 worker 恢复已存在的 queued/处理中状态，通用任务共用这条队列。

当前原生 whisper LaunchDaemon 参数为回环8767、多语言medium、auto语言、4线程、best-of2以及私有临时目录；网关另行监听经过配置的地址8765。发行时服务名、数据目录、模型路径及端口应属于安装目标。隔离安装验收应选不同数据根和端口，避免启动第二个生产写入者或无意抢占现有 ASR。

本地英文翻译启用需要真实 MLX环境和模型；未完成模型初始化时明确暂停或只允许已支持路径。不能以 translation.enabled=false 却声称英文完整中文交付。既有通用 adapter 对中/英文及逐段中文、品牌标识、发音字面量和修订审计的校验须保留。[来源实现](../../services/mini-media/translate_generic.py)、[共用字面量策略](../../services/mini-media/transcript-identifiers.json)

## 版本与许可证依据

- F2 生产源码 commit `3f842b6b28bf70e5525631f7d992245b2dbccc0b`，vendor Git工作树干净；project metadata 与 LICENSE 均声明 Apache-2.0。[固定版本 LICENSE](https://github.com/Johnserf-Seed/f2/blob/3f842b6b28bf70e5525631f7d992245b2dbccc0b/LICENSE)、[项目 metadata](https://github.com/Johnserf-Seed/f2/blob/3f842b6b28bf70e5525631f7d992245b2dbccc0b/pyproject.toml)
- whisper.cpp 生产源码 commit `60c0be6ac8fa71b1a2ae2dd938a31a34a508e774`，vendor Git工作树干净；LICENSE 为 MIT。[固定版本 LICENSE](https://github.com/ggml-org/whisper.cpp/blob/60c0be6ac8fa71b1a2ae2dd938a31a34a508e774/LICENSE)
- Qwen MLX模型现有翻译元数据记录 revision `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`；对应 model card 声明 Apache-2.0，来源为 Qwen/Qwen3-4B-Instruct-2507。本次只读模型README和文件名，未复制模型或重新证明本地权重与该revision的全部文件一致。[固定模型 card](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit/blob/50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b/README.md)
- FFmpeg/FFprobe 只核对到生产版本9.0.2；尚未完成该二进制构建选项及再分发清单核对。因此当前不建议将现有brew二进制直接装入本项目发行包；由安装步骤获取明确依赖后记录实际版本。
- 项目自有 Mini backend 的 package metadata 没有单独 license字段；本仓库根目录也未发现项目级 LICENSE。这里仅记录事实，不替所有权人选择新许可证；第三方源代码/模型的许可证、来源和固定revision在发行清单中保留。

## 需要实现后再验收

干净目录安装与依赖解析；配置初始化/升级不覆盖原件；隔离 gateway启动；真实文件上传、hash/range、失败与重启续作；抖音URL接口保留；本地英文译文完整对齐；模型与工具来源检查；归档中无私人配置、令牌、数据库、媒体或模型缓存。当前生产已成功运行不是上述新安装行为的替代证据。
