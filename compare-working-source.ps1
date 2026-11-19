param(
    [string]$WorkingZip = ".\scum-current-source-review.zip",
    [string]$ReleaseRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)
$ErrorActionPreference = 'Stop'
$WorkingZip = (Resolve-Path -LiteralPath $WorkingZip).Path
$ReleaseRoot = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("scum-review-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Temp | Out-Null
try {
    Expand-Archive -LiteralPath $WorkingZip -DestinationPath $Temp -Force
    $files = @(
        'docker/Dockerfile',
        'docker/entrypoint.sh',
        'docker/supervisor.py',
        'docker/user_accounts.py',
        'docker/web/index.html',
        'docker-compose.yml'
    )
    $differences = 0
    foreach ($f in $files) {
        $rel = $f.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $a = Join-Path $Temp $rel
        $b = Join-Path $ReleaseRoot $rel
        if (!(Test-Path -LiteralPath $a)) {
            Write-Host "WORKING SOURCE MISSING: $f" -ForegroundColor Yellow
            continue
        }
        if (!(Test-Path -LiteralPath $b)) {
            Write-Host "RELEASE SOURCE MISSING: $f" -ForegroundColor Red
            $differences++
            continue
        }
        $ah = (Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash
        $bh = (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash
        if ($ah -eq $bh) {
            Write-Host "MATCH: $f" -ForegroundColor Green
        } else {
            Write-Host "DIFFERENT: $f" -ForegroundColor Yellow
            $differences++
            if (Get-Command git -ErrorAction SilentlyContinue) {
                & git -c core.autocrlf=false -c core.safecrlf=false --no-pager diff --no-index -- "$a" "$b"
                # Git's exit code 1 simply means files differ; intentional
            }
        }
    }
    Write-Host "`nDiffering files: $differences" 
    if ($differences -gt 0) {
        Write-Host 'STOP: inspect differences before publishing. No files were changed.' -ForegroundColor Yellow
    } else {
        Write-Host 'Compared files match the working archive. Continue with independent release-specific review.' -ForegroundColor Green
    }
} finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force
}

