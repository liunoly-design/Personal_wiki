# X 回复关系与串文获取：只读证据

日期：2026-11-16。范围：项目官方文档/源码与获授权公开样本的只读元数据请求。没有登录、读取账户 Cookie、修改采集代码或运行状态；不在本文保存用户的原链接、正文、图片、作者身份和回复内容。

## 可复用接口

FxEmbed 官方当前提供 v2 公开接口：单帖 `/2/status/{id}`、串文 `/2/thread/{id}`、会话 `/2/conversation/{id}`。官方机器可读规范位于 [GitHub OpenAPI](https://github.com/FxEmbed/FxEmbed/blob/main/docs/specs/fxtwitter-openapi.json)，线上也提供 `/2/openapi.json`；v1 与 v2 的字段形状不同，不能混用。[官方 API 介绍](https://github.com/FxEmbed/FxEmbed/blob/main/docs/src/content/docs/api/introduction.mdx)

| 对象 | 可验证字段 | 注意事项 |
| --- | --- | --- |
| v2 单帖 | `status.id`、`status.author.id`、`status.replying_to`、`status.quote`、正文/媒体/文章对象 | `replying_to` 是可为 null 的对象；父帖 ID 在 `replying_to.status`，不是 v1 的独立 `replying_to_status` 字段 |
| v2 串文 | 外层 `code/status/thread/author`；串文项保留帖子身份及回复目标 | `thread=null` 与取得非空串文数组不同；数组中可能有 tombstone，必须先判断类型 |
| v2 会话 | `thread` 与 `replies` 分开；`cursor.bottom` 为回复分页游标 | 同作者回复可能是在回答别人，不能只按作者相同就归入自回复串文；会话回复页不等于原作者串文 |
| X 长文章 | `status.article.content.blocks`、`entityMap`、`media_entities` | 普通 `status.text` 可能只有文章标题/链接；应区分完整文章块与预览 |

以上结构以官方 OpenAPI 的 `SocialThread`、`SocialConversation`、`APIReplyingTo`、`APITwitterStatus` 为依据。

## 官方串文实现的边界

官方 [conversation.ts](https://github.com/FxEmbed/FxEmbed/blob/main/packages/atmosphere/src/providers/twitter/conversation.ts) 的当前源码提供以下证据：

- `filterBucketStatuses`（读取时第 803–808 行）按作者稳定 ID 过滤。
- `findNextStatus`（第 746–765 行）按 `in_reply_to_status_id_str` 关联下一条，遇同父帖多个分支按时间线顺序选择一条。
- 串文遍历（第 1128–1200 行）跟随作者回复关系，并在已有条目走到末端时尝试游标；祖先也有对应回溯。
- 处理保留 tombstone；从删除或不可用节点不能推导出已取得完整正文。
- 会话输出（第 1340–1529 行）将祖先链和其他回复分开，并暴露回复的 bottom cursor。
- 文章富化（第 369–412 行）在初始文章仅有预览而缺少正文块时再取完整文章字段。

这是比“页面没有回复字段，因此永远无法判断”更强的来源证据。但 v2 响应没有独立的全局完整性证明字段；上游受限、分支选择、删除内容或分页失败时，不能声称数学上证明所有隐藏帖子都已穷尽。实施应保留提供方、取得的链、明确父子关系及限制。

## 获授权样本的实际结果

本次对同一公开目标只读请求得到：

- `/2/status`、`/2/thread`、`/2/conversation` 均实际返回过 HTTP 200 / code=200。
- `/2/thread` 返回包含目标自身的一条串文；目标的 `replying_to` 字段实际存在且为 null。这能补充“平台未提供回复关系”这个具体缺口，不是从缺字段猜测根帖。
- 目标包含长文章对象，实际取得 89 个正文块及 entityMap；普通 text 字段仅为短标题/链接，不应单独充当全文。
- `/2/conversation` 初页返回 33 个回复条目，其中有 13 个同作者回复，但它们指向的是其他用户的评论，而非同作者自回复链。它们不应自动归档为串文。
- 会话后续三页返回空回复数组但仍有变化的 bottom cursor；本轮有界调查止于此，不能将空页解释为分页已穷尽，也不需要为了归档正文收集其他评论。
- 一种 HTTP 客户端默认请求出现 HTTP 错误，使用带应用 User-Agent 的 urllib 公开 GET 多次成功。该差异只作为本轮观察，尚未确定错误原因；实施应有明确超时/有限重试，不能宣称所有客户端永久可用。

## 建议的接入规则，供主线程实现与测试

1. 获取并保留原始 v2 串文响应证据，验证 HTTP 与业务 code、目标 ID、类型、作者 ID，以及目标确实在取得的链中。
2. 按稳定作者身份与明确父子关系构建同作者连续链；父子指向其他作者的评论时不扩大归档范围。引用帖单独按引用关系处理，不能因正文提到某链接就当作引用结构。
3. 显式 null 的回复目标可与非空串文结果共同作为本次观测的上下文证据；缺字段、thread=null、目标不在链、tombstone、冲突身份或已知未取得父帖继续保留缺口。
4. 不能把串文数组长度为一或没有 quote 键单独当作全局不存在其他内容的证明。保留实际获取方式及来源限制，避免去掉所有完整性检查。
5. 对长文章核验完整块和媒体映射，不能用预览填充全文。现有 HTML 已取得正文时可用 API 只补来源/关系证据，原件继续保持不变。

## Twikit 的替代边界

[Twikit 官方文档](https://twikit.readthedocs.io/en/latest/twikit.html)提供 `Tweet.in_reply_to`、`quote`、`replies`、`reply_to`。其 [`get_tweet_by_id` 源码](https://twikit.readthedocs.io/en/latest/_modules/twikit/client/client.html)解析 TweetDetail，并在 SelfThread 时间线模块提供 thread。此路径通常依赖已授权登录/Cookie；本轮没有登录或调用账户接口，因此只确认能力定义，未验证该样本在 Twikit 下可取。

本轮足够支持给现有 X 获取器增加公开关系证据的候选方案；不意味着新处理器、测试或真实入库已经完成。
