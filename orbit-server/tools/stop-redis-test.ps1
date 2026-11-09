param([string]$RedisHome = 'D:/progress/orbit/.toolchain/redis-it/Redis-8.10.3-Windows-x64-msys2')
$ErrorActionPreference = 'Stop'
$orbitWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$orbitRuntime = Join-Path $orbitWorkspace '.runtime/redis-it'
$orbitPidFile = Join-Path $orbitRuntime 'process.id'
if (-not (Test-Path -LiteralPath $orbitPidFile)) { throw '缺少本项目Redis PID，不会停止任何实例。' }
$orbitOwnedPid = [int](Get-Content -LiteralPath $orbitPidFile)
$orbitProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $orbitOwnedPid"
if (-not $orbitProcess) { Write-Output '本项目Redis测试实例已停止。'; return }
$orbitExe = [IO.Path]::GetFullPath((Join-Path $RedisHome 'redis-server.exe'))
$orbitListener = Get-NetTCPConnection -State Listen -LocalPort 16379 -ErrorAction SilentlyContinue
if ($orbitProcess.ExecutablePath -ne $orbitExe -or -not $orbitProcess.CommandLine.Contains($orbitRuntime.Replace('\','/')) -or -not $orbitListener -or $orbitListener.OwningProcess -ne $orbitOwnedPid) { throw 'Redis测试实例身份不匹配，不会发出停止指令。' }
& (Join-Path $RedisHome 'redis-cli.exe') '-h' '127.0.0.1' '-p' '16379' 'SHUTDOWN' 'NOSAVE'
if ($LASTEXITCODE -ne 0) { throw '本项目Redis测试实例停止失败。' }
$orbitWaiting = Get-Process -Id $orbitOwnedPid -ErrorAction SilentlyContinue
if ($orbitWaiting -and -not $orbitWaiting.WaitForExit(15000)) { throw '本项目Redis仍在退出。' }
Write-Output 'ORBIT独立Redis测试实例已停止。'
