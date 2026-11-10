# TDD: AI 识别配置系统级化与固定 JSON 契约（V1）

- 文档版本: v1.1
- 创建日期: 2026-04-10
- 文档类型: 测试设计文档（TDD）
- 关联 PRD: `docs/PRD/2026-04-10-AI识别配置系统级化与测试闭环PRD.md`
- 关联 FD: `docs/FD/2026-04-10-AI识别配置系统级化与固定JSON契约FD.md`

---

## 1. 测试目标

本专项测试要证明：

1. AI 配置由系统设置统一维护（非 group）。
2. 验证码提取链路满足“规则快路径优先，AI 按需触发”。
3. AI 输入与输出均满足固定 JSON 契约。
4. AI 输出异常时，系统可快速回退且不阻塞主流程。
5. Web 与 External 两条链路行为一致。

---

## 2. 分层测试策略

| 层级 | 目标 | 建议文件 | 重点 |
|---|---|---|---|
| A. settings Repo/API | 系统级 AI 配置读写 | `tests/test_settings_verification_ai_config.py` | 加密存储、脱敏回显、缺项校验 |
| B. groups API | group 去 AI 化兼容 | `tests/test_groups_verification_policy_api.py` | length/regex 正常，AI 字段兼容窗口 |
| C. AI 契约 | 固定 JSON 输入输出 | `tests/test_verification_ai_json_contract.py` | schema_version、字段完整性、类型校验 |
| D. Web 提取链路 | 规则优先 + AI 回退 | `tests/test_extract_verification_group_policy.py` | 规则命中不触发 AI、AI 异常不阻塞 |
| E. External 提取链路 | 与 Web 一致 | `tests/test_external_verification_group_policy.py` | 同口径、同错误语义 |

---

## 3. 核心测试矩阵

### 3.1 配置闭环矩阵

| 场景 | 输入 | 预期 |
|---|---|---|
| C-01 | AI 关闭 | 不要求 URL/APIKey/Model |
| C-02 | AI 开启 + 三项齐全 | 保存成功 |
| C-03 | AI 开启 + 缺 URL | 明确配置错误 |
| C-04 | AI 开启 + 缺 APIKey | 明确配置错误 |
| C-05 | AI 开启 + 缺 Model | 明确配置错误 |

### 3.2 固定 JSON 契约矩阵

| 场景 | 类型 | 预期 |
|---|---|---|
| J-01 | AI 输入 JSON 字段齐全 | 通过 |
| J-02 | AI 输入缺 schema_version | 失败 |
| J-03 | AI 输出 JSON 合法 | 通过 |
| J-04 | AI 输出非 JSON | 回退规则结果 |
| J-05 | AI 输出字段类型错误 | 回退规则结果 |

### 3.3 性能/加速行为矩阵

| 场景 | 输入 | 预期 |
|---|---|---|
| P-01 | 规则可命中验证码 | 不触发 AI（快路径） |
| P-02 | 规则未命中，AI 可命中 | 返回 AI 结果 |
| P-03 | 规则未命中，AI 超时/异常 | 快速回退并返回稳定错误或空结果 |

---

## 4. 关键用例（建议）

1. `test_settings_ai_config_save_and_masked_read`
2. `test_settings_ai_enabled_requires_all_fields`
3. `test_groups_payload_ai_fields_do_not_drive_runtime`
4. `test_ai_input_json_contract_fixed_schema`
5. `test_ai_output_json_contract_validation`
6. `test_web_extract_rule_hit_skips_ai`
7. `test_web_extract_ai_invalid_json_fallback_rule`
8. `test_external_extract_ai_invalid_json_fallback_rule`

---

## 5. Mock 约束

1. 禁止真实 AI 网络调用。
2. AI 客户端统一 mock，输出固定测试夹具。
3. 需要显式覆盖：合法 JSON、非 JSON、类型错误 JSON。

---

## 6. 通过标准

1. 配置、契约、回退、一致性四类矩阵全部通过。
2. 关键回归（group 规则策略、web/external 提取）不退化。
3. 全量测试通过后方可结束专项。

---

## 7. 执行结果回填（2026-04-10）

1. settings 配置与安全行为测试：通过
2. 固定 JSON 契约测试：通过
3. Web/External 快路径与回退一致性测试：通过
4. 全量回归：`python -m unittest discover -s tests -v` → `Ran 946 tests in 206.872s`，`OK (skipped=7)`

---

## 8. 人工联调反馈回填（2026-04-11）

1. 人工确认通过：
   - 完整配置保存成功（系统级 AI 设置）。
   - 分组字段范围正确（仅 length/regex）。
   - 长度容错输入可保存且被规范化。
   - Web 提取链路可用。
2. 人工未直接覆盖项：
   - AI 异常快速回退（场景构造成本较高，采用自动化用例覆盖）。
   - External 提取人工验证（采用自动化回归覆盖）。
3. 自动化补充验证（本会话复跑）：
   - `tests.test_settings_verification_ai_config`
   - `tests.test_verification_ai_json_contract`
   - `tests.test_external_verification_group_policy`
   - 结果：`Ran 8 tests ... OK`

---

**文档结束**
