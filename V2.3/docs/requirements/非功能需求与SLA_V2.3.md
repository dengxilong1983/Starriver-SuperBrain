# 非功能需求与SLA_V2.3

> 更新公告（2025-08-22）
> - 新增云端同步 SLA、隐私与安全以及可观测性等非功能需求占位。

> v0.2 补充（2025-08-21）
> - 明确性能、可靠性、恢复力、安全合规、可观测性、可维护性等阈值与度量；定义 SLO/SLA、告警门限与演练计划。

- 版本：V2.3
- 文档状态：v0.2（初版完成）
- 作者：星河
- 审批：熙龙（待审批）
- 最近修订：2025-08-23

## 1. 性能指标（Performance）
- 接口 P95 延迟上限：
  - GET /cloud/status ≤ 200ms
  - POST /cloud/consent ≤ 500ms
  - POST /memory/sync ≤ 1s（每 100 条 changes）
  - POST /memory/export 启动 ≤ 300ms；导出完成 TTFB ≤ 2s（下载）
- 吞吐与容量：
  - 同步：支持 100 并发用户，峰值 1k rps（集群）无明显退化
  - 队列：单租户待同步队列上限 50k 条，队列深度>80% 触发扩容
- 资源与成本：
  - CPU 使用率目标 < 70%（P95）；内存 < 75%（P95）
  - 单用户日均存储配额：匿名化记忆≤1GB；导出单次≤5GB

### 1.1 AGT 专项性能指标（/agents/*）
- 延迟（P95）：
  - POST /agents/run（调度响应）≤ 2s（返回 taskId）
  - GET /agents/tasks/{task_id}/status ≤ 300ms
  - GET /agents/tasks/{task_id}/result ≤ 1s（≤2MB 结果）
  - GET /agents/tasks/{task_id}/trace ≤ 1s（trace≤5MB）
- 并发与容量：
  - 预览期每租户并发运行中的 AGT 任务 ≤ 20；单任务 maxAgents ≤ 5
  - 单任务墙钟上限（budgetSeconds）默认 ≤ 900s；超限强制 timeout
- 预算与成本：
  - 每任务 budgetTokens 可配置（默认 0 表示不限额预览），成本明细需在 result 中返回
  - 取消任务应在 3s 内释放 ≥95% 资源

## 2. 可靠性与可用性（Reliability & Availability）
- 月度 SLO：
  - 授权/状态接口（/cloud/*）：99.9%
  - 同步与导出接口（/memory/*）：99.5%
  - 多智能体接口（/agents/*，预览）：≥ 99.0%
- 错误预算：
  - 以 30 天为周期，结合烧蚀速率（burn rate）告警：
    - 14.4× 烧蚀（1h 窗口）触发 Sev-1
    - 6× 烧蚀（6h 窗口）触发 Sev-2
- 恢复力：
  - 任务恢复：Worker 故障或中断后 60s 内自动重试或迁移；最多 3 次指数退避（1m/3m/5m）
  - 取消/回滚：取消操作幂等；任务状态允许 in_progress→{canceled, timeout, failed} 的单向流转
  - 配置热更新：AgentConfig 更新 ≤ 10s 生效，失败自动回滚上一版本

## 3. 安全与合规（Security & Compliance）
- 身份与权限：
  - /agents/* 仅允许经鉴权用户访问；每个请求需校验租户隔离与 RBAC
- 数据最小化与脱敏：
  - AgentTrace 默认脱敏（PII/密钥/令牌）；引用（citations）仅保留必要元数据
  - Trace 存储上限 5MB/任务，默认保留 7 天（或达到上限择小）
- 出口与工具访问控制：
  - 工具与外网访问采用允许名单（allowlist）与速率限制，禁止本地文件/内网探测
  - 防注入：提示词注入检测与降权策略；高风险来源自动隔离
- 合规：
  - 支持数据主体访问/删除请求（7 天内完成）；关键操作审计不可篡改

## 4. 可观测性与运维（Observability & Ops）
- 指标（Metrics）：
  - agent_tasks_active, agent_tasks_total{status}
  - agent_task_latency_ms{phase="schedule|run_total|result_fetch|trace_fetch"}
  - agent_task_cost_tokens_sum, agent_task_budget_exceeded_total
  - agent_cancel_success_total, agent_cancel_latency_ms
  - agent_trace_size_bytes, agent_citation_count, agent_quality_score
- 日志与链路：
  - 全链路传递 X-Request-Id/X-Task-Id；重要操作以结构化日志落盘
  - 采样率：默认 10% 记录详细轨迹（可配置），错误与超时 100% 采集
- 告警门限：
  - /agents/* P95 超阈值连续 5 分钟 → Sev-2；错误率>1%（5 分钟）→ Sev-1
  - 任务取消超时>3s（5 分钟窗口 P95）→ Sev-2；预算超限事件>0 → Sev-2

## 5. 可维护与可扩展（Maintainability & Scalability）
- 模块化与弹性：
  - Orchestrator-Worker 解耦，Worker 可水平扩展；健康检查周期 ≤ 30s
- 配置与灰度：
  - Feature Flag 控制多智能体开关；逐步放量（1%→10%→50%→100%）
- 向后兼容：
  - API 遵循 SemVer，弃用提前 ≥ 90 天公告与迁移文档

## 6. 合规与可访问性（Compliance & Accessibility）
- 可访问性：
  - 符合 WCAG 2.1 AA 级（前端界面），关键流程提供键盘操作与语义标签
- 合规：
  - 支持数据主体访问请求（SAR）与删除请求；7 天内完成

## 7. 验收门禁（Quality Gates）
- 发布前：
  - 性能压测满足 P95 指标；稳定性 24h 无致命错误
  - 安全扫描 0 高危；合规检查通过
  - AGT 门禁：
    - /agents/run 与状态/结果/取消/轨迹端到端通过率 100%（基本路径）
    - 引用准确率 ≥ 96%；结果完整性 ≥ 99.5%；配置更新验证 100%
- 上线后：
  - 前 72 小时开启增强监控与回滚预案

## 8. 变更记录
- 2025-08-20：新增占位（星河）
- 2025-08-21：v0.2 完成阈值、SLO/SLA 与告警策略（星河）
- 2025-08-23：v0.3 新增多智能体（AGT）专项性能/SLO、安全/合规、可观测性与质量门禁（星河）