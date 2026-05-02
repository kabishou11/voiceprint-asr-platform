param(
    [switch]$SkipModelDownload,
    [switch]$SkipGpuCheck,
    [switch]$Pull,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Services
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"
$EnvExample = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"
$ModelsDir = Join-Path $Root "models"
$StorageDir = Join-Path $Root "storage"
$ReferenceRoot = Resolve-Path -Path (Join-Path $Root "..") | ForEach-Object {
    Join-Path $_ "3D-Speaker"
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

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
        Write-Host ".env is aligned with .env.example keys"
        return
    }

    Add-Content -Path $EnvFile -Value ""
    Add-Content -Path $EnvFile -Value "# Added by scripts/prod-up.ps1 to align with .env.example"
    foreach ($Line in $MissingLines) {
        Add-Content -Path $EnvFile -Value $Line
    }
    Write-Host "Added missing .env keys: $($MissingLines.Count)"
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

Set-Location $Root

Write-Step "Checking Docker"
Invoke-Checked -FilePath "docker" -Arguments @("--version")
Invoke-Checked -FilePath "docker" -Arguments @("compose", "version")

if (-not $SkipGpuCheck) {
    Write-Step "Checking Docker GPU passthrough"
    Invoke-Checked -FilePath "docker" -Arguments @(
        "run",
        "--rm",
        "--gpus",
        "all",
        "nvidia/cuda:12.4.1-base-ubuntu22.04",
        "nvidia-smi"
    )
}

Write-Step "Preparing local directories and .env"
Ensure-Directory $ModelsDir
Ensure-Directory $StorageDir
Ensure-Directory $ReferenceRoot
Sync-EnvFile

if ($Pull) {
    Write-Step "Pulling base service images"
    Invoke-Checked -FilePath "docker" -Arguments @(
        "compose",
        "-f",
        $ComposeFile,
        "pull",
        "postgres",
        "redis",
        "minio"
    )
}

if (-not $SkipModelDownload) {
    Write-Step "Downloading required models and 3D-Speaker reference runtime"
    Invoke-Checked -FilePath "docker" -Arguments @(
        "compose",
        "-f",
        $ComposeFile,
        "--profile",
        "init",
        "run",
        "--rm",
        "model-init"
    )
}

Write-Step "Building and starting production stack"
$ComposeArgs = @("compose", "-f", $ComposeFile, "up", "-d", "--build")
if ($Services -and $Services.Count -gt 0) {
    $ComposeArgs += $Services
}
Invoke-Checked -FilePath "docker" -Arguments $ComposeArgs

Write-Step "Runtime endpoints"
Write-Host "API health:    http://127.0.0.1:8000/api/v1/health"
Write-Host "Models:        http://127.0.0.1:8000/api/v1/models"
Write-Host "Web:           http://127.0.0.1:5173"
Write-Host "MinIO console: http://127.0.0.1:9001"

Write-Step "Useful verification commands"
Write-Host "docker compose -f infra/compose/docker-compose.yml logs -f api worker"
Write-Host "curl http://127.0.0.1:8000/api/v1/health"
Write-Host "curl http://127.0.0.1:8000/api/v1/models"
Write-Host "curl -X POST http://127.0.0.1:8000/api/v1/models/funasr-nano/warmup-worker"
Write-Host "curl -X POST http://127.0.0.1:8000/api/v1/models/3dspeaker-diarization/warmup-worker"
Write-Host "curl -X POST http://127.0.0.1:8000/api/v1/models/3dspeaker-embedding/warmup-worker"
