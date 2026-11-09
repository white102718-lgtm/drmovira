param([string]$RedisHome = 'D:/progress/orbit/.toolchain/redis-it/Redis-8.10.3-Windows-x64-msys2')
$ErrorActionPreference = 'Stop'
$orbitWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$orbitRuntime = Join-Path $orbitWorkspace '.runtime/redis-it'
$orbitExe = [IO.Path]::GetFullPath((Join-Path $RedisHome 'redis-server.exe'))
$orbitPidFile = Join-Path $orbitRuntime 'process.id'
if (-not (Test-Path -LiteralPath $orbitExe)) { throw '缺少已校验的本项目Redis测试二进制。' }
$orbitListener = Get-NetTCPConnection -State Listen -LocalPort 16379 -ErrorAction SilentlyContinue
if ($orbitListener) {
    if (-not (Test-Path -LiteralPath $orbitPidFile)) { throw '16379被未知实例占用，不会复用或停止。' }
    $orbitOwnedPid = [int](Get-Content -LiteralPath $orbitPidFile)
    $orbitProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $orbitOwnedPid"
    if (-not $orbitProcess -or $orbitListener.OwningProcess -ne $orbitOwnedPid -or $orbitProcess.ExecutablePath -ne $orbitExe -or -not $orbitProcess.CommandLine.Contains($orbitRuntime.Replace('\','/'))) { throw 'Redis测试进程身份不匹配。' }
    Write-Output 'ORBIT独立Redis测试实例已运行。'; return
}
New-Item -ItemType Directory -Force -Path $orbitRuntime | Out-Null
# 只监听回环；关闭RDB/AOF，不注册系统服务，不清空或复用其他实例。
$orbitProcess = Start-Process -FilePath $orbitExe -ArgumentList '--bind','127.0.0.1','--port','16379','--protected-mode','yes','--appendonly','no','--save','""','--dir',$orbitRuntime.Replace('\','/'),'--logfile',"$($orbitRuntime.Replace('\','/'))/redis.log" -WorkingDirectory $RedisHome -WindowStyle Hidden -PassThru
$orbitProcess.Id | Set-Content -LiteralPath $orbitPidFile
for ($orbitAttempt = 0; $orbitAttempt -lt 40; $orbitAttempt++) {
    $orbitReady = Get-NetTCPConnection -State Listen -LocalPort 16379 -ErrorAction SilentlyContinue
    if ($orbitReady) {
        if ($orbitReady.OwningProcess -ne $orbitProcess.Id) { throw 'Redis监听PID不匹配，不会复用未知进程。' }
        Write-Output 'ORBIT独立Redis测试实例已就绪于127.0.0.1:16379。'; return
    }
    if ($orbitProcess.HasExited) { throw 'Redis测试进程启动失败。' }
    Start-Sleep -Milliseconds 250
}
throw 'Redis测试实例未就绪，请核查本项目运行日志。'
