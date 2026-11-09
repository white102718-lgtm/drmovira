param([string]$MysqlHome = 'D:/progress/orbit/.toolchain/mysql-8.4.13-winx64')
$ErrorActionPreference = 'Stop'
$orbitWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$orbitRuntime = Join-Path $orbitWorkspace '.runtime/mysql-it'
$orbitData = Join-Path $orbitRuntime 'data'
$orbitPidFile = Join-Path $orbitRuntime 'process.id'
$orbitServer = [IO.Path]::GetFullPath((Join-Path $MysqlHome 'bin/mysqld.exe'))
if (-not (Test-Path -LiteralPath $orbitServer)) { throw '请先将官方MySQL8 ZIP解压到指定MysqlHome；不使用参考项目数据库。' }
$orbitListener = Get-NetTCPConnection -State Listen -LocalPort 13306 -ErrorAction SilentlyContinue
if ($orbitListener) {
    if (-not (Test-Path -LiteralPath $orbitPidFile)) { throw '13306端口被未知实例使用，不会停止或复用。' }
    $orbitOwnedPid = [int](Get-Content -LiteralPath $orbitPidFile)
    $orbitOwnedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $orbitOwnedPid"
    if (-not $orbitOwnedProcess -or $orbitOwnedProcess.ExecutablePath -ne $orbitServer -or -not $orbitOwnedProcess.CommandLine.Contains($orbitData.Replace('\', '/'))) { throw '进程身份不匹配，不会停止或复用。' }
    if ($orbitListener.OwningProcess -ne $orbitOwnedPid) {
        # Windows mysqld可能由启动进程派生服务子进程，必须核对父子关系、程序和目录。
        $orbitChild = Get-CimInstance Win32_Process -Filter "ProcessId = $($orbitListener.OwningProcess)"
        if (-not $orbitChild -or $orbitChild.ParentProcessId -ne $orbitOwnedPid -or $orbitChild.ExecutablePath -ne $orbitServer -or -not $orbitChild.CommandLine.Contains($orbitData.Replace('\', '/'))) { throw '监听进程不是已识别的本项目子进程。' }
        $orbitChild.ProcessId | Set-Content -LiteralPath $orbitPidFile
    }
    Write-Output 'ORBIT独立MySQL测试实例已运行于127.0.0.1:13306。'
    return
}
New-Item -ItemType Directory -Force -Path $orbitRuntime | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $orbitData 'auto.cnf'))) {
    if ((Test-Path -LiteralPath $orbitData) -and (Get-ChildItem -LiteralPath $orbitData -Force | Select-Object -First 1)) { throw '初始化目录非空，不会覆盖或清理。' }
    & $orbitServer '--no-defaults' '--initialize-insecure' "--basedir=$MysqlHome" "--datadir=$($orbitData.Replace('\', '/'))" "--log-error=$($orbitRuntime.Replace('\', '/'))/initialize.log"
    if ($LASTEXITCODE -ne 0) { throw '独立测试实例初始化失败。' }
}
# 仅回环地址、隔离端口和数据目录；空密码仅用于这台短期fixture实例，不用于应用部署。
$orbitProcess = Start-Process -FilePath $orbitServer -ArgumentList '--no-defaults',"--basedir=$MysqlHome","--datadir=$($orbitData.Replace('\', '/'))",'--bind-address=127.0.0.1','--port=13306','--mysqlx=OFF','--default-time-zone=+00:00',"--log-error=$($orbitRuntime.Replace('\', '/'))/error.log" -WindowStyle Hidden -PassThru
$orbitProcess.Id | Set-Content -LiteralPath $orbitPidFile
for ($orbitAttempt = 0; $orbitAttempt -lt 40; $orbitAttempt++) {
    $orbitReady = Get-NetTCPConnection -State Listen -LocalPort 13306 -ErrorAction SilentlyContinue
    if ($orbitReady) {
        $orbitChild = Get-CimInstance Win32_Process -Filter "ProcessId = $($orbitReady.OwningProcess)"
        if ($orbitChild -and ($orbitChild.ProcessId -eq $orbitProcess.Id -or $orbitChild.ParentProcessId -eq $orbitProcess.Id) -and $orbitChild.ExecutablePath -eq $orbitServer -and $orbitChild.CommandLine.Contains($orbitData.Replace('\', '/'))) {
            $orbitChild.ProcessId | Set-Content -LiteralPath $orbitPidFile
            Write-Output 'ORBIT独立MySQL测试实例已就绪于127.0.0.1:13306。'
            return
        }
        throw '监听进程身份不匹配。'
    }
    Start-Sleep -Milliseconds 250
}
throw '本项目MySQL测试实例未在就绪时间内启动，请核查本地错误日志。'
