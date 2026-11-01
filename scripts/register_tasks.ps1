<#
.SYNOPSIS
  Registers (or removes) the four Windows Task Scheduler jobs that run Intraday Picks.

.DESCRIPTION
  Mon-Fri, IST (the machine clock must be set to India Standard Time):
    20:00  prep       evening watchlist for the next session
    09:10  morning    final picks after pre-open
    09:34  confirm    opening 15-minute candle check
    15:45  scorecard  outcomes
  Tasks wake the laptop, run as soon as possible if the time was missed, and never overlap.
  Run from an elevated PowerShell if registration is denied:  .\scripts\register_tasks.ps1
  Remove:  .\scripts\register_tasks.ps1 -Unregister
#>
param([switch]$Unregister)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root "scripts\run.cmd"
$taskPath = "\IntradayPicks\"
$jobs = @(
    @{ Name = "prep";      Time = "20:00" },
    @{ Name = "morning";   Time = "09:10" },
    @{ Name = "confirm";   Time = "09:34" },
    @{ Name = "scorecard"; Time = "15:45" }
)

foreach ($job in $jobs) {
    if ($Unregister) {
        Unregister-ScheduledTask -TaskName $job.Name -TaskPath $taskPath -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "removed $taskPath$($job.Name)"
        continue
    }
    $action = New-ScheduledTaskAction -Execute $runner -Argument $job.Name -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $job.Time
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
    Register-ScheduledTask -TaskName $job.Name -TaskPath $taskPath -Action $action -Trigger $trigger `
        -Settings $settings -Description "Intraday Picks: $($job.Name) run" -Force | Out-Null
    Write-Host "registered $taskPath$($job.Name) at $($job.Time) Mon-Fri"
}

if (-not $Unregister) {
    Write-Host ""
    Write-Host "Check with:  schtasks /query /tn ""IntradayPicks\prep"" /v /fo list"
    Write-Host "Run now:     schtasks /run /tn ""IntradayPicks\prep"""
    Write-Host "Log:         $env:LOCALAPPDATA\intraday-picks\logs\task.log"
}
