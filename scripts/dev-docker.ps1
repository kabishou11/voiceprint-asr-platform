param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Services
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"

Write-Host "Starting Docker Compose stack..."
Write-Host "Compose file: $ComposeFile"

$ComposeArgs = @("compose", "-f", $ComposeFile, "up", "-d", "--build")
if ($Services -and $Services.Count -gt 0) {
    $ComposeArgs += $Services
}

& docker @ComposeArgs

Write-Host ""
Write-Host "Services are starting. Useful URLs:"
Write-Host "  API health:    http://127.0.0.1:8000/api/v1/health"
Write-Host "  Web:           http://127.0.0.1:5173"
Write-Host "  MinIO console: http://127.0.0.1:9001"
Write-Host ""
Write-Host "Follow API/worker logs:"
Write-Host "  docker compose -f infra/compose/docker-compose.yml logs -f api worker"
