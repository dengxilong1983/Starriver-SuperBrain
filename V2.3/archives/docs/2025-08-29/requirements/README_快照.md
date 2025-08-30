# Postman API 契约测试

> **目录用途**：存放 Postman 集合、环境配置和自动化测试脚本，用于验证 OpenAPI 规范的契约合规性  
> **版本**：V2.3  
> **维护者**：星河（Owner），熙龙（Reviewer）  

## 📁 目录结构

```
postman/
├── README.md                                    # 本说明文档
├── run_postman_collection.ps1                  # 一键运行脚本（PowerShell）
├── openapi_v2.3-preview.postman_collection.json # Postman 集合文件
├── env_v2.3-preview.postman_environment.json   # 环境配置文件
└── reports/                                     # 测试报告目录（自动生成）
    ├── postman_report_2025-01-28_14-30-00.json
    └── postman_report_2025-01-28_14-30-00.html
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装 Newman（Postman 命令行工具）
npm install -g newman

# 安装 HTML 报告生成器（可选）
npm install -g newman-reporter-html
```

### 2. 一键执行测试

```powershell
# 基础执行
.\run_postman_collection.ps1

# 详细输出模式
.\run_postman_collection.ps1 -Verbose

# 不生成报告
.\run_postman_collection.ps1 -GenerateReport:$false

# 指定环境
.\run_postman_collection.ps1 -Environment "staging"
```

### 3. 手动执行（高级）

```bash
# 基础命令
newman run openapi_v2.3-preview.postman_collection.json \
  -e env_v2.3-preview.postman_environment.json

# 生成报告
newman run openapi_v2.3-preview.postman_collection.json \
  -e env_v2.3-preview.postman_environment.json \
  -r html,json \
  --reporter-html-export reports/report.html \
  --reporter-json-export reports/report.json
```

## 🔍 测试覆盖内容

### 核心契约测试项

- **状态枚举一致性**：验证所有接口的状态字段符合标准枚举定义
- **响应结构完整性**：确保 JSON Schema 与 OpenAPI 规范一致  
- **HTTP 状态码正确性**：验证成功/异常场景的状态码  
- **字段类型与格式**：验证数据类型、日期格式、枚举值等  

### 重点测试场景

#### 1. Agent 任务状态断言

```javascript
// 任务状态必须在标准枚举内
pm.test("Task status must be valid enum", function() {
    const validStatuses = ['pending', 'in_progress', 'completed', 'failed', 'canceled', 'timeout'];
    const status = pm.response.json().status;
    pm.expect(validStatuses).to.include(status);
});

// 禁止使用 active 状态
pm.test("Task status must not be 'active'", function() {
    const status = pm.response.json().status;
    pm.expect(status).to.not.equal('active');
});
```

#### 2. Agent 运行状态断言

```javascript
// Agent 状态必须在运行枚举内
pm.test("Agent status must be valid runtime enum", function() {
    const validStatuses = ['idle', 'busy', 'error', 'maintenance'];
    const agents = pm.response.json().agents;
    agents.forEach(agent => {
        pm.expect(validStatuses).to.include(agent.status);
    });
});
```

#### 3. 字段存在性检查

```javascript
// 必需字段检查
pm.test("Response has required fields", function() {
    const response = pm.response.json();
    pm.expect(response).to.have.property('busy_agents');
    pm.expect(response).to.have.property('agents');
});
```

## 📊 测试报告

### 报告文件说明

- **JSON 报告**：`reports/postman_report_[timestamp].json`  
  - 机器可读格式，用于 CI/CD 集成  
  - 包含详细的断言结果、响应数据、执行时间等  

- **HTML 报告**：`reports/postman_report_[timestamp].html`  
  - 人类可读格式，适合手动检查  
  - 可视化展示测试结果、失败详情、性能指标等  

### 关键指标

| 指标 | 说明 | 期望值 |
|------|------|--------|
| `requests.total` | 总请求数 | ≥ 10 |
| `requests.failed` | 失败请求数 | 0 |
| `assertions.total` | 总断言数 | ≥ 50 |
| `assertions.failed` | 失败断言数 | 0 |

## 🚨 故障排除

### 常见问题

#### 1. Newman 未安装

```
❌ Newman 未安装，请先安装:
   npm install -g newman
   npm install -g newman-reporter-html
```

**解决方案**：按提示安装 Newman

#### 2. 状态枚举断言失败

```
⚠️ 检测到状态枚举相关的断言失败:
   • Task status must not be 'active'
   • Agent status must be valid runtime enum
```

**解决方案**：
1. 检查 API 实现是否使用了禁用的状态值（如 `active`）
2. 参考 `状态枚举字典_V2.3.md` 确认标准枚举定义
3. 更新 API 实现或修正 Postman 断言

#### 3. 环境连接失败

```
Error: connect ECONNREFUSED 127.0.0.1:8080
```

**解决方案**：
1. 确认 API 服务已启动
2. 检查环境配置文件中的 `baseUrl` 设置
3. 验证网络连接和防火墙设置

### 调试技巧

```powershell
# 1. 详细输出模式
.\run_postman_collection.ps1 -Verbose

# 2. 单独运行特定请求
newman run collection.json --folder "Agents API"

# 3. 设置更长的超时时间
newman run collection.json --timeout-request 30000

# 4. 跳过 SSL 验证（仅开发环境）
newman run collection.json --insecure
```

## 🔧 CI/CD 集成

### Jenkins Pipeline 示例

```groovy
stage('API Contract Testing') {
    steps {
        script {
            powershell '''
                cd docs/requirements/api/postman
                .\run_postman_collection.ps1 -GenerateReport
            '''
        }
        
        publishHTML([
            allowMissing: false,
            alwaysLinkToLastBuild: true,
            keepAll: true,
            reportDir: 'docs/requirements/api/postman/reports',
            reportFiles: '*.html',
            reportName: 'Postman Contract Test Report'
        ])
    }
}
```

### GitHub Actions 示例

```yaml
- name: Run Postman Tests
  run: |
    npm install -g newman newman-reporter-html
    cd docs/requirements/api/postman
    pwsh -File run_postman_collection.ps1
  
- name: Upload Test Reports
  uses: actions/upload-artifact@v3
  with:
    name: postman-reports
    path: docs/requirements/api/postman/reports/
```

## 📚 参考文档

- [状态枚举字典_V2.3.md](../standards/状态枚举字典_V2.3.md) - 状态枚举标准定义
- [OpenAPI 规范文件](../openapi_v2.3-preview.yaml) - API 接口契约
- [验收标准与测试策略_V2.3.md](../../验收标准与测试策略_V2.3.md) - 测试策略文档
- [Newman 官方文档](https://github.com/postmanlabs/newman) - Newman 使用指南

## 📝 维护日志

| 日期 | 版本 | 变更内容 | 负责人 |
|------|------|----------|--------|
| 2025-01-28 | v1.0 | 初始版本，创建 PowerShell 脚本和说明文档 | 星河 |

---

**💡 提示**：如有问题或改进建议，请联系维护团队或提交 Issue。