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
$PreviousEnvironment = @{}
foreach ($Name in @('WEB_BIND_ADDRESS', 'WEB_PORT', 'APP_ORIGIN')) {
    $PreviousEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
}
Push-Location $ProjectRoot
try {
    $EngineType = Invoke-Docker -DockerArguments @('info', '--format', '{{.OSType}}')
    if (($EngineType -join '').Trim() -ne 'linux') { throw 'Select Linux containers in Docker Desktop before running this project.' }
    Write-Host '1/5 Docker integration tests (isolated synthetic database)'
    $TestCompose = @('compose', '-p', 'bestar-hours-test', '-f', 'compose.test.yaml')
    Invoke-Docker -DockerArguments ($TestCompose + @('up', '--build', '--abort-on-container-exit', '--exit-code-from', 'engine-tests'))

    $Image = 'bestar-hours-test-engine-tests'
    $ScriptPath = Join-Path $PSScriptRoot 'docker-verify.py'
    $ScriptMount = "type=bind,source=$ScriptPath,target=/verification.py,readonly"
    $EnvFile = Join-Path $ProjectRoot '.env.smoke'
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        $EnvLines = Invoke-Docker -DockerArguments @('run', '--rm', '--mount', $ScriptMount, $Image, 'python', '/verification.py', 'init')
        [System.IO.File]::WriteAllText($EnvFile, ($EnvLines -join "`n"), [System.Text.UTF8Encoding]::new($false))
    }
    $EnvText = Get-Content -Raw -LiteralPath $EnvFile
    foreach ($Line in @('APP_ORIGIN=http://localhost:3100', 'WEB_PORT=3100')) {
        if (($EnvText -split '\r?\n') -notcontains $Line) { throw '.env.smoke does not match this isolated test profile. It has not been changed.' }
    }
    if ($EnvText -match '(?m)^WEB_BIND_ADDRESS=(?!127\.0\.0\.1\s*$).+') { throw 'The synthetic test profile must bind only to 127.0.0.1.' }
    # Override possible inherited environment settings for this verification process only.
    $env:WEB_BIND_ADDRESS = '127.0.0.1'
    $env:WEB_PORT = '3100'
    $env:APP_ORIGIN = 'http://localhost:3100'
    $AppCompose = @('compose', '--env-file', '.env.smoke', '-p', 'bestar-hours-smoke')
    Write-Host '2/5 Build and start the local Windows Docker deployment'
    Invoke-Docker -DockerArguments ($AppCompose + @('up', '--build', '-d'))

    $OutputPath = Join-Path $ProjectRoot 'storage\docker-verification'
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
    $RunArgs = @('run', '--rm', '--network', 'bestar-hours-smoke_default', '--mount', $ScriptMount,
        '--mount', "type=bind,source=$OutputPath,target=/out", $Image, 'python', '/verification.py')
    Write-Host '3/5 Verify the real HTTP upload-to-download flow'
    Invoke-Docker -DockerArguments ($RunArgs + @('run'))
    Write-Host '4/5 Restart services and verify effective rows and XLS'
    Invoke-Docker -DockerArguments ($AppCompose + @('restart', 'database', 'api', 'web'))
    Invoke-Docker -DockerArguments ($RunArgs + @('resume'))
    Write-Host '5/5 Remove only the ephemeral test containers; leave the application running'
    Invoke-Docker -DockerArguments ($TestCompose + @('down'))
    Invoke-Docker -DockerArguments ($AppCompose + @('ps'))
    Write-Host 'READY: http://localhost:3100/work-hours'
    Write-Host 'Application stays running without login. This profile contains synthetic test records.'
} finally {
    foreach ($Name in $PreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousEnvironment[$Name], 'Process')
    }
    Pop-Location
}
