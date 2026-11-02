# Windows only. Appends one folder (the Git for Windows "bin" folder that holds sh.exe) to the USER PATH, once.
# Nothing else on PATH is changed. Run only after the user agreed. Usage: -Folder "C:\Program Files\Git\bin"
param([Parameter(Mandatory = $true)][string]$Folder)
if (-not (Test-Path -LiteralPath (Join-Path $Folder 'sh.exe'))) { Write-Output "error: no sh.exe in $Folder"; exit 1 }
$current = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @($current -split ';' | Where-Object { $_ })
if ($parts -contains $Folder) { Write-Output 'already-present'; exit 0 }
[Environment]::SetEnvironmentVariable('Path', (($parts + $Folder) -join ';'), 'User')
Write-Output "added:$Folder"
