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
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Compose failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

$StartsAllServices = -not ($Services -and $Services.Count -gt 0)
$RequestedServices = @()
if (-not $StartsAllServices) {
    $RequestedServices = $Services | ForEach-Object { $_.ToLowerInvariant() }
}
$StartsApi = $StartsAllServices -or $RequestedServices -contains "api"
$StartsWorker = $StartsAllServices -or $RequestedServices -contains "worker"
$StartsWeb = $StartsAllServices -or $RequestedServices -contains "web"
$StartsMinio = $StartsAllServices -or $RequestedServices -contains "minio" -or $StartsApi -or $StartsWorker

Write-Host ""
Write-Host "Services are starting. Useful URLs:"
if ($StartsApi) {
    Write-Host "  API health:    http://127.0.0.1:8000/api/v1/health"
}
if ($StartsWeb) {
    Write-Host "  Web:           http://127.0.0.1:5173"
}
else {
    Write-Host "  Web:           not requested. Start it with: .\scripts\dev-docker.ps1 web"
}
if ($StartsMinio) {
    Write-Host "  MinIO console: http://127.0.0.1:9001"
}
Write-Host ""
if ($StartsApi -or $StartsWorker) {
    Write-Host "Follow API/worker logs:"
    Write-Host "  docker compose -f infra/compose/docker-compose.yml logs -f api worker"
}
