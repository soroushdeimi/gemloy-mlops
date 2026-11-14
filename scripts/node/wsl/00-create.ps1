# Operator-run Windows PowerShell; creates only the separate test distribution.
$ErrorActionPreference = 'Stop'
$Distro = 'k8s-test'
$Installed = @(wsl.exe --list --quiet) | ForEach-Object { ($_ -replace "`0", '').Trim() }
if ($Installed -notcontains $Distro) {
    if ((wsl.exe --help | Out-String) -notmatch '--name') {
        throw 'This WSL version lacks named installation. Update WSL after the snapshot and retry.'
    }
    wsl.exe --install --distribution Ubuntu-24.04 --name $Distro --no-launch
    if ($LASTEXITCODE -ne 0) { throw 'Distribution installation did not finish; review WSL output.' }
}
wsl.exe --set-version $Distro 2
if ($LASTEXITCODE -ne 0) { throw 'The test distribution could not be set to WSL2.' }
Write-Output 'Open k8s-test, finish its first-user setup, then run 01-prepare.sh there.'
