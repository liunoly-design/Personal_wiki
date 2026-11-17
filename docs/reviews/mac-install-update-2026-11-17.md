# 新 Mac 安装与每日空闲更新验收

日期：2026-11-17。规格：[其他 Mac 安装与每日空闲更新](../specs/mac-install-update.md)。基线8460b0；实现b3e52ac，审查修复45e30aa。

## 交付

- GitHub发行附统一入口install-pwiki.sh、标准库管理器pwiki-setup.py、各自SHA256及mac-install.md。客户端独立Vault，Mini仅媒体服务；旧生产服务未被新安装器接管。
- 在已有Homebrew/正常系统权限前提下补齐客户端工具、抓取环境和薄skill；复用固定官方LLM Wiki下载/校验安装器。账号、API、项目注册仍在目标机正常配置。
- 当前用户launchd每日检查稳定发行，每小时重试空闲。安装器独占锁与CLI共享命令锁防止并发切换，worker每轮释放；队列中仍有可执行任务时延后。代码维护实例不由发行更新接管。
- 发行外层/内部哈希、原文转换预检、受控切换、入口失败回退、中断事务恢复、旧版保留。配置、令牌、原件和任务不随更新重建。依赖/上游固定版本或major变化保留旧版并要求独立环境验收。

## 自动验证

- Node完整回归171通过，含新增最小PATH下npm风格Codex入口的外部进程测试。
- Python既有完整回归91项通过（3项浏览器环境检查跳过）；采用项目忽略目录内隔离Python3.12/venv和固定抓取依赖，未修改系统Python。
- 独立发行安装/更新20项通过，其中新增10项覆盖：实际包升级与重放、私有配置/原件保留、共享运行锁/排队延后、每日计划/检查间隔、统一入口保留Mini配置与既有应用/skill、哈希篡改及激活失败保留旧版、切换期间拒绝新命令、中断后恢复、拒绝依赖变化绕过、拒绝旧安装器降级、稳定Node符号入口和最小PATH。
- 标准与规格分别独立审查，四项发现均修复并复核无剩余阻塞：旧环境重装绕过依赖检查、过期候选并发降级、后台Codex缺Node PATH、Homebrew版本目录被清理后的Node入口失效。

## 实机与发行边界

原LLM Wiki固定官方安装器的实机证据见[独立发行0.9.1](independent-distribution-2026-11-16.md)；本次统一入口的离线重放测试使用已有应用，不冒充新账号登录与新Mac整机验收。媒体服务和真实平台采集沿用既有版本能力，未在本次对另一台用户Mac重新验收。Homebrew安装依赖的完整新Mac流程未在空白机器上执行。

## 发行下载与实际启动项

- [0.10.0发行](https://github.com/liunoly-design/Personal_wiki/releases/tag/distribution-v0.10.0)，源码c31a79b26bf820fccc456740cf0d0d44cef8352e；[GitHub Actions](https://github.com/liunoly-design/Personal_wiki/actions/runs/44007040100)成功。tag未移动。
- 21项发行资产已从GitHub实际下载，GitHub digest及SHA256SUMS全部匹配。4个tar包的内部清单、来源提交、source_dirty=false及文件哈希全部核验通过。
- 从官方已发布0.9.1 CLI包在隔离prefix安装，使用新下载的pwiki-setup.py及0.10.0包实际升级。私有配置逐字一致，合成Vault原件不变；升级后的CLI中文转换达到converted并核对完整正文，新pwiki-update重放返回up_to_date。
- 使用下载包的更新管理入口临时注册独立label的真实当前用户launchd任务；后台pwiki-update实际输出not_due（已于本次检查，不再次联网），随后正常移除，launchctl确认任务已卸载。本机原生产launcher、worker、配置和正式Vault未改动。
- 私有下载/测试产物与回执位于项目忽略目录，不随Git或Release发布。上述隔离本机证据不替代其他Mac的首次登录、真实模型入库及平台采集验收。
