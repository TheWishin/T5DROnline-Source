<#
.SYNOPSIS
  Keep a T5DR lobby server running in the background on this Windows PC: a scheduled task that
  starts with Windows (or at your logon), restarts after a crash, and runs as you with normal
  rights. For a player who hosts friends permanently; to host only while you play, use
  host-for-friends.cmd or the launcher's "Host for friends" instead.

.DESCRIPTION
  Registers the task "T5DR Lobby Server" running
      <release>\python\pythonw.exe <release>\lobby\run.py host --port 7781 [--map-ports]
  Data, logs (rotated) and daily backups: %LOCALAPPDATA%\T5DR Online\lobby-host.
  Registering a task that runs without you being logged on needs an administrator console.
  -OpenFirewall adds inbound Windows Firewall rules for that python.exe and the lobby ports only.
  -DryRun prints everything it would do and changes nothing (no administrator needed).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install-task.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File install-task.ps1 -OpenFirewall
  powershell -ExecutionPolicy Bypass -File install-task.ps1 -Uninstall
#>
param(
    [switch]$DryRun,
    [switch]$Uninstall,
    [switch]$OpenFirewall,
    [switch]$MapPorts,
    [switch]$AtLogon,
    [int]$Port = 7781,
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "T5DR Online\lobby-host")
)
$ErrorActionPreference = "Stop"
$TaskName = "T5DR Lobby Server"
$RulePrefix = "T5DR lobby"
$Lobby = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# The release zip's own Python (pythonw: no console window), else an installed one.
$Python = Join-Path $Lobby "..\python\pythonw.exe"
if (Test-Path $Python) {
    $Python = (Resolve-Path $Python).Path
} else {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "No Python found (expected $Python, or pythonw.exe on PATH)." }
    $Python = $cmd.Source
}
$Arguments = "`"$Lobby\run.py`" host --port $Port --data `"$DataDir`""
if ($MapPorts) { $Arguments += " --map-ports" }
$User = "$env:USERDOMAIN\$env:USERNAME"

function Step([string]$What, [scriptblock]$Action) {
    if ($DryRun) { Write-Host "[dry run] $What" } else { Write-Host $What; & $Action }
}

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $DryRun -and -not $IsAdmin) {
    throw "Run this from an administrator PowerShell (or add -DryRun to see what it would do)."
}

if ($Uninstall) {
    Step "Stop and remove the scheduled task '$TaskName'" {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    Step "Remove the firewall rules '$RulePrefix *'" {
        Get-NetFirewallRule -DisplayName "$RulePrefix *" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    Write-Host "Kept: $DataDir (database, certificate, logs, backups)."
    return
}

Write-Host "Python:    $Python"
Write-Host "Command:   $Python $Arguments"
Write-Host "Runs as:   $User ($(if ($AtLogon) {'at your logon'} else {'at Windows start, logged on or not'}))"

Step "Register the scheduled task '$TaskName' (restarts every minute after a failure, no time limit)" {
    $action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Lobby
    if ($AtLogon) {
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
        $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    } else {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        # S4U: runs whether or not you are logged on, without storing your password
        $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited
    }
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Force `
        -Description "T5DR Online lobby server (lobby\deploy\windows\install-task.ps1). Data: $DataDir" | Out-Null
}

if ($OpenFirewall) {
    $udp2 = $Port + 1
    Step "Allow inbound TCP $Port and UDP $Port,$udp2 for $Python (private and domain networks)" {
        New-NetFirewallRule -DisplayName "$RulePrefix (TCP $Port)" -Direction Inbound -Action Allow `
            -Program $Python -Protocol TCP -LocalPort $Port -Profile Private,Domain | Out-Null
        New-NetFirewallRule -DisplayName "$RulePrefix (UDP $Port-$udp2)" -Direction Inbound -Action Allow `
            -Program $Python -Protocol UDP -LocalPort $Port,$udp2 -Profile Private,Domain | Out-Null
    }
} else {
    Write-Host "Firewall: unchanged (add -OpenFirewall, or allow Python when Windows asks)."
}

Step "Start it now" { Start-ScheduledTask -TaskName $TaskName }

Write-Host ""
Write-Host "Your router must forward TCP $Port and UDP $Port-$($Port + 1) to this PC (or use -MapPorts)."
Write-Host "The line to give your friends is written to $DataDir\host.json ('internet' / 'lan')."
Write-Host "Status: http://127.0.0.1:7780/status    Log: $DataDir\logs\t5lobby.log"
