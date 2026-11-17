param([string]$SentruxCommand = 'sentrux')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not (Get-Command $SentruxCommand -ErrorAction SilentlyContinue)) { throw 'Sentrux no disponible.' }
    if (Test-Path .sentrux/baseline.json) { & $SentruxCommand gate . } else { & $SentruxCommand gate --save . }
    if ($LASTEXITCODE -ne 0) { throw 'Fallo del control estructural.' }
    if (Test-Path .sentrux/rules.toml) {
        & $SentruxCommand check .
        if ($LASTEXITCODE -ne 0) { throw 'Fallo de reglas Sentrux.' }
    } else { Write-Output 'Sin reglas Sentrux locales; se verifica la regresión.' }
} finally { Pop-Location }
