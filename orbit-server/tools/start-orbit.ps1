param([int]$Port = 18083)

$ErrorActionPreference = 'Stop'
$orbitServerRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonExecutable = Join-Path $orbitServerRoot '.venv/Scripts/python.exe'
$pythonFramework = Join-Path $orbitServerRoot 'python/ruoyi_fastapi'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw '请先安装ORBIT Python独立虚拟环境与锁定依赖。' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw '目标端口已被使用；不会停止现有进程。' }
# 后端配置由Python唯一加载指定私有文件，启动器不读取、打印或导出凭据。
$env:PYTHONPATH = (Join-Path $orbitServerRoot 'python') + [System.IO.Path]::PathSeparator + $pythonFramework
Push-Location $pythonFramework
try {
    & $pythonExecutable -m uvicorn 'orbit_api.application:create_app' --factory --host 127.0.0.1 --port $Port --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'ORBIT Python启动失败；请核对独立配置及已审核数据库结构。' }
} finally { Pop-Location }
