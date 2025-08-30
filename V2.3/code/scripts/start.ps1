Param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 8230,
  [switch]$Reload
)

$env:HOST = $Host
$env:PORT = "$Port"
$env:RELOAD = $(if ($Reload) { "true" } else { "false" })

python -m scripts.deploy