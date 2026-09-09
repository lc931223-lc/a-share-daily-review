param([string]$Root = (Split-Path -Parent $PSScriptRoot), [switch]$ProbeSource)
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path -LiteralPath $Root).Path
Set-Location -LiteralPath $Root
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Out = Join-Path $Root "data\auction_host_audit\$Stamp"
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$Tasks = @(Get-ScheduledTask -TaskName 'Ashare-Auction-*' | ForEach-Object {
    $t = $_; $i = Get-ScheduledTaskInfo -InputObject $t
    Export-ScheduledTask -TaskName $t.TaskName | Set-Content -LiteralPath (Join-Path $Out "$($t.TaskName).xml") -Encoding UTF8
    [ordered]@{TaskName=$t.TaskName; State=[string]$t.State; Enabled=$t.Settings.Enabled
        LastRunTime=$(if ($i.LastRunTime) {$i.LastRunTime.ToString('o')} else {$null}); LastTaskResult=$i.LastTaskResult; NextRunTime=$(if ($i.NextRunTime) {$i.NextRunTime.ToString('o')} else {$null})
        User=$t.Principal.UserId; LogonType=[string]$t.Principal.LogonType; WakeToRun=$t.Settings.WakeToRun
        StartWhenAvailable=$t.Settings.StartWhenAvailable; ExecutionTimeLimit=$t.Settings.ExecutionTimeLimit
        RestartCount=$t.Settings.RestartCount; RestartInterval=$t.Settings.RestartInterval
        DisallowStartIfOnBatteries=$t.Settings.DisallowStartIfOnBatteries; StopIfGoingOnBatteries=$t.Settings.StopIfGoingOnBatteries
        WorkingDirectory=$t.Actions.WorkingDirectory; Program=$t.Actions.Execute; Arguments=$t.Actions.Arguments
        ProgramExists=(Test-Path -LiteralPath $t.Actions.Execute)}
})
$Events = @(Get-WinEvent -FilterHashtable @{LogName='System'; Id=12,13,42,1074,6006,6008; StartTime=[datetime]::Today} -ErrorAction SilentlyContinue | Select-Object TimeCreated,Id,ProviderName,Message)
$Copies = @(Get-ChildItem -LiteralPath (Split-Path -Parent (Split-Path -Parent $Root)),"$env:USERPROFILE\Documents",'D:\CodexData' -Directory -Recurse -Depth 4 -ErrorAction SilentlyContinue | Where-Object Name -Match '^a[-_]share[-_]daily[-_]review')
$Files = @($Copies | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Filter '*2026-09-09*' -ErrorAction SilentlyContinue } | Where-Object FullName -Match 'auction' | Select-Object FullName,Length,CreationTime,LastWriteTime)
$Proxy = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$Result = [ordered]@{observed_at=(Get-Date -Format o); hostname=$env:COMPUTERNAME; username=$env:USERNAME
    current_power_state='AWAKE_AT_PROBE_TIME'; last_boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
    wake_timer_policy=@(powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE); wake_timers=@(powercfg /waketimers 2>&1 | Out-String)
    power_capabilities=@(powercfg /a); network=@(Get-NetConnectionProfile | Select-Object Name,IPv4Connectivity)
    internet_connectivity=@(& "$Root\.venv\Scripts\python.exe" -c "from pathlib import Path; from src.auction.git_sync import git; print(git(Path.cwd(), 'ls-remote', 'origin', 'refs/heads/main'))" 2>&1 | Out-String)
    proxy_enabled=$Proxy.ProxyEnable; proxy_server=$Proxy.ProxyServer
    repo_path=$Root; repo_status=@(& git -C $Root status --short --branch); git_head=@(& git -C $Root rev-parse HEAD)
    python_exists=(Test-Path -LiteralPath (Join-Path $Root '.venv\Scripts\python.exe'))
    script_exists=(Test-Path -LiteralPath (Join-Path $Root 'tools\run_auction_scheduled.py'))
    tasks=$Tasks; events=$Events; repository_copies=@($Copies.FullName); local_files=$Files
    source_connection='NOT_PROBED'}
if ($ProbeSource) { $Result.source_connection = @(& "$Root\.venv\Scripts\python.exe" "$Root\tools\probe_auction_host_source.py" 2>&1 | Out-String) }
$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Out 'audit.json') -Encoding UTF8
Write-Output $Out
