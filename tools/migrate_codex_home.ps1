[CmdletBinding()]
param(
    [string]$Source = (Join-Path $env:USERPROFILE '.codex'),
    [string]$Target = 'D:\CodexData\codex-home',
    [string]$AllowedTargetRoot = 'D:\CodexData',
    [string]$LogPath = 'D:\CodexData\codex-home-migration.log',
    [string]$AppExecutable = 'C:\Program Files\WindowsApps\OpenAI.Codex_26.825.6671.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe',
    [int]$ExitWaitTimeoutSeconds = 600,
    [switch]$Preflight,
    [switch]$Rollback
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-MigrationLog {
    param([string]$Message)

    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
}

function Get-NormalizedPath {
    param([string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Assert-MigrationPaths {
    $sourcePath = Get-NormalizedPath $Source
    $targetPath = Get-NormalizedPath $Target
    $allowedRoot = (Get-NormalizedPath $AllowedTargetRoot) + '\'

    if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
        throw "Codex source directory does not exist: $sourcePath"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $sourcePath 'config.toml') -PathType Leaf)) {
        throw "Codex source config is missing: $sourcePath\config.toml"
    }
    if (-not ($targetPath + '\').StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Target must stay under $AllowedTargetRoot"
    }
    if ($sourcePath -eq $targetPath) {
        throw 'Source and target directories must differ.'
    }
}

function Wait-ForCodexExit {
    $deadline = (Get-Date).AddSeconds($ExitWaitTimeoutSeconds)
    do {
        $running = @(Get-Process -Name 'ChatGPT', 'codex' -ErrorAction SilentlyContinue)
        if ($running.Count -eq 0) {
            return
        }
        if ((Get-Date) -ge $deadline) {
            throw "Timed out waiting for Codex to exit after $ExitWaitTimeoutSeconds seconds."
        }
        Start-Sleep -Seconds 2
    } while ($true)
}

function Copy-CodexState {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null

    $arguments = @(
        $Source,
        $Target,
        '/E',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/SL',
        '/SJ',
        '/R:3',
        '/W:2',
        '/NP',
        '/NFL',
        '/NDL'
    )
    & robocopy.exe @arguments | Out-Null
    $robocopyExitCode = $LASTEXITCODE
    if ($robocopyExitCode -gt 7) {
        throw "Robocopy failed with exit code $robocopyExitCode."
    }

    $sourceFiles = @(Get-ChildItem -LiteralPath $Source -File -Recurse -Force)
    $targetFiles = @(Get-ChildItem -LiteralPath $Target -File -Recurse -Force)
    if ($targetFiles.Count -lt $sourceFiles.Count) {
        throw "File-count validation failed: source=$($sourceFiles.Count), target=$($targetFiles.Count)."
    }

    foreach ($relativePath in @('config.toml', 'sessions', 'skills', 'plugins')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Target $relativePath))) {
            throw "Migration validation failed; missing target item: $relativePath"
        }
    }

    return [pscustomobject]@{
        RobocopyExitCode = $robocopyExitCode
        SourceFileCount = $sourceFiles.Count
        TargetFileCount = $targetFiles.Count
    }
}

function Add-JunctionTargetsToTrustedCodePaths {
    $configPath = Join-Path $Target 'config.toml'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        return
    }

    $junctionTargets = @(
        Get-ChildItem -LiteralPath $Target -Force |
            Where-Object { $_.LinkType -eq 'Junction' } |
            ForEach-Object { $_.Target } |
            Where-Object { $_ } |
            ForEach-Object { Get-NormalizedPath $_ } |
            Sort-Object -Unique
    )
    if ($junctionTargets.Count -eq 0) {
        return
    }

    $lines = @(Get-Content -LiteralPath $configPath)
    $key = 'NODE_REPL_TRUSTED_CODE_PATHS'
    $lineIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^$key\s*=\s*'([^']*)'\s*$") {
            $lineIndex = $index
            $existingPaths = @($Matches[1] -split ';' | Where-Object { $_ })
            break
        }
    }
    if ($lineIndex -lt 0) {
        return
    }

    $trustedPaths = @($existingPaths + $junctionTargets | Sort-Object -Unique)
    $lines[$lineIndex] = "$key = '$($trustedPaths -join ';')'"
    Set-Content -LiteralPath $configPath -Value $lines -Encoding utf8
}

if ($Rollback) {
    [Environment]::SetEnvironmentVariable('CODEX_HOME', $null, 'User')
    Write-MigrationLog 'Rollback completed: user CODEX_HOME was cleared. Source data was not changed.'
    Write-Output 'Rollback completed. Fully restart Codex to use the original home directory.'
    exit 0
}

Assert-MigrationPaths

if ($Preflight) {
    $sourceFiles = @(Get-ChildItem -LiteralPath $Source -File -Recurse -Force)
    $sourceBytes = ($sourceFiles | Measure-Object -Property Length -Sum).Sum
    [pscustomobject]@{
        Status = 'ready'
        Source = Get-NormalizedPath $Source
        Target = Get-NormalizedPath $Target
        SourceFileCount = $sourceFiles.Count
        SourceSizeMB = [math]::Round($sourceBytes / 1MB, 2)
        AppExecutableExists = Test-Path -LiteralPath $AppExecutable -PathType Leaf
        ExistingUserCodexHome = [Environment]::GetEnvironmentVariable('CODEX_HOME', 'User')
    }
    exit 0
}

try {
    Write-MigrationLog 'Migration helper started; waiting for Codex processes to exit.'
    Wait-ForCodexExit
    Write-MigrationLog 'Codex processes exited; copying state.'

    $result = Copy-CodexState
    Write-MigrationLog "Copy validated: source files=$($result.SourceFileCount), target files=$($result.TargetFileCount), robocopy=$($result.RobocopyExitCode)."

    Add-JunctionTargetsToTrustedCodePaths
    Write-MigrationLog 'Junction targets added to Node REPL trusted code paths.'

    [Environment]::SetEnvironmentVariable('CODEX_HOME', (Get-NormalizedPath $Target), 'User')
    $env:CODEX_HOME = Get-NormalizedPath $Target
    Write-MigrationLog "User CODEX_HOME set to $env:CODEX_HOME."

    $markerPath = Join-Path $Target 'CODEX_HOME_MIGRATION_COMPLETE.txt'
    Set-Content -LiteralPath $markerPath -Value "Completed $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding ascii

    if (Test-Path -LiteralPath $AppExecutable -PathType Leaf) {
        Write-MigrationLog 'Restarting Codex with the new CODEX_HOME.'
        Start-Process -FilePath $AppExecutable
    } else {
        Write-MigrationLog 'Migration succeeded, but the saved Codex executable path no longer exists.'
    }
} catch {
    Write-MigrationLog "Migration failed: $($_.Exception.Message)"
    throw
}
