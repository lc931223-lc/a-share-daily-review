param([string]$Root = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Python = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Project Python missing' }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Scheduler requires Asia/Shanghai system time' }
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)
foreach ($Slot in @(@('Live','09:12','live'),@('0935','09:35','post-open'),@('0945','09:45','post-open'),@('1000','10:00','post-open'),@('EOD','15:15','eod'))) {
    $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Root\tools\run_auction_scheduled.py`" --stage $($Slot[2]) --sync" -WorkingDirectory $Root
    $Clock = [datetime]::Today.Add([timespan]::ParseExact(($Slot[1] + ':00'), 'hh\:mm\:ss', $null))
    $Trigger = New-ScheduledTaskTrigger -Daily -At $Clock
    Register-ScheduledTask -TaskName "Ashare-Auction-$($Slot[0])" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Select-Object TaskName,State
}
