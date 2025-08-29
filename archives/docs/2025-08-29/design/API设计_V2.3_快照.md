# API 设计_V2.3

> 更新公告（2025-08-23）
> - 服务基址：本地开发 http://127.0.0.1:8230/api/v2.3-preview（预览命名空间）。
> - 补充接口一览与示例；新增 PowerShell JSON 提交指引。
> - 说明预览期与 OpenAPI 契约的差异点与对齐计划。
> - **【NEW】新增 /agents/run 多智能体调度端点与示例。**

- 版本：V2.3
- 文档状态：v0.4（加入多智能体接口）
- 作者：星河
- 最近修订：2025-08-23

## 1. 设计约束（预览期）
- 协议：REST/JSON；UTF-8；Content-Type: application/json。
- 头部：可选 X-Request-Id；写操作预留 Idempotency-Key（代码将对齐）。
- 错误码：4xx 客户端错误（含 422 校验失败），5xx 服务端错误；详见 OpenAPI。

## 2. 服务基址与命名空间
- 本地开发：http://127.0.0.1:8230/api/v2.3-preview
- 生产/预览：以 OpenAPI servers 为准（已包含 /api/v2.3-preview）。

## 3. 接口一览（与当前实现一致）
- GET / → 服务元信息（无前缀）
- GET /health → 健康检查（无前缀）
- GET /consciousness/state
- POST /consciousness/state
- POST /reasoning/plan
- POST /execution/act
- POST /cloud/consent
- DELETE /cloud/consent（query: user_id）
- GET /cloud/status（query: user_id）
- POST /memory/sync
- GET /memory/export
- **POST /agents/run（多智能体任务调度）【NEW】**

以上路径均相对于基址 /api/v2.3-preview（根与健康检查除外）。

## 4. 示例（PowerShell 与 curl）
- 计划生成（reasoning/plan）：
  curl -s -X POST "http://127.0.0.1:8230/api/v2.3-preview/reasoning/plan" \
    -H "Content-Type: application/json" \
    -d '{ "goal": "实现最小规划", "constraints": [], "max_steps": 3 }'

- 执行动作（execution/act）：
  curl -s -X POST "http://127.0.0.1:8230/api/v2.3-preview/execution/act" \
    -H "Content-Type: application/json" \
    -d '{ "action": "echo", "params": { "k": "v" } }'

- 云授权创建（cloud/consent）：
  curl -s -X POST "http://127.0.0.1:8230/api/v2.3-preview/cloud/consent" \
    -H "Content-Type: application/json" \
    -d '{ "user_id": "u-001", "consent": true, "scopes": ["dialog"] }'

- 云授权状态（cloud/status）：
  curl -s "http://127.0.0.1:8230/api/v2.3-preview/cloud/status?user_id=u-001"

- 记忆同步（memory/sync）：
  curl -s -X POST "http://127.0.0.1:8230/api/v2.3-preview/memory/sync" \
    -H "Content-Type: application/json" \
    -d '{ "items": [ { "content": { "type": "note", "text": "hello" } } ] }'

- 记忆导出（memory/export）：
  curl -s "http://127.0.0.1:8230/api/v2.3-preview/memory/export"

- 多智能体任务（agents/run）【NEW】：
  curl -s -X POST "http://127.0.0.1:8230/api/v2.3-preview/agents/run" \
    -H "Content-Type: application/json" \
    -d '{
      "task_type": "breadth_first_research",
      "query": "2024-2025年AI多智能体研究的关键进展与开源实现",
      "max_agents": 3,
      "budget": { "time_limit": 30, "cost_limit": 0.1 },
      "quality_threshold": 0.7
    }'

提示：如返回 422，多为 JSON 属性名缺少双引号或转义不当，请对照示例修正。

## 5. PowerShell JSON 提交指引
- 建议外层使用单引号，JSON 内部属性名使用双引号：
  -H "Content-Type: application/json" -d '{ "key": "value" }'
- 或使用 Here-String：
  $body = @'{
    "key": "value"
  }'@
  curl -s -X POST url -H "Content-Type: application/json" -d $body

## 6. 预览期与契约差异（将对齐）
- cloud/consent：请求/响应尚未完全符合 Consent 模式（OpenAPI 定义），将调整为标准字段（id, userId, status…）。
- cloud/status：将对齐为 { active, expiresAt, lastJob }。
- memory/sync：将对齐为 { clientCommitId, items } → 返回 202 + CloudSyncJob。
- memory/export：响应字段将对齐为 { downloadUrl, expiresAt, checksum }。
- **agents/run：将对齐为 Job + Result 模式，包含jobId、progress、costBreakdown、confidence等字段。**

OpenAPI 契约文件：docs/requirements/api/openapi_v2.3-preview.yaml。