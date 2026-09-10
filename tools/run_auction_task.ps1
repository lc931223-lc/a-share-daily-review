param([ValidateSet('live','post-open','eod','watchdog','retry')][string]$Stage = 'live', [switch]$DryRun, [string]$SyncDate, [string]$DryRunDate)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Day = Get-Date -Format 'yyyy-MM-dd'
$Folder = if ($DryRun) { Join-Path $Root "data\auction_dry_runs\bootstrap-$Day" } else { Join-Path $Root "data\auction_logs\$Day" }
New-Item -ItemType Directory -Path $Folder -Force | Out-Null
$Log = Join-Path $Folder 'live.log'
$env:AUCTION_SCHEDULER_TRIGGERED_AT = Get-Date -Format o
$env:PYTHONUTF8 = '1'
@{event='scheduler_triggered_at'; timestamp=$env:AUCTION_SCHEDULER_TRIGGERED_AT; stage=$Stage; repo_path=$Root; username=$env:USERNAME; hostname=$env:COMPUTERNAME} | ConvertTo-Json -Compress | Add-Content -LiteralPath $Log -Encoding UTF8
try {
    if ($DryRunDate -and (-not $DryRun -or $Stage -eq 'retry')) { throw 'DryRunDate requires a non-retry DryRun' }
    Set-Location -LiteralPath $Root
    $Python = Join-Path $Root '.venv\Scripts\python.exe'
    $Script = Join-Path $Root 'tools\run_auction_scheduled.py'
    if (-not (Test-Path -LiteralPath $Python)) { throw "Python missing: $Python" }
    if (-not (Test-Path -LiteralPath $Script)) { throw "Script missing: $Script" }
    $ArgsList = @($Script, '--stage', $Stage, '--sync')
    if ($Stage -eq 'retry') {
        if ($SyncDate -notmatch '^\d{4}-\d{2}-\d{2}$') { throw 'Retry requires -SyncDate YYYY-MM-DD' }
        $ArgsList = @((Join-Path $Root 'tools\retry_auction_sync.py'), '--date', $SyncDate)
    }
    if ($DryRun) { $ArgsList += '--dry-run' }
    if ($DryRunDate) { $ArgsList += @('--dry-run-date', $DryRunDate) }
    & $Python @ArgsList >> (Join-Path $Folder 'process.log') 2>&1
    $Code = $LASTEXITCODE
    @{event='python_exit'; timestamp=(Get-Date -Format o); exit_code=$Code} | ConvertTo-Json -Compress | Add-Content -LiteralPath $Log -Encoding UTF8
    exit $Code
} catch {
    @{event='BOOTSTRAP_FAILED'; timestamp=(Get-Date -Format o); exception=$_.Exception.ToString(); traceback=$_.ScriptStackTrace} | ConvertTo-Json -Compress | Add-Content -LiteralPath $Log -Encoding UTF8
    exit 1
}
