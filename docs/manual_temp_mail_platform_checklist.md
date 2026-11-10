# 临时邮箱能力二期平台化手工验收清单

- 文档目的: 为 temp-mail 二期平台化提供最小人工验收闭环
- 关联验证记录: `verification.md`

## 1. 环境准备

1. 在设置页确认 `temp_mail_enabled`、`temp_mail_provider`、`temp_mail_api_key`、域名配置有效。
2. 准备一个普通 Outlook/IMAP 邮箱账号，确认 external 普通邮箱路径可读。
3. 准备一组可用的 external `consumer_key` / `task_id` 调用参数。

## 2. 用户侧验收

1. 访问临时邮箱页面并创建邮箱，确认返回地址、前缀、域名与 UI 列表正常显示。
2. 打开邮箱消息列表并查看详情，确认详情接口和页面展示正常。
3. 对同一邮箱执行验证码提取与验证链接提取，确认返回结构稳定。
4. 删除单封邮件、清空邮箱、删除邮箱，确认页面状态与后端行为一致。

## 3. 任务侧验收

1. 调用 `POST /api/external/temp-emails/apply`，确认返回 `task_token`、`email`、`status`。
2. 用 `GET /api/external/messages*`、`/api/external/verification-*`、`/api/external/wait-message` 读取任务邮箱，确认无需新路径。
3. 调用 `POST /api/external/temp-emails/{task_token}/finish` 后再次读取，确认返回 `TASK_FINISHED` 或对应终态拒绝。
4. 取消 probe 或等待终止后，确认返回 `PROBE_CANCELLED` 等稳定终态。

## 4. 普通邮箱回归

1. 用普通 Outlook/IMAP 邮箱调用 `/api/external/messages*` 与 `/api/external/verification-*`，确认行为未受 temp-mail 改造影响。
2. 确认 temp mailbox 与普通邮箱授权边界正常，普通邮箱仍走 `allowed_emails` 语义。

## 5. 通过标准

以下条件同时满足即可判定人工验收通过：

1. 用户侧和任务侧都未出现新增路径或 provider 泄漏。
2. finish、wait、probe 终态稳定。
3. `/api/settings` 可读写正式 `temp_mail_*` 字段，空字符串不会误清空正式 API key。
4. 普通 Outlook/IMAP external 链路无回归。
