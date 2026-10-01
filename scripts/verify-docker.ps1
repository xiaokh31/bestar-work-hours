# Requires Windows PowerShell 5.1+ and Docker Desktop running Linux containers.
# All application/test dependencies run in Docker; no host Python or Node needed.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($DockerCommand) {
    $DockerExe = $DockerCommand.Source
} else {
    $Candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')
    )
    $DockerExe = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $DockerExe) { throw 'Docker Desktop CLI not found. Install/start Docker Desktop and reopen PowerShell.' }
# Docker's credential helper must be discoverable too. Only this process PATH changes.
$env:PATH = (Split-Path -Parent $DockerExe) + ';' + $env:PATH
function Invoke-Docker {
    param([string[]]$DockerArguments)
    & $DockerExe @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE). Existing data has been preserved." }
}
# This stack has a separate network and a tmpfs database, without host ports.
# Never seed or restart the application that holds the user's attendance records.
$TestCompose = @('compose', '-p', 'bestar-hours-test', '-f', 'compose.test.yaml')
Push-Location $ProjectRoot
try {
    $EngineType = Invoke-Docker -DockerArguments @('info', '--format', '{{.OSType}}')
    if (($EngineType -join '').Trim() -ne 'linux') { throw 'Select Linux containers in Docker Desktop before running this project.' }
    Write-Host 'Run isolated, temporary engine/API regression tests.'
    try {
        Invoke-Docker -DockerArguments ($TestCompose + @('up', '--build', '--abort-on-container-exit', '--exit-code-from', 'engine-tests'))
    } finally {
        Invoke-Docker -DockerArguments ($TestCompose + @('down'))
    }
    Write-Host 'PASS: Temporary test data removed. The attendance application was not modified.'
} finally {
    Pop-Location
}
