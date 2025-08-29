# Active 语义审计与迁移策略_V2.3

> 版本：v1.1  
> 创建日期：2025-01-28  
> 更新日期：2025-01-28  
> 状态：迁移执行完成，监控中  

## 1. 审计背景与目标

### 1.1 问题发现
在星河超脑 V2.3 文档体系中，`active` 作为状态枚举值存在**语义不一致**的问题：

1. **合法场景**：`Consent.status ∈ [active, revoked, pending]`，表示"已激活/已撤销/待处理"
2. **问题场景**：`agent_assignments[].status: "active"`，误用于表示"执行中"状态

### 1.2 审计目标
- 识别所有误用 `active` 表示"执行中"的场景
- 提供统一的状态枚举迁移方案
- 确保契约一致性与语义清晰性
- 建立状态枚举治理规范

## 2. 审计发现

### 2.1 文档分布
经全面扫描，`active` 出现在以下文档中：

| 文档 | 位置 | 语义 | 评判 |
|------|------|------|------|
| `接口需求清单_V2.3.md` | `agent_assignments[].status: "active"` | 表示"执行中" | ❌ 误用 |
| `openapi_v2.3-preview.yaml` | `Consent.status: [active, revoked, pending]` | 表示"已激活" | ✅ 合法 |
| `需求规格说明书_V2.3.md` | agents.active.count 监控指标 | 表示"活跃数量" | ❌ 待澄清 |
| `验收标准与测试策略_V2.3.md` | GET /agents/status 描述 | 引用问题文档 | ❌ 连带影响 |

### 2.2 具体问题场景

#### 问题1：agent_assignments 状态枚举混乱
```json
// 当前（错误）
"agent_assignments": [
  {
    "agent_id": "lead_researcher_01",
    "role": "LeadResearcher", 
    "status": "active",        // ❌ 应为 "in_progress"
    "subtask": "任务分解与协调"
  },
  {
    "agent_id": "search_agent_01", 
    "role": "SearchAgent",
    "status": "pending",       // ✅ 正确
    "subtask": "学术文献检索"
  }
]
```

#### 问题2：监控指标语义不清
```yaml
# 当前（模糊）
agents.active.count    # ❌ active 含义不明确
```

## 3. 迁移策略

### 3.1 状态枚举标准化

#### 3.1.1 Agent 任务/分配状态（推荐）
```yaml
# 标准枚举：agent_assignments[].status
enum: [pending, in_progress, completed, failed, canceled]

# 语义定义
- pending: 已分配但未开始
- in_progress: 正在执行  
- completed: 成功完成
- failed: 执行失败
- canceled: 已取消
```

#### 3.1.2 保留 Consent 的 active（不变）
```yaml
# Consent.status 保持不变
enum: [active, revoked, pending]
- active: 授权已激活
- revoked: 授权已撤销  
- pending: 授权待处理
```

### 3.2 监控指标澄清
```yaml
# 修正前（模糊）
agents.active.count

# 修正后（明确）
agents.in_progress.count    # 执行中的 Agent 数量
agents.total.count          # 总 Agent 数量
```

### 3.3 迁移映射表

| 原状态值 | 新状态值 | 场景 | 语义 |
|----------|----------|------|------|
| `active` | `in_progress` | Agent 分配状态 | 正在执行任务 |
| `active` | `active` | Consent 状态 | 授权已激活（保持不变） |
| `agents.active.count` | `agents.in_progress.count` | 监控指标 | 执行中数量 |

## 4. 执行计划

### 4.1 WBS 任务分解

#### 4.1.1 文档修正（优先级：高）
- **WBS-QA-007**：修正 `接口需求清单_V2.3.md` 中 agent_assignments.status 枚举
- **WBS-QA-008**：更新 `需求规格说明书_V2.3.md` 中监控指标定义
- **WBS-QA-009**：同步修正 `验收标准与测试策略_V2.3.md` 相关引用

#### 4.1.2 Postman 集合更新（优先级：中）
- **WBS-QA-010**：更新 Postman 断言，禁用 `active` 用于 Agent 状态校验
- **WBS-QA-011**：新增 `in_progress` 状态的正向断言

### 4.2 风险评估

| 风险项 | 影响 | 概率 | 缓解措施 |
|--------|------|------|----------|
| R-QA-04 | 前端适配延迟 | 中 | 提前通知前端团队，提供迁移指南 |
| R-QA-05 | 历史数据不一致 | 低 | 当前为预览版，影响有限 |
| R-QA-06 | 第三方集成影响 | 低 | 文档化向后兼容策略 |

### 4.3 验收标准

#### 4.3.1 文档一致性
- [ ] 所有状态枚举与 OpenAPI 契约一致
- [ ] 无 `active` 误用于 Agent 执行状态的场景
- [ ] 监控指标语义明确，无歧义

#### 4.3.2 契约测试通过
- [ ] Postman 集合执行无 `active` 相关断言失败
- [ ] 新增 `in_progress` 状态的正向测试通过

#### 4.3.3 文档追溯性
- [ ] 迁移变更记录完整
- [ ] 影响范围文档化
- [ ] 提供迁移前后对照表

## 5. 治理规范

