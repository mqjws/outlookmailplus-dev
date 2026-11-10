# 注册 Pool 人工测试清单

## 目标

验证“通过页面注册 Outlook 账号后，该账号能够进入邮箱池并可被 `/api/external/pool/*` 正常领取”的完整链路。

## 当前检查结论

当前代码已切换为“显式加入池”模式：

1. 前端存在“`🔑 注册`”按钮，可触发 OAuth 获取 Token。
2. 导入弹窗新增“`导入后加入邮箱池`”复选框。
3. 勾选时，新导入的 Outlook/IMAP 账号会写入 `pool_status='available'`。
4. 不勾选时，账号保持池外，`pool_status` 为 `NULL`。

结论：当前版本不再采用“注册即自动入池”，而是由用户在导入时显式决定是否加入 Pool。

## 代码定位

- 前端注册入口：
  - `templates/index.html`
  - `static/js/features/groups.js`
  - `static/js/main.js`
- 账号新增入库：
  - `outlook_web/repositories/accounts.py`
- 池领取条件：
  - `outlook_web/repositories/pool.py`
- 数据库字段默认值：
  - `outlook_web/db.py`

## 测试前置条件

1. 本地启动项目：

```bash
python start.py
```

2. 准备一个可用的 Outlook OAuth 授权流程。
3. 准备至少一个普通分组，不使用“临时邮箱”系统分组。
4. 登录系统后台。

## 人工测试用例

### RTP-001 注册按钮可见性

步骤：

1. 打开“账号管理”页面。
2. 选择任意非“临时邮箱”的分组。
3. 观察账号面板右上角是否显示“`🔑 注册`”按钮。

预期结果：

1. 普通分组显示“`🔑 注册`”按钮。
2. 选择“临时邮箱”分组时该按钮隐藏。

### RTP-002 OAuth 获取 Token

步骤：

1. 点击“`🔑 注册`”按钮。
2. 获取授权链接并完成微软授权。
3. 将回调完整 URL 粘贴回弹窗。
4. 点击“换取 Token”。

预期结果：

1. 能成功换取 `refresh_token`。
2. 页面自动回到“导入账号”弹窗。
3. 输入框被预填为 `邮箱----密码----client_id----refresh_token` 格式。

### RTP-003 注册 Outlook 账号

步骤：

1. 将预填内容中的占位邮箱、密码替换为真实值。
2. 点击导入。
3. 等待导入成功提示。
4. 在当前分组列表中确认账号出现。

预期结果：

1. 页面提示导入成功。
2. 分组账号列表可见该 Outlook 账号。

### RTP-004 注册后是否进入 Pool

步骤：

1. 完成 RTP-003。
2. 打开数据库，执行以下 SQL：

```sql
SELECT email, pool_status, provider, account_type
FROM accounts
WHERE email = '刚注册的邮箱';
```

预期结果：

1. 如果勾选“导入后加入邮箱池”，这里应返回 `pool_status = 'available'`。
2. 如果未勾选，这里应返回 `pool_status = NULL`。

### RTP-005 对外池领取验证

步骤：

1. 在设置中开启 `pool_external_enabled`。
2. 准备一个具备 `pool_access=true` 的 API Key。
3. 调用：

```bash
curl -X POST http://127.0.0.1:5000/api/external/pool/claim-random ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: <your-key>" ^
  -d "{\"caller_id\":\"manual_test\",\"task_id\":\"rtp005\"}"
```

2. 观察返回结果。

预期结果：

1. 如果注册账号已进池，应返回 `success=true`，并包含该账号的 `account_id`、`email`、`claim_token`。

当前验证重点：

1. 勾选加入池时，应能领取到刚注册的账号或至少使池内 `available` 数量增加。
2. 不勾选时，即使注册成功，也不应被池领取到。

### RTP-006 领取后状态流转

步骤：

1. 先确保池内存在一个 `available` 账号。
2. 调用 `/api/external/pool/claim-random` 领取。
3. 调用 `/api/external/pool/claim-complete`，分别传入：
   - `success`
   - `verification_timeout`
   - `provider_blocked`
   - `credential_invalid`
   - `network_error`

预期结果：

1. 状态分别流转到：
   - `used`
   - `cooldown`
   - `frozen`
   - `retired`
   - `available`

## 已确认的自动化基线

已执行：

```bash
python -m unittest tests.test_external_pool tests.test_external_pool_e2e tests.test_pool tests.test_pool_flow_suite -v
```

结果：

1. 池相关服务层、external pool HTTP 用例与 flow suite 用例全部通过。
2. 说明“池本身的 claim/release/complete/stats 逻辑”当前没有明显回归。
3. 但这些测试主要覆盖“已有池内账号”的流转，不覆盖“注册后进入池”。

## 自动化补充

本轮已补充 API 级回归思路：

1. 默认导入不入池。
2. 勾选 `add_to_pool=true` 时进入 `available`。
3. `provider=auto` 的 Outlook/IMAP 导入同样支持该开关。
