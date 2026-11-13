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

# Registro en la carpeta temporal de Windows (la de MCServer se borra)
$logFile = Join-Path ([IO.Path]::GetTempPath()) "mcserver-uninstall.log"
try { Start-Transcript -Path $logFile -Force | Out-Null } catch {}

# Desde el panel: deja que conteste la peticion antes de detenerlo
if ($Yes) { Start-Sleep -Seconds 3 }

Write-Host (T "Deteniendo MCServer y sus servidores..." "Stopping MCServer and its servers...")

# Primero se quita la tarea para que no vuelva a encender el panel al
# matarlo (tiene reinicio automatico); luego se detiene lo que corre
Unregister-ScheduledTask -TaskName "MCServer" -Confirm:$false -ErrorAction SilentlyContinue
& schtasks.exe /End /TN "MCServer" 2>$null | Out-Null
& schtasks.exe /Delete /TN "MCServer" /F 2>$null | Out-Null

# Esta ventana y sus padres no se tocan (taskkill /T mataria tambien a esta)
$keep = @{}
$cursor = $PID
while ($cursor -and -not $keep.ContainsKey([int]$cursor)) {
    $keep[[int]$cursor] = $true
    $cursor = (Get-CimInstance Win32_Process -Filter "ProcessId=$cursor" -ErrorAction SilentlyContinue).ParentProcessId
}

function Stop-McProcesses {
    # Todo lo que corre desde la carpeta (panel, vigilantes, Java, Bedrock),
    # menos esta misma ventana
    $found = @(Get-CimInstance Win32_Process | Where-Object {
        -not $keep.ContainsKey([int]$_.ProcessId) -and (
            ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($Dir, [StringComparison]::OrdinalIgnoreCase)) -or
            ($_.CommandLine -and $_.CommandLine -like "*$Dir*" -and $_.Name -notlike "powershell*"))
    })

    foreach ($proc in $found) {
        Write-Host ("  - {0} ({1})" -f $proc.Name, $proc.ProcessId)
        & taskkill.exe /F /T /PID $proc.ProcessId 2>$null | Out-Null
    }

    return $found.Count
}

# Varias pasadas: un vigilante puede alcanzar a lanzar algo antes de morir
for ($i = 0; $i -lt 5; $i++) {
    if ((Stop-McProcesses) -eq 0) { break }
    Start-Sleep -Seconds 2
}

function Remove-Retry([string]$path) {
    # Algun archivo puede seguir en uso unos segundos
    for ($i = 0; $i -lt 10 -and (Test-Path -LiteralPath $path); $i++) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $path) { Start-Sleep -Seconds 1 }
    }

    if (Test-Path -LiteralPath $path) {
        Write-Host ((T "No se pudo borrar: " "Could not delete: ") + $path) -ForegroundColor Red
    }
}

Get-NetFirewallRule -Group "MCServer" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Remove-Item (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\MCServer") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "MCServer.url") -Force -ErrorAction SilentlyContinue

foreach ($name in @("app", "python", "java", "run", "logs", "state", "config.env")) {
    Remove-Retry (Join-Path $Dir $name)
}

if ($PurgeData) { Remove-Retry $dataDir }
if ($PurgeBackups) { Remove-Retry $backupDir }

# La tarea de una sola vez con la que el panel lanzo esto
Unregister-ScheduledTask -TaskName "MCServer Uninstall" -Confirm:$false -ErrorAction SilentlyContinue

# La carpeta se quita si quedo vacia
if ((Test-Path $Dir) -and -not (Get-ChildItem $Dir -Force)) {
    Remove-Item $Dir -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host (T "MCServer se desinstalo." "MCServer was uninstalled.") -ForegroundColor Green

if (Test-Path $Dir) {
    Write-Host (T "Lo que se conservo sigue en $Dir" "What was kept is still in $Dir")
}

Write-Host ((T "Registro: " "Log: ") + $logFile)
try { Stop-Transcript | Out-Null } catch {}

# Desde el acceso directo la ventana no se cierra sin que se lea
if (-not $Yes) { Read-Host (T "Enter para cerrar" "Press Enter to close") | Out-Null }
