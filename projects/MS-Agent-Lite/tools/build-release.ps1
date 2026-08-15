# MS-Agent-Lite release packaging script
# 1) Assemble distribution content from git-tracked files (auto-excludes local
#    sensitive files such as config.json, resume files, generated materials)
# 2) Compile the Inno Setup installer into tools\_dist
$ErrorActionPreference = 'Stop'
# Decode external command output (git ls-files with Chinese paths) as UTF-8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root   = Split-Path -Parent $PSScriptRoot
$tools  = $PSScriptRoot
$staging = Join-Path $tools '_staging'
$dist    = Join-Path $tools '_dist'

if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging -Force | Out-Null

# 1. Copy git-tracked files (i.e. the exact release content of the repository)
Push-Location $root
try { $files = git -c core.quotepath=false ls-files } finally { Pop-Location }
foreach ($f in $files) {
    $dst    = Join-Path $staging $f
    $dstDir = Split-Path -Parent $dst
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
    Copy-Item -Path (Join-Path $root $f) -Destination $dst
}
Write-Host "[1/2] Staged $($files.Count) files into _staging"

# 2. Compile the installer
$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path $_ }
if (-not $candidates) { throw 'ISCC.exe (Inno Setup 6) not found. Install Inno Setup first.' }
$iscc = $candidates | Select-Object -First 1

New-Item -ItemType Directory -Path $dist -Force | Out-Null

# 2.1 Derive version: Actions 注入的 RELEASE_VERSION（tag，如 v0.4.19）→ 本地 git tag → .iss 默认值
$ver = $env:RELEASE_VERSION
if (-not $ver) {
    Push-Location $root
    try { $ver = git describe --tags --abbrev=0 2>$null } finally { Pop-Location }
}
if ($ver -match '^v') { $ver = $ver.Substring(1) }
$issArgs = @()
if ($ver) {
    Write-Host "[2/2] Building installer for version $ver (tag=$env:RELEASE_VERSION)"
    $issArgs += "/DMyAppVersion=$ver"
} else {
    Write-Host '[2/2] No tag found, using default version defined in .iss'
}
& $iscc $issArgs (Join-Path $tools 'ms-agent-lite.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit=$LASTEXITCODE)" }
Write-Host '[2/2] Installer generated in tools\_dist'
