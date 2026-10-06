#
# MCServer by Derpchees - desinstalador para Windows
#
# Quita el arranque con Windows, las reglas del firewall, los accesos
# directos y los programas (panel, Python, Java). Los mundos y respaldos se
# conservan salvo que se pida borrarlos.
#
#   -Yes           sin preguntas (lo usa el panel)
#   -PurgeData     borra tambien los mundos
#   -PurgeBackups  borra tambien los respaldos
#

param(
    [switch]$Yes,
    [switch]$PurgeData,
    [switch]$PurgeBackups
)

$ErrorActionPreference = "Continue"
$Dir = Split-Path $PSScriptRoot -Parent
$Lang = "en"

if ((Get-UICulture).TwoLetterISOLanguageName -eq "es") { $Lang = "es" }

function T([string]$es, [string]$en) {
    if ($Lang -eq "es") { return $es }
    return $en
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    $extra = @()
    if ($Yes) { $extra += "-Yes" }
    if ($PurgeData) { $extra += "-PurgeData" }
    if ($PurgeBackups) { $extra += "-PurgeBackups" }

    Start-Process powershell -Verb RunAs -ArgumentList (@("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"") + $extra)
    return
}

# Rutas reales (el panel puede haberlas cambiado)
$config = @{}
$configFile = Join-Path $Dir "config.env"

if (Test-Path $configFile) {
    foreach ($line in Get-Content $configFile -Encoding UTF8) {
        if ($line -match '^\s*([A-Z_]+)\s*=\s*"?(.*?)"?\s*$') { $config[$Matches[1]] = $Matches[2] }
    }
}

$dataDir = $config["DATA_ROOT"]
$backupDir = $config["BACKUP_ROOT"]
if (-not $dataDir) { $dataDir = Join-Path $Dir "servers" }
if (-not $backupDir) { $backupDir = Join-Path $Dir "backups" }

if (-not $Yes) {
    Write-Host ""
    Write-Host (T "Desinstalar MCServer de $Dir" "Uninstall MCServer from $Dir") -ForegroundColor Yellow
    $answer = Read-Host (T "Escribe SI para continuar" "Type YES to continue")

    if ($answer -notin @("SI", "SÍ", "si", "sí", "YES", "yes")) {
        Write-Host (T "Cancelado." "Cancelled.")
        return
    }

    $PurgeData = (Read-Host (T "Borrar tambien los mundos? (s/N)" "Also delete the worlds? (y/N)")) -match '^[sSyY]'
    $PurgeBackups = (Read-Host (T "Borrar tambien los respaldos? (s/N)" "Also delete the backups? (y/N)")) -match '^[sSyY]'
}

Write-Host (T "Deteniendo MCServer y sus servidores..." "Stopping MCServer and its servers...")
Stop-ScheduledTask -TaskName "MCServer" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "MCServer" -Confirm:$false -ErrorAction SilentlyContinue

# Todo lo que corre desde la carpeta (panel, vigilantes, Java, Bedrock),
# menos esta misma ventana
Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and (
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($Dir, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -like "*$Dir*" -and $_.Name -notlike "powershell*"))
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2

Get-NetFirewallRule -Group "MCServer" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Remove-Item (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\MCServer") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "MCServer.url") -Force -ErrorAction SilentlyContinue

foreach ($name in @("app", "python", "java", "run", "logs", "state", "config.env")) {
    Remove-Item (Join-Path $Dir $name) -Recurse -Force -ErrorAction SilentlyContinue
}

if ($PurgeData) { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }
if ($PurgeBackups) { Remove-Item $backupDir -Recurse -Force -ErrorAction SilentlyContinue }

# La carpeta se quita si quedo vacia
if ((Test-Path $Dir) -and -not (Get-ChildItem $Dir -Force)) {
    Remove-Item $Dir -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host (T "MCServer se desinstalo." "MCServer was uninstalled.") -ForegroundColor Green

if (Test-Path $Dir) {
    Write-Host (T "Lo que se conservo sigue en $Dir" "What was kept is still in $Dir")
}
