# Postman 集合一键运行脚本
# 版本：V2.3
# 创建日期：2025-01-28
# 用途：自动执行 Postman API 契约测试，验证 OpenAPI 规范合规性

param(
    [string]$Environment = "dev",
    [string]$Collection = "openapi_v2.3-preview.postman_collection.json",
    [string]$EnvFile = "env_v2.3-preview.postman_environment.json",
    [switch]$Verbose = $false,
    [switch]$GenerateReport = $true
)

# 脚本路径配置
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
$CollectionPath = Join-Path $ScriptPath $Collection
$EnvironmentPath = Join-Path $ScriptPath $EnvFile
$ReportDir = Join-Path $ScriptPath "reports"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$ReportFile = Join-Path $ReportDir "postman_report_$Timestamp.json"
$HtmlReportFile = Join-Path $ReportDir "postman_report_$Timestamp.html"

# 函数：检查 Newman 是否安装
function Test-NewmanInstalled {
    try {
        $null = newman --version
        return $true
    }
    catch {
        return $false
    }
}

# 函数：检查 Postman 集合文件
function Test-PostmanFiles {
    if (-not (Test-Path $CollectionPath)) {
        Write-Error "Postman 集合文件未找到: $CollectionPath"
        return $false
    }
    
    if (-not (Test-Path $EnvironmentPath)) {
        Write-Warning "环境文件未找到: $EnvironmentPath，将使用默认环境"
        $script:EnvironmentPath = $null
    }
    
    return $true
}

# 函数：创建报告目录
function Initialize-ReportDirectory {
    if (-not (Test-Path $ReportDir)) {
        New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
        Write-Host "✓ 创建报告目录: $ReportDir" -ForegroundColor Green
    }
}

# 函数：构建 Newman 命令
function Build-NewmanCommand {
    $cmd = @("newman", "run", "`"$CollectionPath`"")
    
    if ($EnvironmentPath) {
        $cmd += "-e"
        $cmd += "`"$EnvironmentPath`""
    }
    
    if ($GenerateReport) {
        $cmd += "-r"
        $cmd += "json,html"
        $cmd += "--reporter-json-export"
        $cmd += "`"$ReportFile`""
        $cmd += "--reporter-html-export"
        $cmd += "`"$HtmlReportFile`""
    }
    
    if ($Verbose) {
        $cmd += "--verbose"
    }
    
    # 添加状态枚举相关的断言配置
    $cmd += "--timeout-request"
    $cmd += "10000"  # 10秒超时
    $cmd += "--bail"  # 遇到失败立即停止（可选）
    
    return $cmd -join " "
}

# 函数：执行 Newman 并处理输出
function Invoke-NewmanRun {
    param($Command)
    
    Write-Host "🚀 开始执行 Postman 集合测试..." -ForegroundColor Yellow
    Write-Host "命令: $Command" -ForegroundColor Gray
    Write-Host ""
    
    $startTime = Get-Date
    
    try {
        # 执行 Newman 命令
        Invoke-Expression $Command
        $exitCode = $LASTEXITCODE
        
        $endTime = Get-Date
        $duration = $endTime - $startTime
        
        if ($exitCode -eq 0) {
            Write-Host ""
            Write-Host "✅ Postman 集合测试执行成功！" -ForegroundColor Green
            Write-Host "⏱️  执行时间: $($duration.TotalSeconds.ToString('F2')) 秒" -ForegroundColor Green
            
            if ($GenerateReport -and (Test-Path $HtmlReportFile)) {
                Write-Host "📊 HTML 报告: $HtmlReportFile" -ForegroundColor Cyan
            }
        }
        else {
            Write-Host ""
            Write-Host "❌ Postman 集合测试执行失败！" -ForegroundColor Red
            Write-Host "⏱️  执行时间: $($duration.TotalSeconds.ToString('F2')) 秒" -ForegroundColor Red
            Write-Host "💡 请检查测试结果，重点关注状态枚举断言失败" -ForegroundColor Yellow
        }
        
        return $exitCode
    }
    catch {
        Write-Host ""
        Write-Host "💥 执行过程中发生异常: $($_.Exception.Message)" -ForegroundColor Red
        return 1
    }
}

# 函数：分析测试结果
function Analyze-TestResults {
    if (-not $GenerateReport -or -not (Test-Path $ReportFile)) {
        return
    }
    
    try {
        $report = Get-Content $ReportFile | ConvertFrom-Json
        $run = $report.run
        
        Write-Host ""
        Write-Host "📈 测试结果统计:" -ForegroundColor Cyan
        Write-Host "   总请求数: $($run.stats.requests.total)" -ForegroundColor White
        Write-Host "   成功请求: $($run.stats.requests.total - $run.stats.requests.failed)" -ForegroundColor Green
        Write-Host "   失败请求: $($run.stats.requests.failed)" -ForegroundColor Red
        Write-Host "   总断言数: $($run.stats.assertions.total)" -ForegroundColor White
        Write-Host "   成功断言: $($run.stats.assertions.total - $run.stats.assertions.failed)" -ForegroundColor Green
        Write-Host "   失败断言: $($run.stats.assertions.failed)" -ForegroundColor Red
        
        # 检查状态枚举相关的失败
        $statusEnumFailures = @()
        foreach ($execution in $run.executions) {
            if ($execution.assertions) {
                foreach ($assertion in $execution.assertions) {
                    if ($assertion.assertion -match "status" -and $assertion.error) {
                        $statusEnumFailures += $assertion
                    }
                }
            }
        }
        
        if ($statusEnumFailures.Count -gt 0) {
            Write-Host ""
            Write-Host "⚠️  检测到状态枚举相关的断言失败 ($($statusEnumFailures.Count) 个):" -ForegroundColor Yellow
            foreach ($failure in $statusEnumFailures[0..2]) {  # 只显示前3个
                Write-Host "   • $($failure.assertion)" -ForegroundColor Yellow
            }
            if ($statusEnumFailures.Count -gt 3) {
                Write-Host "   • ... 还有 $($statusEnumFailures.Count - 3) 个失败" -ForegroundColor Yellow
            }
        }
    }
    catch {
        Write-Warning "无法解析测试报告: $($_.Exception.Message)"
    }
}

# 主执行逻辑
Write-Host "🔍 星河超脑 V2.3 - Postman API 契约测试" -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta

# 1. 检查 Newman 是否安装
if (-not (Test-NewmanInstalled)) {
    Write-Host "❌ Newman 未安装，请先安装:" -ForegroundColor Red
    Write-Host "   npm install -g newman" -ForegroundColor White
    Write-Host "   npm install -g newman-reporter-html" -ForegroundColor White
    exit 1
}

Write-Host "✓ Newman 已安装" -ForegroundColor Green

# 2. 检查 Postman 文件
if (-not (Test-PostmanFiles)) {
    exit 1
}

Write-Host "✓ Postman 集合文件检查通过" -ForegroundColor Green

# 3. 初始化报告目录
if ($GenerateReport) {
    Initialize-ReportDirectory
}

# 4. 构建并执行 Newman 命令
$newmanCommand = Build-NewmanCommand
$exitCode = Invoke-NewmanRun -Command $newmanCommand

# 5. 分析测试结果
if ($GenerateReport) {
    Analyze-TestResults
}

# 6. 退出处理
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "🎉 所有测试已通过，API 契约合规！" -ForegroundColor Green
}
else {
    Write-Host "⚠️  存在测试失败，请检查状态枚举一致性。" -ForegroundColor Red
    Write-Host "💡 参考文档: docs/requirements/standards/状态枚举字典_V2.3.md" -ForegroundColor Yellow
}

exit $exitCode