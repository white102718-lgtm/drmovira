# Local development launcher. Secrets are loaded only from the Git-ignored
# .env.local file, then passed to both backend processes at startup.
param(
  [switch]$Diagnostics,
  [switch]$DisableHotReload,
  [ValidateSet('all', 'main', 'system')]
  [string]$Service = 'all'
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$mavenCommand = Join-Path $projectRoot '.codex-toolchain\maven\bin\mvn.cmd'
$javaHome = Join-Path $projectRoot '.codex-toolchain\jdk'
$environmentFile = Join-Path $projectRoot '.env.local'
$mpowerEnvironmentFile = Join-Path $projectRoot '.env.mpower.local'
$diagnosticLogDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'adpulse-local-launch'
$systemPid = 0
$mainPid = 0

function Get-LocalEnvironment {
  param(
    [string]$ConfigPath
  )

  if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Missing local environment file: $ConfigPath"
  }

  $environment = @{}

  foreach ($line in Get-Content -LiteralPath $ConfigPath) {
    $trimmedLine = $line.Trim()

    if (-not $trimmedLine -or $trimmedLine.StartsWith('#')) {
      continue
    }

    $match = [regex]::Match($trimmedLine, '^(?<key>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$')

    if (-not $match.Success) {
      throw "Invalid local environment entry in $ConfigPath."
    }

    $value = $match.Groups['value'].Value.Trim()

    if ($value.Length -ge 2 -and (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    )) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    $environment[$match.Groups['key'].Value] = $value
  }

  return $environment
}

function Get-RequiredEnvironment {
  param(
    [hashtable]$Environment,
    [string]$VariableName
  )

  if (-not $Environment.ContainsKey($VariableName) -or [string]::IsNullOrWhiteSpace($Environment[$VariableName])) {
    throw "Missing required environment variable $VariableName in $environmentFile."
  }

  return $Environment[$VariableName]
}

function Start-AdPulseService {
  param(
    [string]$Module,
    [string[]]$Arguments,
    [hashtable]$Environment
  )

  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $mavenCommand
  $startInfo.WorkingDirectory = $projectRoot
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true

  # Windows PowerShell 5 does not expose ProcessStartInfo.ArgumentList.
  $argumentText = ($Arguments | ForEach-Object {
    if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
  }) -join ' '

  if ($Diagnostics) {
    New-Item -ItemType Directory -Force -Path $diagnosticLogDirectory | Out-Null
    $diagnosticLogFile = Join-Path $diagnosticLogDirectory "$Module-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
    $startInfo.FileName = $env:ComSpec
    $startInfo.Arguments = ('/d /c ""{0}" {1} > "{2}" 2>&1"' -f $mavenCommand, $argumentText, $diagnosticLogFile)
  } else {
    $startInfo.Arguments = $argumentText
  }

  foreach ($entry in $Environment.GetEnumerator()) {
    # Windows PowerShell 5.1 exposes the child-process environment through EnvironmentVariables.
    $startInfo.EnvironmentVariables[$entry.Key] = $entry.Value
  }

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo

  if (-not $process.Start()) {
    throw "Unable to start $Module."
  }

  if ($Diagnostics) {
    Write-Host "$Module launcher output: $diagnosticLogFile"
  }

  return $process.Id
}

function Start-HotReloadWatcher {
  param(
    [string]$SelectedService,
    [int]$SystemProcessId,
    [int]$MainProcessId
  )

  $watcherScript = Join-Path $PSScriptRoot 'watch-local-services.ps1'
  $powershellCommand = (Get-Command 'powershell.exe').Source
  $arguments = @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $watcherScript,
    '-Service',
    $SelectedService
  )

  if ($SystemProcessId -gt 0) {
    $arguments += @('-SystemProcessId', $SystemProcessId)
  }

  if ($MainProcessId -gt 0) {
    $arguments += @('-MainProcessId', $MainProcessId)
  }

  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $powershellCommand
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.Arguments = ($arguments | ForEach-Object {
    $argument = [string]$_
    if ($argument -match '\s') { '"' + $argument + '"' } else { $argument }
  }) -join ' '

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo

  if (-not $process.Start()) {
    throw 'Unable to start backend hot reload watcher.'
  }

  return $process.Id
}

$localEnvironment = Get-LocalEnvironment $environmentFile
if (Test-Path -LiteralPath $mpowerEnvironmentFile) {
  $mpowerEnvironment = Get-LocalEnvironment $mpowerEnvironmentFile
  foreach ($entry in $mpowerEnvironment.GetEnumerator()) {
    $localEnvironment[$entry.Key] = $entry.Value
  }
}
$requiredVariables = @(
  'FEISHU_OAUTH_REDIRECT_URI',
  'DB_URL',
  'REDIS_HOST',
  'REDIS_PASSWORD',
  'DORIS_URL',
  'MONGODB_URI',
  'MINIO_ACCESS_KEY',
  'MINIO_SECRET_KEY'
)
$serviceEnvironment = @{
  JAVA_HOME = $javaHome
}

foreach ($variableName in $requiredVariables) {
  $serviceEnvironment[$variableName] = Get-RequiredEnvironment $localEnvironment $variableName
}

foreach ($variableName in @('MPOWER_FEISHU_APP_ID', 'MPOWER_FEISHU_APP_SECRET')) {
  if ($localEnvironment.ContainsKey($variableName) -and -not [string]::IsNullOrWhiteSpace($localEnvironment[$variableName])) {
    $serviceEnvironment[$variableName] = $localEnvironment[$variableName]
  }
}

$devToolsJvmArgument = if ($DisableHotReload) {
  '-Dspring-boot.run.jvmArguments=-Dspring.devtools.restart.enabled=false'
} else {
  '-Dspring-boot.run.jvmArguments=-Dspring.devtools.restart.trigger-file=.reloadtrigger'
}

if ($Service -ne 'main') {
  $systemPid = Start-AdPulseService -Module 'adpulse-system' -Arguments @('-f', 'adpulse-system\pom.xml', $devToolsJvmArgument, 'spring-boot:run') -Environment $serviceEnvironment
}

if ($Service -ne 'system') {
  $mainPid = Start-AdPulseService -Module 'adpulse-main' -Arguments @('-f', 'adpulse-main\pom.xml', '-Dmaven.test.skip=true', $devToolsJvmArgument, 'spring-boot:run') -Environment $serviceEnvironment
}

if (-not $DisableHotReload) {
  $watcherPid = Start-HotReloadWatcher `
    -SelectedService $Service `
    -SystemProcessId $systemPid `
    -MainProcessId $mainPid
}

if ($Service -eq 'all') {
  Write-Output "Started system launcher PID $systemPid and main launcher PID $mainPid."
} elseif ($Service -eq 'system') {
  Write-Output "Started system launcher PID $systemPid."
} else {
  Write-Output "Started main launcher PID $mainPid."
}

if ($DisableHotReload) {
  Write-Output 'Backend automatic compilation and DevTools restart are disabled.'
} else {
  Write-Output "Started backend hot reload watcher PID $watcherPid."
}
