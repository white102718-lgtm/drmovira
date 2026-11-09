# Watches local backend sources, compiles the changed service, and triggers
# Spring Boot DevTools only after a successful compilation.
param(
  [ValidateSet('all', 'main', 'system')]
  [string]$Service = 'all',
  [ValidateRange(250, 5000)]
  [int]$DebounceMilliseconds = 750,
  [int]$SystemProcessId = 0,
  [int]$MainProcessId = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$mavenCommand = Join-Path $projectRoot '.codex-toolchain\maven\bin\mvn.cmd'
$javaHome = Join-Path $projectRoot '.codex-toolchain\jdk'
$triggerFileName = '.reloadtrigger'
$watchers = [System.Collections.Generic.List[System.IO.FileSystemWatcher]]::new()
$sourceIdentifiers = [System.Collections.Generic.List[string]]::new()
$pendingServices = @{}
$commonChangePending = $false
$lastChangeAt = [DateTime]::MinValue

$serviceConfigurations = @{}

if ($Service -ne 'main') {
  $serviceConfigurations['system'] = @{
    Module = 'adpulse-system'
    ProcessId = $SystemProcessId
  }
}

if ($Service -ne 'system') {
  $serviceConfigurations['main'] = @{
    Module = 'adpulse-main'
    ProcessId = $MainProcessId
  }
}

function Test-ServiceProcess {
  param(
    [hashtable]$Configuration
  )

  if ($Configuration.ProcessId -le 0) {
    return $true
  }

  return $null -ne (Get-Process -Id $Configuration.ProcessId -ErrorAction SilentlyContinue)
}

function Add-SourceWatcher {
  param(
    [string]$SourceName,
    [string]$SourcePath
  )

  if (-not (Test-Path -LiteralPath $SourcePath -PathType Container)) {
    throw "Missing source directory: $SourcePath"
  }

  $watcher = [System.IO.FileSystemWatcher]::new($SourcePath)
  $watcher.IncludeSubdirectories = $true
  $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, Size'

  foreach ($eventName in @('Changed', 'Created', 'Deleted', 'Renamed')) {
    $sourceIdentifier = "adpulse-hot-reload|$SourceName|$eventName"
    Register-ObjectEvent `
      -InputObject $watcher `
      -EventName $eventName `
      -SourceIdentifier $sourceIdentifier | Out-Null
    $sourceIdentifiers.Add($sourceIdentifier)
  }

  $watcher.EnableRaisingEvents = $true
  $watchers.Add($watcher)
}

function Invoke-ServiceCompile {
  param(
    [string]$ServiceName,
    [hashtable]$Configuration
  )

  if (-not (Test-ServiceProcess $Configuration)) {
    Write-Warning "$ServiceName is no longer running; skipped automatic compilation."
    return
  }

  $module = $Configuration.Module
  $pomPath = Join-Path $projectRoot "$module\pom.xml"
  Write-Host "[$ServiceName hot reload] Compiling changed sources..."

  & $mavenCommand -f $pomPath '-Dmaven.test.skip=true' compile

  if ($LASTEXITCODE -ne 0) {
    Write-Warning "[$ServiceName hot reload] Compilation failed. The running service keeps its previous reload state; save another change to retry."
    return
  }

  $triggerFile = Join-Path $projectRoot "$module\target\classes\$triggerFileName"
  $triggerDirectory = Split-Path -Parent $triggerFile
  New-Item -ItemType Directory -Force -Path $triggerDirectory | Out-Null

  if (Test-Path -LiteralPath $triggerFile) {
    [System.IO.File]::SetLastWriteTimeUtc($triggerFile, [DateTime]::UtcNow)
  } else {
    [System.IO.File]::WriteAllText($triggerFile, '')
  }

  Write-Host "[$ServiceName hot reload] Compilation succeeded; DevTools reload requested."
}

function Receive-SourceEvents {
  param(
    [System.Management.Automation.PSEventArgs]$FirstEvent
  )

  $eventRecord = $FirstEvent

  while ($null -ne $eventRecord) {
    $identifierParts = $eventRecord.SourceIdentifier.Split('|')
    $sourceName = $identifierParts[1]
    Remove-Event -EventIdentifier $eventRecord.EventIdentifier

    if ($sourceName -eq 'common') {
      $script:commonChangePending = $true
    } else {
      $script:pendingServices[$sourceName] = $true
    }

    $script:lastChangeAt = [DateTime]::UtcNow
    $eventRecord = Get-Event | Select-Object -First 1
  }
}

if (-not (Test-Path -LiteralPath $mavenCommand -PathType Leaf)) {
  throw "Missing Maven command: $mavenCommand"
}

if (-not (Test-Path -LiteralPath $javaHome -PathType Container)) {
  throw "Missing local JDK: $javaHome"
}

$env:JAVA_HOME = $javaHome

try {
  foreach ($entry in $serviceConfigurations.GetEnumerator()) {
    $moduleSourceRoot = Join-Path $projectRoot "$($entry.Value.Module)\src\main"
    Add-SourceWatcher -SourceName $entry.Key -SourcePath $moduleSourceRoot
  }

  Add-SourceWatcher `
    -SourceName 'common' `
    -SourcePath (Join-Path $projectRoot 'adpulse-common\src\main')

  $watchedServices = ($serviceConfigurations.Keys | Sort-Object) -join ', '
  Write-Host "Backend hot reload watcher started for: $watchedServices."
  Write-Host 'Changes under adpulse-common require restarting the affected services.'

  while ($true) {
    $activeServiceCount = @(
      $serviceConfigurations.Values | Where-Object { Test-ServiceProcess $_ }
    ).Count

    if ($activeServiceCount -eq 0) {
      Write-Host 'Backend services stopped; hot reload watcher is exiting.'
      break
    }

    $firstEvent = Wait-Event -Timeout 1

    if ($null -ne $firstEvent) {
      Receive-SourceEvents -FirstEvent $firstEvent
    }

    if ($lastChangeAt -eq [DateTime]::MinValue) {
      continue
    }

    $millisecondsSinceLastChange = ([DateTime]::UtcNow - $lastChangeAt).TotalMilliseconds

    if ($millisecondsSinceLastChange -lt $DebounceMilliseconds) {
      continue
    }

    if ($commonChangePending) {
      Write-Warning 'adpulse-common changed. Automatic compilation and reload are not configured for this module; restart the affected backend services.'
      $commonChangePending = $false
    }

    $servicesToCompile = @($pendingServices.Keys | Sort-Object)
    $pendingServices.Clear()
    $lastChangeAt = [DateTime]::MinValue

    foreach ($serviceName in $servicesToCompile) {
      Invoke-ServiceCompile `
        -ServiceName $serviceName `
        -Configuration $serviceConfigurations[$serviceName]
    }
  }
} finally {
  foreach ($sourceIdentifier in $sourceIdentifiers) {
    Unregister-Event -SourceIdentifier $sourceIdentifier -ErrorAction SilentlyContinue
  }

  foreach ($watcher in $watchers) {
    $watcher.Dispose()
  }
}
