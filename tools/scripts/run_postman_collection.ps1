Param(
  [string]$CollectionPath = "..\..\tests\postman\status_enum_v2.3.postman_collection.json",
  [string]$EnvPath = "..\..\tests\postman\postman_environment_local.json",
  [string]$ReportDir = "..\..\reports\testing\postman"
)

# Ensure report directory exists
$fullReportDir = Resolve-Path -Path $ReportDir -ErrorAction SilentlyContinue
if (-not $fullReportDir) {
  New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
  $fullReportDir = Resolve-Path -Path $ReportDir
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportHtml = Join-Path $fullReportDir "postman_report_$timestamp.html"
$reportJson = Join-Path $fullReportDir "postman_report_$timestamp.json"

# Prefer newman if available, fallback to postman-cli, then npx newman
function Command-Exists {
  param([string]$cmd)
  $old = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
  $null = Get-Command $cmd
  $exists = $?
  $ErrorActionPreference = $old
  return $exists
}

if (Command-Exists "newman") {
  Write-Host "Running with newman..." -ForegroundColor Green
  newman run $CollectionPath -e $EnvPath --reporters cli,htmlextra,json --reporter-htmlextra-export $reportHtml --reporter-json-export $reportJson --suppress-exit-code
}
elseif (Command-Exists "postman") {
  Write-Host "Running with postman-cli..." -ForegroundColor Green
  postman collection run "$CollectionPath" -e "$EnvPath" --reporters "cli,htmlextra,json" --reporter-htmlextra-export "$reportHtml" --reporter-json-export "$reportJson"
}
elseif (Command-Exists "npx") {
  Write-Host "Running with npx newman (no global install)..." -ForegroundColor Yellow
  npx -y -p newman -p newman-reporter-htmlextra newman run "$CollectionPath" -e "$EnvPath" --reporters "cli,htmlextra,json" --reporter-htmlextra-export "$reportHtml" --reporter-json-export "$reportJson" --suppress-exit-code
}
else {
  Write-Error "Neither 'newman' nor 'postman' nor 'npx' found. Please install Node.js/npm or Postman CLI."
  exit 1
}

Write-Host "Reports saved to: $fullReportDir" -ForegroundColor Cyan