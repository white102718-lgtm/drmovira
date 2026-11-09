param([string]$MysqlHome = 'D:/progress/orbit/.toolchain/mysql-8.4.13-winx64')
$ErrorActionPreference = 'Stop'
$orbitWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$orbitRuntime = Join-Path $orbitWorkspace '.runtime/mysql-it'
$orbitPidFile = Join-Path $orbitRuntime 'process.id'
if (-not (Test-Path -LiteralPath $orbitPidFile)) { throw '缺少本项目测试实例PID，不会停止任何进程。' }
$orbitOwnedPid = [int](Get-Content -LiteralPath $orbitPidFile)
$orbitProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $orbitOwnedPid"
if (-not $orbitProcess) { Write-Output '本项目测试实例已停止。'; return }
$orbitServer = [IO.Path]::GetFullPath((Join-Path $MysqlHome 'bin/mysqld.exe'))
$orbitData = (Join-Path $orbitRuntime 'data').Replace('\', '/')
if ($orbitProcess.ExecutablePath -ne $orbitServer -or -not $orbitProcess.CommandLine.Contains($orbitData)) { throw 'PID不属于本项目测试实例，不会停止。' }
$orbitListener = Get-NetTCPConnection -State Listen -LocalPort 13306 -ErrorAction SilentlyContinue
if (-not $orbitListener -or $orbitListener.OwningProcess -ne $orbitOwnedPid) { throw '端口与进程身份不匹配，不会发出停止命令。' }
& (Join-Path $MysqlHome 'bin/mysqladmin.exe') '--no-defaults' '--protocol=TCP' '--host=127.0.0.1' '--port=13306' '--user=root' 'shutdown'
if ($LASTEXITCODE -ne 0) { throw '本项目测试实例正常停止失败；不会强制结束其他进程。' }
# mysqladmin返回时InnoDB可能仍在释放文件，必须等待已识别实例退出后才允许重启。
$orbitWaiting = Get-Process -Id $orbitOwnedPid -ErrorAction SilentlyContinue
if ($orbitWaiting -and -not $orbitWaiting.WaitForExit(15000)) { throw '本项目实例仍在正常关闭，暂不允许重启。' }
Write-Output 'ORBIT独立MySQL测试实例已停止，数据目录保留。'
