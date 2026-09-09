param([string]$Root = (Split-Path -Parent $PSScriptRoot), [ValidateSet('Interactive','Password')][string]$LogonType = 'Interactive', [System.Management.Automation.PSCredential]$Credential)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Project Python missing' }
$Git = (Get-Command git -ErrorAction Stop).Source
$HostConfig = @{git_executable=$Git; python_executable=$Python; repo_path=$Root}
$ConfigJson = $HostConfig | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $Root 'data\auction_host_config.json'), $ConfigJson, (New-Object System.Text.UTF8Encoding($false)))
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Scheduler requires Asia/Shanghai system time' }
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($LogonType -eq 'Password') {
    if (-not $Credential) { throw 'Password logon requires a Windows PSCredential supplied locally, never in source or command-line plaintext' }
    $User = $Credential.UserName
}
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType $LogonType -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)
foreach ($Slot in @(@('Live','09:12','live'),@('Watchdog','09:13','watchdog'),@('0935','09:35','post-open'),@('0945','09:45','post-open'),@('1000','10:00','post-open'),@('EOD','15:15','eod'))) {
    $Action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Root\tools\run_auction_task.ps1`" -Stage $($Slot[2])" -WorkingDirectory $Root
    $Clock = [datetime]::Today.Add([timespan]::ParseExact(($Slot[1] + ':00'), 'hh\:mm\:ss', $null))
    $Trigger = New-ScheduledTaskTrigger -Daily -At $Clock
    $Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal
    if ($LogonType -eq 'Password') {
        Register-ScheduledTask -TaskName "Ashare-Auction-$($Slot[0])" -InputObject $Task -User $User -Password $Credential.GetNetworkCredential().Password -Force | Select-Object TaskName,State
    } else {
        Register-ScheduledTask -TaskName "Ashare-Auction-$($Slot[0])" -InputObject $Task -Force | Select-Object TaskName,State
    }
}
