#
# MCServer by Derpchees - instalador para Windows
# https://github.com/Derpchees/mcserver
#
# Uso (PowerShell):
#   irm https://raw.githubusercontent.com/Derpchees/mcserver/main/install.ps1 | iex
#
# Todo queda en una carpeta (C:\MCServer por defecto): el panel, un Python
# portatil, Java (se baja solo, por version), los servidores y respaldos.
# No usa Docker: cada servidor es un programa normal. El panel arranca con
# Windows (tarea "MCServer" del Programador de tareas, como SYSTEM).
# La cuenta de administrador se crea despues en el navegador.
#
# Parametros (los usa el boton Actualizar del panel):
#   -Update      actualiza el panel; conserva cuentas, servidores y mundos
#   -Dir <ruta>  carpeta de instalacion
#   -Port <n>    puerto del panel (solo instalacion nueva)
#   -Lang es|en  idioma del instalador
#

param(
    [switch]$Update,
    [string]$Dir = "",
    [int]$Port = 0,
    [string]$Lang = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = "Derpchees/mcserver"
$Branch = "main"
$RawUrl = "https://raw.githubusercontent.com/$Repo/$Branch/install.ps1"
$ZipUrl = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
$PyVersion = "3.12.10"
$PyUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$TaskName = "MCServer"
$FirewallGroup = "MCServer"
$DefaultDir = "C:\MCServer"

if (-not $Lang) {
    $Lang = "en"

    if ((Get-UICulture).TwoLetterISOLanguageName -eq "es") {
        $Lang = "es"
    }
}

function T([string]$es, [string]$en) {
    if ($Lang -eq "es") { return $es }
    return $en
}

function Step([string]$es, [string]$en) {
    Write-Host ""
    Write-Host ("==> " + (T $es $en)) -ForegroundColor Green
}

function Fail([string]$es, [string]$en) {
    Write-Host ""
    Write-Host (T $es $en) -ForegroundColor Red
    throw (T $es $en)
}


# ============================================================
# Permisos de administrador
# ============================================================

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host (T "MCServer necesita permisos de administrador (firewall y arranque con Windows)." `
                  "MCServer needs administrator rights (firewall and start with Windows).")
    Write-Host (T "Acepta la ventana de Windows que va a aparecer." "Accept the Windows prompt that will appear.")

    $extra = ""
    if ($Update) { $extra += " -Update" }
    if ($Dir) { $extra += " -Dir '" + $Dir.Replace("'", "''") + "'" }
    if ($Port) { $extra += " -Port $Port" }
    $extra += " -Lang $Lang"

    if ($PSCommandPath) {
        $command = "& ([scriptblock]::Create([IO.File]::ReadAllText('" + $PSCommandPath.Replace("'", "''") + "', [Text.Encoding]::UTF8)))$extra"
    } else {
        $command = "& ([scriptblock]::Create((Invoke-RestMethod -UseBasicParsing '$RawUrl')))$extra"
    }

    Start-Process powershell -Verb RunAs -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $command)
    return
}


# ============================================================
# Carpeta y puerto
# ============================================================

function Read-Config([string]$path) {
    $values = @{}

    if (Test-Path $path) {
        foreach ($line in Get-Content $path -Encoding UTF8) {
            if ($line -match '^\s*([A-Z_]+)\s*=\s*"?(.*?)"?\s*$') {
                $values[$Matches[1]] = $Matches[2]
            }
        }
    }

    return $values
}

Write-Host ""
Write-Host "MCServer by Derpchees" -ForegroundColor Cyan
Write-Host (T "Servidores de Minecraft (Java y Bedrock) con panel web, en Windows." `
              "Minecraft servers (Java and Bedrock) with a web panel, on Windows.")

if (-not $Dir) {
    if ($Update -or (Test-Path (Join-Path $DefaultDir "config.env"))) {
        $Dir = $DefaultDir
    } else {
        Write-Host ""
        $answer = Read-Host (T "Carpeta de instalacion (Enter = $DefaultDir)" "Install folder (Enter = $DefaultDir)")
        $Dir = $DefaultDir
        if ($answer.Trim()) { $Dir = $answer.Trim().Trim('"') }
    }
}

$Dir = [IO.Path]::GetFullPath($Dir).TrimEnd("\")
$ConfigFile = Join-Path $Dir "config.env"
$existing = Test-Path $ConfigFile

if ($Update -and -not $existing) {
    Fail "No se encontro una instalacion en $Dir" "No installation found in $Dir"
}

$config = Read-Config $ConfigFile

if ($existing) {
    $Port = [int]$config["PANEL_PORT"]
    if (-not $Update) {
        Write-Host (T "MCServer ya esta instalado en $Dir : se actualiza (cuentas, servidores y mundos se conservan)." `
                      "MCServer is already installed in $Dir : updating it (accounts, servers and worlds are kept).")
        $Update = $true
    }
} elseif (-not $Port) {
    $answer = Read-Host (T "Puerto del panel (Enter = 8090)" "Panel port (Enter = 8090)")
    $Port = 8090
    if ($answer.Trim()) { $Port = [int]$answer.Trim() }
}

if (-not $Port) { $Port = 8090 }

$AppDir = Join-Path $Dir "app"
$PyDir = Join-Path $Dir "python"
$PyExe = Join-Path $PyDir "python.exe"
$PywExe = Join-Path $PyDir "pythonw.exe"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null


# ============================================================
# Codigo del panel
# ============================================================

Step "Descargando MCServer" "Downloading MCServer"

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("mcserver-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

try {
    Invoke-WebRequest -UseBasicParsing $ZipUrl -OutFile (Join-Path $tmp "src.zip")
    Expand-Archive (Join-Path $tmp "src.zip") -DestinationPath $tmp -Force
    $src = Get-ChildItem $tmp -Directory | Select-Object -First 1

    $versionLine = Select-String -Path (Join-Path $src.FullName "install.sh") -Pattern '^VERSION="([^"]+)"' | Select-Object -First 1
    $Version = "dev"
    if ($versionLine) { $Version = $versionLine.Matches[0].Groups[1].Value }
    Write-Host ("MCServer " + $Version)

    # Al actualizar: se cierran el panel y el agente; los servidores siguen
    if ($Update) {
        Step "Deteniendo el panel (los servidores siguen encendidos)" "Stopping the panel (servers keep running)"
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

        Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object {
            $_.CommandLine -and $_.CommandLine -like "*$AppDir*" -and
            ($_.CommandLine -like "*service.py*" -or $_.CommandLine -like "*mcpanel.py*" -or $_.CommandLine -like "*mcpanel-agent.py*")
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

        Start-Sleep -Seconds 2
    }

    Step "Copiando archivos a $AppDir" "Copying files to $AppDir"
    robocopy $src.FullName $AppDir /MIR /XD .git /NFL /NDL /NJH /NJS /NP | Out-Null

    if ($LASTEXITCODE -ge 8) {
        Fail "No se pudieron copiar los archivos (robocopy $LASTEXITCODE)" "Could not copy the files (robocopy $LASTEXITCODE)"
    }

    $global:LASTEXITCODE = 0
    Set-Content -Path (Join-Path $AppDir "VERSION") -Value $Version -Encoding ASCII
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}


# ============================================================
# Python portatil (sin instalar nada en el sistema)
# ============================================================

if (-not (Test-Path $PywExe)) {
    Step "Descargando Python $PyVersion (portatil)" "Downloading Python $PyVersion (portable)"
    $pyZip = Join-Path $Dir "python.zip"
    Invoke-WebRequest -UseBasicParsing $PyUrl -OutFile $pyZip
    Expand-Archive $pyZip -DestinationPath $PyDir -Force
    Remove-Item $pyZip -Force
}

# El Python portatil solo busca modulos donde dice este archivo
$pth = Get-ChildItem $PyDir -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem $PyDir -Filter "python*.zip" | Select-Object -First 1).Name
Set-Content -Path $pth.FullName -Value @($zipName, ".", "..\app\panel") -Encoding ASCII


# ============================================================
# Configuracion
# ============================================================

function Lan-IP {
    try {
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Sort-Object RouteMetric | Select-Object -First 1
        $ip = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 -ErrorAction Stop | Select-Object -First 1
        return $ip.IPAddress
    } catch {
        return "localhost"
    }
}

if (-not $existing) {
    Step "Creando la configuracion" "Creating the configuration"
    $slash = $Dir.Replace("\", "/")
    $lines = @(
        'SYSTEM_NAME="MCServer"',
        ('LANG_DEFAULT="' + $Lang + '"'),
        ('INSTALL_DIR="' + $slash + '/app"'),
        ('DATA_ROOT="' + $slash + '/servers"'),
        ('BACKUP_ROOT="' + $slash + '/backups"'),
        ('LOG_DIR="' + $slash + '/logs"'),
        ('STATE_DIR="' + $slash + '/state"'),
        ('RUN_DIR="' + $slash + '/run"'),
        ('JAVA_DIR="' + $slash + '/java"'),
        ('PANEL_PORT="' + $Port + '"'),
        'PANEL_BIND="0.0.0.0"',
        'LISTEN_IP="0.0.0.0"',
        ('PUBLIC_HOST="' + (Lan-IP) + '"'),
        'GAME_PORT_START="25565"',
        'BEDROCK_PORT_START="19132"',
        'INTERNAL_PORT_START="35565"',
        'RUNTIME="native"'
    )
    [IO.File]::WriteAllLines($ConfigFile, $lines)
    $config = Read-Config $ConfigFile
}

& $PyExe (Join-Path $AppDir "panel\mcpanel_core.py") init | Out-Null

if ($LASTEXITCODE -ne 0) {
    Fail "No se pudo preparar la base de datos" "Could not prepare the database"
}


# ============================================================
# Firewall: el panel y los puertos de juego
# ============================================================

Step "Abriendo los puertos en el Firewall de Windows" "Opening the ports in Windows Firewall"

$javaStart = [int]$config["GAME_PORT_START"]
$bedrockStart = [int]$config["BEDROCK_PORT_START"]
if (-not $javaStart) { $javaStart = 25565 }
if (-not $bedrockStart) { $bedrockStart = 19132 }

Get-NetFirewallRule -Group $FirewallGroup -ErrorAction SilentlyContinue | Remove-NetFirewallRule

$rules = @(
    @{ Name = "MCServer panel"; Protocol = "TCP"; Port = "$Port" },
    @{ Name = "MCServer Java"; Protocol = "TCP"; Port = "$javaStart-$($javaStart + 49)" },
    @{ Name = "MCServer Bedrock (TCP)"; Protocol = "TCP"; Port = "$bedrockStart-$($bedrockStart + 49)" },
    @{ Name = "MCServer Bedrock (UDP)"; Protocol = "UDP"; Port = "$bedrockStart-$($bedrockStart + 999)" }
)

foreach ($rule in $rules) {
    New-NetFirewallRule -DisplayName $rule.Name -Group $FirewallGroup -Direction Inbound -Action Allow `
        -Protocol $rule.Protocol -LocalPort $rule.Port -Profile Any | Out-Null
}

# Minecraft Bedrock de la Tienda no puede conectarse a este mismo equipo sin esto
CheckNetIsolation.exe LoopbackExempt -a -n="Microsoft.MinecraftUWP_8wekyb3d8bbwe" 2>$null | Out-Null
$global:LASTEXITCODE = 0


# ============================================================
# Arranque con Windows
# ============================================================

Step "Configurando el arranque con Windows" "Setting up start with Windows"

$action = New-ScheduledTaskAction -Execute $PywExe -Argument ('"' + (Join-Path $AppDir "panel\native\service.py") + '"') -WorkingDirectory (Join-Path $AppDir "panel")
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "MCServer by Derpchees: panel web y servidores de Minecraft" -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName


# ============================================================
# Accesos directos
# ============================================================

$menu = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\MCServer"
New-Item -ItemType Directory -Force -Path $menu | Out-Null

$panelUrl = "http://localhost:$Port/"
Set-Content -Path (Join-Path $menu "MCServer.url") -Value @("[InternetShortcut]", "URL=$panelUrl") -Encoding ASCII

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $menu (T "Desinstalar MCServer.lnk" "Uninstall MCServer.lnk")))
$link.TargetPath = "powershell.exe"
$link.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $AppDir "uninstall.ps1") + '"'
$link.Save()

if (-not $Update) {
    $desktop = [Environment]::GetFolderPath("CommonDesktopDirectory")
    Set-Content -Path (Join-Path $desktop "MCServer.url") -Value @("[InternetShortcut]", "URL=$panelUrl") -Encoding ASCII
}


# ============================================================
# Listo
# ============================================================

Step "Esperando al panel" "Waiting for the panel"

$ready = $false

for ($i = 0; $i -lt 40; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/" -TimeoutSec 3 | Out-Null
        $ready = $true
        break
    } catch {
        if ($_.Exception.Response) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
}

Write-Host ""

if (-not $ready) {
    Write-Host (T "El panel tarda en responder. Revisa $Dir\logs\web.log" "The panel is slow to answer. Check $Dir\logs\web.log") -ForegroundColor Yellow
}

if ($Update) {
    Write-Host (T "MCServer actualizado a la $Version." "MCServer updated to $Version.") -ForegroundColor Green
} else {
    $lan = Lan-IP
    Write-Host (T "MCServer quedo instalado en $Dir" "MCServer is installed in $Dir") -ForegroundColor Green
    Write-Host ""
    Write-Host (T "Panel en este equipo:   $panelUrl" "Panel on this computer: $panelUrl")
    Write-Host (T "Desde otros aparatos:   http://${lan}:$Port/" "From other devices:     http://${lan}:$Port/")
    Write-Host ""
    Write-Host (T "Abre el panel y crea la cuenta de administrador. Arranca solo con Windows." `
                  "Open the panel and create the administrator account. It starts with Windows.")
    Start-Process $panelUrl
}
