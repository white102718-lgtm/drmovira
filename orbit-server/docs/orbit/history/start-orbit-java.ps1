param(
    [string]$JavaHome = 'D:\progress\adpulse-power-system\.codex-toolchain\jdk',
    [string]$Maven = 'D:\progress\adpulse-power-system\.codex-toolchain\maven\bin\mvn.cmd'
)

$ErrorActionPreference = 'Stop'
$orbitServerRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$privateEnvironmentFile = 'D:\progress\adpulse-power-system\.env.local'

# 遵从本机约定，只从指定私有文件读取ORBIT_变量，不读取、回显或复用其他项目配置。
if (Test-Path -LiteralPath $privateEnvironmentFile) {
    foreach ($line in [System.IO.File]::ReadAllLines($privateEnvironmentFile)) {
        if ($line -match '^\s*(?:export\s+)?(ORBIT_[A-Z0-9_]+)\s*=(.*)$') {
            $variableName = $Matches[1]
            $variableValue = $Matches[2].Trim()
            if ($variableValue.Length -ge 2) {
                $first = $variableValue[0]
                $last = $variableValue[$variableValue.Length - 1]
                if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                    $variableValue = $variableValue.Substring(1, $variableValue.Length - 2)
                }
            }
            [Environment]::SetEnvironmentVariable($variableName, $variableValue, 'Process')
        }
    }
}

if ([string]::IsNullOrWhiteSpace($env:ORBIT_LOGIN_JWT_SECRET)) {
    throw '未配置ORBIT独立登录密钥，请在指定私有环境文件中配置后重试；不会使用默认密钥。'
}
if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\java.exe'))) {
    throw '未找到Java21，请指定JavaHome。'
}
if (-not (Test-Path -LiteralPath $Maven)) {
    throw '未找到Maven，请指定Maven路径。'
}

$env:JAVA_HOME = $JavaHome
$env:Path = (Join-Path $JavaHome 'bin') + [System.IO.Path]::PathSeparator + $env:Path
Push-Location -LiteralPath $orbitServerRoot
try {
    # 包含测试，不以跳过检查方式掩盖不完整交付；不自动创建或迁移数据库。
    & $Maven -B -ntp -pl ruoyi-admin -am package
    if ($LASTEXITCODE -ne 0) { throw 'ORBIT构建或测试失败，服务未启动。' }
    & (Join-Path $JavaHome 'bin\java.exe') -jar 'ruoyi-admin\target\ruoyi-admin.jar' '--spring.profiles.active=druid,orbit'
} finally {
    Pop-Location
}
