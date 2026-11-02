# Windows only. Does the PATH that the Claude app starts with (user + machine PATH from the registry, NOT the PATH of the
# shell running this script) contain a folder with sh.exe? Prints one line: on-path | found:<folder> | git-missing
$dirs = @([Environment]::GetEnvironmentVariable('Path', 'User'), [Environment]::GetEnvironmentVariable('Path', 'Machine')) |
    ForEach-Object { $_ -split ';' } | Where-Object { $_ } |
    ForEach-Object { [Environment]::ExpandEnvironmentVariables($_).Trim('"') }
foreach ($d in $dirs) { if (Test-Path -LiteralPath (Join-Path $d 'sh.exe')) { 'on-path'; exit 0 } }
foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
    if (-not $root) { continue }
    $bin = Join-Path $root 'Git\bin'
    if (Test-Path -LiteralPath (Join-Path $bin 'sh.exe')) { "found:$bin"; exit 0 }
}
'git-missing'