### 5.1 状态枚举设计原则
1. **语义唯一性**：同一状态值在不同上下文中应有明确且一致的语义
2. **业务对齐**：状态枚举应反映真实业务流程
3. **扩展性**：预留未来状态扩展空间
4. **可观测性**：支持有效的监控与告警

### 5.2 变更管控流程
1. **提案阶段**：任何状态枚举变更须提交设计评审
2. **影响分析**：评估对文档、契约、测试的影响范围
3. **迁移计划**：制定详细的迁移路径与回滚方案
4. **验收确认**：通过契约测试与文档审查后方可合入

## 6. 后续行动

### 6.1 即时行动（本轮）
1. 修正 `接口需求清单_V2.3.md` 中的 agent_assignments.status
2. 更新监控指标定义
3. 同步修正验收文档

### 6.2 中期规划
1. 建立状态枚举字典与治理工具
2. 集成到 CI/CD 流水线中的契约一致性检查
3. 提供状态机可视化工具

---

**附录：迁移检查清单**

- [x] 📋 修正 `状态枚举字典_V2.3.md` Line 94: agents.active.count → agents.busy.count 
- [x] 📋 确认 `experience.py` Line 345: status="active" 为经验规则启用状态（合法保留）
- [x] 📋 更新 Postman 集合断言（已完成）
- [x] 📋 验证 OpenAPI 契约一致性（已完成）
- [x] 📋 更新项目里程碑与风险计划（已完成）
- [x] 📋 归档迁移报告至 WBS 追踪（已完成）

**负责人**：星河  
**计划完成时间**：2025-01-28  
**状态跟踪**：projects/StarRiver_SuperBrain_V2.3/issues/active-semantic-migration

## 7. 执行结果总结（2025-01-28）

### 7.1 文档与契约修复结果
- ✅ OpenAPI: 已统一 Agents 任务状态枚举为 [pending, in_progress, completed, failed, canceled, timeout]，并保留 Consent.status 的 [active, revoked, pending] 不变；GET /agents/status 的 agents[].status 为 [idle, busy, error, maintenance]
- ✅ 接口需求清单: agent_assignments[].status 的枚举与示例已移除 active，采用 in_progress，并补充 canceled/timeout 的说明
- ✅ 验收标准与测试策略: 已修正状态枚举与断言，新增状态枚举校验与 Postman 脚本路径修正
- ✅ Postman 集合: 取消任务接口期望 202（Accepted）；结果/轨迹查询仍为 200；新增/修正状态断言覆盖 canceled/timeout；禁用 active 作为执行中

### 7.2 一致性与残留检查
- ✅ 语义搜索与正则扫描：未发现 active 作为“执行中”语义的残留引用（Consent 与备份/历史文件中的 active 不在修复范围内）
- ✅ busy_agents: 已替换并在 GET /agents/status 中保留，未发现 active_agents 残留

### 7.3 回归与风险复核
- ✅ 契约一致性：各文档与 Postman 集合同步一致
- ⚠️ 备份与历史目录（backup/flake8_backup/repair_backup 等）存在使用 active 的枚举，但为历史归档，保持只读，后续以静态扫描白名单方式忽略

## 8. 后续监控与治理建议

### 8.1 监控与指标
- 建立“状态枚举一致性扫描”CI 任务（每日）：
  - 规则1：禁止在 Agent 执行语境（agent_assignments/status、任务响应 status）使用 active
  - 规则2：任务状态必须属于 [pending, in_progress, completed, failed, canceled, timeout]
  - 规则3：Agent 运行状态必须属于 [idle, busy, error, maintenance]
- 指标与告警：
  - docs_contract.check.fail.count（>0 触发告警）
  - postman.contract.fail.count（>0 触发告警）

### 8.2 流程与工具化
- 在 PR 检查清单中新增项：“状态枚举语义检查（active 禁止误用）”
- 在 Postman 集合中为关键断言添加“阻断”标签，集成到 CI 失败门禁
- 在 requirements/api/postman 下补充一键运行脚本（run_postman_collection.ps1）与 README（若不存在）

### 8.3 治理资产与责任人
- 状态枚举字典：集中维护于 docs/requirements/standards/状态枚举字典.md（新建占位，后续完善）
- 责任人：星河（Owner），熙龙（Reviewer）
- 周期复盘：每两周回顾一次契约一致性与断言覆盖率

### 8.4 回滚与兼容策略
- 若第三方集成短期仍使用 active 表示执行中：
  - 文档中提供兼容说明与映射表，仅限网关层做向后兼容（active → in_progress），有效期两周
  - 兼容开关：默认关闭，仅在灰度期间按租户白名单开启

## 9. 验收勾选更新

- [x] 所有状态枚举与 OpenAPI 契约一致
- [x] 无 `active` 误用于 Agent 执行状态的场景
- [x] 监控指标语义明确，无歧义
- [x] Postman 集合执行无 `active` 相关断言失败（本地验证完成）
- [x] 新增 `in_progress`、`canceled`、`timeout` 的正向/负向测试通过
- [x] 迁移变更记录完整，影响范围已文档化，附映射表

---
注：备份/历史目录中的 active 保持不变，纳入静态扫描白名单，不影响当前版本契约。