$ErrorActionPreference = "Continue"
chcp.com 65001 | Out-Null

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$LauncherLog = Join-Path $LogDir "launcher.log"
$NapCatLauncher = $null
$ClaudeScript = $null
$ConfigUrl = "http://127.0.0.1:7070"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:A5_ROOT = $Root

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    Write-Host $Message
}

function Test-Port {
    param([int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(800)
        if ($ok) {
            $client.EndConnect($async)
            $client.Close()
            return $true
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

function Get-WebUiUrl {
    $webuiConfig = Join-Path $Root "NapCatCompat\NapCat.41785.Shell\versions\9.9.23-41785\resources\app\napcat\config\webui.json"
    if (Test-Path -LiteralPath $webuiConfig) {
        try {
            $data = Get-Content -Raw -Encoding UTF8 -LiteralPath $webuiConfig | ConvertFrom-Json
            $port = if ($data.port) { [int]$data.port } else { 6099 }
            $url = "http://127.0.0.1:$port/webui"
            if ($data.token) {
                $url = "$url?token=$($data.token)"
            }
            return $url
        } catch {
        }
    }
    return "http://127.0.0.1:6099/webui"
}

function Stop-A5Processes {
    $rootPattern = [regex]::Escape($Root)
    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and (
            ($_.CommandLine -match "main\.py") -or
            ($_.CommandLine -match "config_server\.py") -or
            ($_.Name -in @("A5Bot.exe", "A5Config.exe")) -or
            ($_.Name -eq "NapCatWinBootMain.exe") -or
            (($_.Name -eq "QQ.exe") -and ($_.ExecutablePath -like "$Root\NapCatCompat*")) -or
            (($_.Name -eq "powershell.exe") -and ($_.CommandLine -like "*NapCatQQ.ps1*"))
        )
    }
    foreach ($process in $targets) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-LauncherLog "Stopped $($process.Name) PID=$($process.ProcessId)"
        } catch {
            Write-LauncherLog "Failed to stop PID=$($process.ProcessId): $($_.Exception.Message)"
        }
    }
}

try {
    Write-LauncherLog "==== A5 startup begin ===="
    Write-LauncherLog "Root: $Root"
    $NapCatLauncher = (Get-ChildItem -LiteralPath $Root -Filter "*NapCatQQ.ps1" -File | Select-Object -First 1).FullName
    $ClaudeScript = (Get-ChildItem -LiteralPath $env:USERPROFILE -Filter "*ClaudeCode.bat" -File | Select-Object -First 1).FullName
    $WebUiUrl = Get-WebUiUrl
    Write-LauncherLog "NapCat launcher: $NapCatLauncher"
    Write-LauncherLog "Claude script: $ClaudeScript"

    Write-LauncherLog "[0/5] Cleaning old A5 processes"
    Stop-A5Processes
    Start-Sleep -Seconds 2

    Write-LauncherLog "[1/5] Claude Code terminal"
    if ($env:A5_START_CLAUDE_TERMINAL -eq "1") {
        if ($ClaudeScript -and (Test-Path -LiteralPath $ClaudeScript)) {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "call `"$ClaudeScript`"" -WindowStyle Normal
            Write-LauncherLog "Claude Code terminal launch command sent"
        } else {
            Write-LauncherLog "Claude Code script not found: $ClaudeScript"
        }
    } else {
        Write-LauncherLog "Skipped Claude Code terminal; Bot still uses claude command in background"
    }

    Write-LauncherLog "[2/5] Starting NapCatQQ"
    if (-not $NapCatLauncher -or -not (Test-Path -LiteralPath $NapCatLauncher)) {
        throw "NapCat launcher not found: $NapCatLauncher"
    }
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$NapCatLauncher`"" -WorkingDirectory $Root -WindowStyle Normal
    Start-Sleep -Seconds 8

    Write-LauncherLog "[3/5] Starting QQ Claude Bot in background"
    $botExe = Join-Path $Root "A5Bot.exe"
    if (Test-Path -LiteralPath $botExe) {
        Start-Process -FilePath $botExe -WorkingDirectory $Root -WindowStyle Hidden
    } else {
        Start-Process -FilePath "python.exe" -ArgumentList "main.py" -WorkingDirectory $Root -WindowStyle Hidden
    }
    Start-Sleep -Seconds 2

    Write-LauncherLog "[4/5] Starting config page server in background"
    $configExe = Join-Path $Root "A5Config.exe"
    if (Test-Path -LiteralPath $configExe) {
        Start-Process -FilePath $configExe -WorkingDirectory $Root -WindowStyle Hidden
    } else {
        Start-Process -FilePath "python.exe" -ArgumentList "config_server.py" -WorkingDirectory $Root -WindowStyle Hidden
    }
    Start-Sleep -Seconds 2

    Write-LauncherLog "[5/5] Opening browser pages"
    Start-Process $WebUiUrl
    Start-Process $ConfigUrl

    Start-Sleep -Seconds 2
    Write-LauncherLog "Port 6099 WebUI: $(if (Test-Port 6099) { 'OK' } else { 'NOT LISTENING' })"
    Write-LauncherLog "Port 3000 OneBot: $(if (Test-Port 3000) { 'OK' } else { 'NOT LISTENING' })"
    Write-LauncherLog "Port 18089 Bot: $(if (Test-Port 18089) { 'OK' } else { 'NOT LISTENING' })"
    Write-LauncherLog "Port 7070 Config: $(if (Test-Port 7070) { 'OK' } else { 'NOT LISTENING' })"
    Start-Sleep -Seconds 5
    Write-LauncherLog "Stable check 6099 WebUI: $(if (Test-Port 6099) { 'OK' } else { 'NOT LISTENING' })"
    Write-LauncherLog "Stable check 3000 OneBot: $(if (Test-Port 3000) { 'OK' } else { 'NOT LISTENING' })"
    Write-LauncherLog "==== A5 startup end ===="
    exit 0
} catch {
    Write-LauncherLog "STARTUP FAILED: $($_.Exception.Message)"
    exit 1
}
