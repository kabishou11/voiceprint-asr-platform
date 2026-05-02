param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Services
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"
$EnvExample = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"

function Read-EnvMap {
    param([string]$Path)
    $Map = [ordered]@{}
    if (-not (Test-Path $Path)) {
        return $Map
    }
    foreach ($Line in Get-Content $Path) {
        if ($Line -match '^\s*#' -or $Line -notmatch '=') {
            continue
        }
        $Parts = $Line.Split('=', 2)
        $Key = $Parts[0].Trim()
        if ($Key) {
            $Map[$Key] = $Parts[1]
        }
    }
    return $Map
}

function Sync-EnvFile {
    if (-not (Test-Path $EnvExample)) {
        Write-Error ".env.example not found: $EnvExample"
        exit 1
    }

    if (-not (Test-Path $EnvFile)) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "Created .env from .env.example"
        return
    }

    $ExampleMap = Read-EnvMap $EnvExample
    $CurrentMap = Read-EnvMap $EnvFile
    $MissingLines = New-Object System.Collections.Generic.List[string]

    foreach ($Key in $ExampleMap.Keys) {
        if (-not $CurrentMap.Contains($Key)) {
            $MissingLines.Add("$Key=$($ExampleMap[$Key])")
        }
    }

    if ($MissingLines.Count -eq 0) {
        return
    }

    Add-Content -Path $EnvFile -Value ""
    Add-Content -Path $EnvFile -Value "# Added by scripts/dev-docker.ps1 to align with .env.example"
    foreach ($Line in $MissingLines) {
        Add-Content -Path $EnvFile -Value $Line
    }
    Write-Host "Added missing .env keys: $($MissingLines.Count)"
}

Write-Host "Starting Docker Compose stack..."
Write-Host "Compose file: $ComposeFile"
Sync-EnvFile

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
