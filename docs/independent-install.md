# Wiki 独立安装与配置回退

范围：[SPEC](specs/independent-install.md)／[#34](https://github.com/liunoly-design/Personal_wiki/issues/34)、任务[#35](https://github.com/liunoly-design/Personal_wiki/issues/35)。本入口安装Wiki插件，不要求PGTD或Apple权限。

## 准备

已有Node24+、OpenClaw、Python3.11+及本仓库capture依赖、Codex CLI、nashsu。先由用户在nashsu初始化自己的新库并注册它，关闭该库重复自动摄取和向量搜索，打开本地API；先配置自己的飞书账号与入口路由。安装器不创建知识正文、不下载依赖、不登录、不自动启动或重启服务。

设置JSON放在代码/Vault外的私有目录，建议权限0600；不得放密钥。宿主账号凭据与模型认证仍由OpenClaw管理。

```json
{
  "hostConfigPath": "/absolute/openclaw/openclaw.json",
  "nashsuStatePath": "/absolute/nashsu/app-state.json",
  "vault": "/absolute/my-library",
  "stateDir": "/absolute/private/wiki",
  "python": "/absolute/venv/bin/python",
  "codexBinary": "/absolute/bin/codex",
  "openclawBinary": "/absolute/bin/openclaw",
  "openclawPackageDir": "/absolute/node_modules/openclaw",
  "accountId": "own",
  "entryAgentId": "my-entry",
  "wikiAgentId": "my-knowledge",
  "allowedSenderIds": ["ou_REPLACE"],
  "allowedConversationIds": ["oc_REPLACE"],
  "flashModel": "gemini-flash-latest",
  "compilerModel": "gpt-6-sol"
}
```

使用实际本机绝对路径与本人账号范围。nashsuStatePath可省略，默认应用标准位置；非默认安装建议显式指定openclawPackageDir。所选模型由用户配置，版本探测不验证模型认证/额度。

入口路由须已有bindings记录，channel为feishu、accountId为所选账号、agentId为entryAgentId。安装器保留既有路由；只创建缺失的所选Agent配置，不复制另一Agent的凭据。Google认证需由用户为wikiAgentId配置，后续读取该Agent的唯一Google profile。已有的活动Wiki安装不会被此入口覆盖，需另做迁移。

## 执行与核对

```sh
node scripts/wiki-setup.mjs check --settings /private/settings.json
node scripts/wiki-setup.mjs check --settings /private/settings.json --api
node scripts/wiki-setup.mjs install --settings /private/settings.json
node scripts/wiki-setup.mjs rollback --settings /private/settings.json --receipt /private/wiki/installations/install-UUID.json
```

基础check只读文件并运行版本/依赖检查；--api只向本机nashsu读索引，不生成内容。失败项status为blocked。authentication/quota及真实飞书验收标为not_verified。

install在私有状态复制独立代码副本，保存原宿主配置字节与安装凭据，暂存后用真实OpenClaw验证配置/插件加载，再原子替换并复核。重复相同设置及源码返回existing；发布副本被改动则拒绝复用。既有其他插件/allow策略/绑定保留。成功不自动重启Gateway。

rollback仅恢复原宿主配置，保留发布副本、状态、Vault、附件和认证。宿主被后续编辑则拒绝回退，需人工核对；不得强行覆盖。安装失败或中断的凭据保留在stateDir/installations，先核对宿主配置与凭据，不能盲目重装。未知并发变更保持现场。

排他锁位于hostConfigPath加.wiki-setup.lock。进程意外退出可能保留锁：先核实进程不再运行、原配置/候选/凭据状态，再由用户删除这一把锁，禁止清理整个状态或Vault。配置/安装元数据路径不接受符号链接；macOS的/var路径需使用真实/private/var路径。

最终配置基线检查在临时文件写完后、同步替换前执行；暂存及凭据写入期间的外部编辑会被拒绝覆盖。完全排除其他进程在检查与系统替换之间的竞争，需要它们遵守同一把锁。因此执行安装/回退时暂停其他宿主配置编辑器；该约束不影响知识正文并发保护。

## 验收边界

自动测试验证独立配置、原件与其他插件保护、重复、缺依赖、失败回退、并发/符号链接及所选模型Agent。真实OpenClaw CLI隔离脚本：

```sh
WIKI_ACCEPTANCE_PYTHON=/absolute/existing/venv/bin/python \
WIKI_ACCEPTANCE_CODEX=/absolute/bin/codex \
WIKI_ACCEPTANCE_PACKAGE_DIR=/absolute/node_modules/openclaw \
node scripts/manual/independent-install-acceptance.mjs
```

该脚本使用合成飞书账号与新临时库，不调用模型、不发送消息、不重启网关。通过代表本机隔离安装与配置回退通过；朋友新Mac、模型认证/费用、真实nashsu新库读搜、真实飞书收集及资料备份恢复须分别验收。
