# Windows only. Can the Claude app find `sh` to start the video2aeo helper? The app starts with the PATH from the
# registry (user + machine), NOT the PATH of the shell running this script.
#   path-check.ps1 [-ShFolder <dir>]    prints one line: on-path | found:<Git bin folder> | git-missing
#                                       (-ShFolder: the folder of the `sh` running the caller, tried first – Scoop, portable Git)
#   path-check.ps1 -Fix -Folder <dir>   appends that Git bin folder to the USER PATH once – only after the user agreed –
#                                       and prints added:<folder> | already-present | error: <reason>
# The fix keeps the raw registry value, so %VAR% entries stay unexpanded and the value stays REG_EXPAND_SZ.
param([string]$ShFolder = '', [switch]$Fix, [string]$Folder = '')
$ErrorActionPreference = 'Stop'

# Git's bin folder for a folder holding sh.exe, or $null. Git\usr\bin maps to Git\bin: usr\bin would put Git's Unix
# tools (find, sort, …) in front of the Windows ones. The folder must belong to a Git install and not be a network path.
function Get-GitBin([string]$dir) {
    $d = ([string]$dir).Trim().Trim('"').Replace('/', '\')
    if ($d -notmatch '^[A-Za-z]:\\') { return $null }   # a local drive path only: no UNC, no relative path
    $d = [IO.Path]::GetFullPath($d).TrimEnd('\')
    if ((Split-Path $d -Leaf) -eq 'bin' -and (Split-Path (Split-Path $d -Parent) -Leaf) -eq 'usr') {
        $d = Join-Path (Split-Path (Split-Path $d -Parent) -Parent) 'bin'
    }
    $root = Split-Path $d -Parent
    if ((Test-Path -LiteralPath (Join-Path $d 'sh.exe')) -and
        ((Test-Path -LiteralPath (Join-Path $d 'git.exe')) -or (Test-Path -LiteralPath (Join-Path $root 'cmd\git.exe')))) {
        return $d
    }
    return $null
}

try {
    if ($Fix) {
        $bin = Get-GitBin $Folder
        if (-not $bin) { Write-Output "error: not a Git for Windows bin folder: $Folder"; exit 1 }
        $key = Get-Item -LiteralPath 'HKCU:\Environment'
        $current = [string]$key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        $parts = @($current -split ';' | Where-Object { $_ })
        foreach ($p in $parts) {
            if ([Environment]::ExpandEnvironmentVariables($p).Trim('"').TrimEnd('\') -ieq $bin) { Write-Output 'already-present'; exit 0 }
        }
        Set-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'Path' -Type ExpandString -Value (($parts + $bin) -join ';')
        # Tell running programs the environment changed (the Claude app still needs a restart to pick it up).
        try { [Environment]::SetEnvironmentVariable('VIDEO2AEO_PATH_FIX', $null, 'User') } catch { }
        Write-Output "added:$bin"
        exit 0
    }
    $dirs = @([Environment]::GetEnvironmentVariable('Path', 'User'), [Environment]::GetEnvironmentVariable('Path', 'Machine')) |
        ForEach-Object { $_ -split ';' } | Where-Object { $_ } |
        ForEach-Object { [Environment]::ExpandEnvironmentVariables($_).Trim('"') }
    foreach ($d in $dirs) { if (Test-Path -LiteralPath (Join-Path $d 'sh.exe')) { 'on-path'; exit 0 } }
    $cands = @($ShFolder)
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
        if ($root) { $cands += (Join-Path $root 'Git\bin') }
    }
    foreach ($c in $cands) { $bin = Get-GitBin $c; if ($bin) { "found:$bin"; exit 0 } }
    'git-missing'
} catch {
    Write-Output "error: $($_.Exception.Message)"
    exit 1
}
