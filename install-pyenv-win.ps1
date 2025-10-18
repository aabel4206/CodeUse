<#
    .SYNOPSIS
    Installs pyenv-win

    .DESCRIPTION
    Installs pyenv-win to $HOME\.pyenv
    If pyenv-win is already installed, try to update to the latest version.

    .PARAMETER Uninstall
    Uninstall pyenv-win. Note that this uninstalls any Python versions that were installed with pyenv-win.

    .INPUTS
    None.

    .OUTPUTS
    None.

    .EXAMPLE
    PS> install-pyenv-win.ps1

    .LINK
    Online version: https://pyenv-win.github.io/pyenv-win/
#>
    
param (
    [Switch] $Uninstall = $False
)
    
$PyEnvDir = "${env:USERPROFILE}\.pyenv"
$PyEnvWinDir = "${PyEnvDir}\pyenv-win"
$BinPath = "${PyEnvWinDir}\bin"
$ShimsPath = "${PyEnvWinDir}\shims"
    
Function Remove-PyEnvVars() {
    $PathParts = [System.Environment]::GetEnvironmentVariable('PATH', "User") -Split ";"
    $NewPathParts = $PathParts.Where{ $_ -ne $BinPath }.Where{ $_ -ne $ShimsPath }
    $NewPath = $NewPathParts -Join ";"
    [System.Environment]::SetEnvironmentVariable('PATH', $NewPath, "User")

    [System.Environment]::SetEnvironmentVariable('PYENV', $null, "User")
    [System.Environment]::SetEnvironmentVariable('PYENV_ROOT', $null, "User")
    [System.Environment]::SetEnvironmentVariable('PYENV_HOME', $null, "User")
}

Function Remove-PyEnv() {
    Write-Host "Removing $PyEnvDir..."
    If (Test-Path $PyEnvDir) {
        Remove-Item -Path $PyEnvDir -Recurse
    }
    Write-Host "Removing environment variables..."
    Remove-PyEnvVars
}

Function Get-CurrentVersion() {
    $VersionFilePath = "$PyEnvDir\.version"
    If (Test-Path $VersionFilePath) {
        $CurrentVersion = Get-Content $VersionFilePath
    }
    Else {
        $CurrentVersion = ""
    }

    Return $CurrentVersion
}

Function Get-LatestVersion() {
    $LatestVersionFilePath = "$PyEnvDir\latest.version"
    (New-Object System.Net.WebClient).DownloadFile("https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/.version", $LatestVersionFilePath)
    $LatestVersion = Get-Content $LatestVersionFilePath

    Remove-Item -Path $LatestVersionFilePath

    Return $LatestVersion
}

Function Ensure-PyenvAvailableInSession() {
    # Ensure pyenv is available for the current PowerShell session
    $global:PyEnvDir = "${env:USERPROFILE}\.pyenv"
    $global:PyEnvWinDir = "${PyEnvDir}\pyenv-win"
    $global:BinPath = "${PyEnvWinDir}\bin"
    $global:ShimsPath = "${PyEnvWinDir}\shims"

    $env:PYENV = "${PyEnvWinDir}\"
    $env:PYENV_ROOT = "${PyEnvWinDir}\"
    $env:PYENV_HOME = "${PyEnvWinDir}\"

    if (-not ($env:Path -split ';' | Where-Object { $_ -eq $BinPath })) {
        $env:Path = "$BinPath;" + $env:Path
    }
    if (-not ($env:Path -split ';' | Where-Object { $_ -eq $ShimsPath })) {
        $env:Path = "$ShimsPath;" + $env:Path
    }
}

Function Install-PythonVersionFromFile() {
    try {
        $versionFile = Join-Path (Get-Location) ".python-version"
        if (-not (Test-Path $versionFile)) {
            Write-Host "No .python-version found in $(Get-Location). Skipping Python install."
            return
        }

        $requestedVersion = (Get-Content -Raw $versionFile).Trim()
        if (-not $requestedVersion) {
            Write-Host ".python-version is empty. Skipping Python install."
            return
        }
        if ($requestedVersion -eq 'system') {
            Write-Host ".python-version specifies 'system'. Skipping Python install."
            return
        }

        Ensure-PyenvAvailableInSession

        $pyenvBat = Join-Path $BinPath 'pyenv.bat'
        $pyenvPs1 = Join-Path $BinPath 'pyenv.ps1'
        if (-not (Test-Path $pyenvBat) -and -not (Test-Path $pyenvPs1)) {
            Write-Host "pyenv executable not found in $BinPath. Ensure install completed successfully."
            return
        }

        # Helper to invoke pyenv regardless of .bat or .ps1
        $pyenvCmd = if (Test-Path $pyenvBat) { $pyenvBat } else { $pyenvPs1 }

        Write-Host "Checking existing pyenv Python installations..."
        $installedList = & $pyenvCmd versions 2>$null
        $alreadyInstalled = $false
        if ($installedList) {
            # versions output may include markers like '* ' or '  '
            foreach ($line in ($installedList -split "`n")) {
                $clean = ($line -replace '^[\* ]+','').Trim()
                if ($clean -eq $requestedVersion) { $alreadyInstalled = $true; break }
            }
        }

        if ($alreadyInstalled) {
            Write-Host "Python $requestedVersion already installed via pyenv."
        }
        else {
            Write-Host "Installing Python $requestedVersion via pyenv-win..."
            & $pyenvCmd install $requestedVersion
            if ($LASTEXITCODE -ne 0) {
                throw "pyenv install $requestedVersion failed with exit code $LASTEXITCODE"
            }
        }

        # Set local version to match the file (keeps behavior explicit)
        Write-Host "Setting local pyenv version to $requestedVersion..."
        & $pyenvCmd local $requestedVersion
        if ($LASTEXITCODE -ne 0) {
            throw "pyenv local $requestedVersion failed with exit code $LASTEXITCODE"
        }

        # Show resulting python version for confirmation
        Write-Host "Verifying Python version..."
        & (Join-Path $ShimsPath 'python.exe') --version
    }
    catch {
        Write-Host "Failed to install/set Python from .python-version:`n$($_.Exception.Message)"
    }
}

Function Main() {
    If ($Uninstall) {
        Remove-PyEnv
        If ($? -eq $True) {
            Write-Host "pyenv-win successfully uninstalled."
        }
        Else {
            Write-Host "Uninstallation failed."
        }
        exit
    }

    $BackupDir = "${env:Temp}/pyenv-win-backup"
    
    $CurrentVersion = Get-CurrentVersion
    If ($CurrentVersion) {
        Write-Host "pyenv-win $CurrentVersion installed."
        $LatestVersion = Get-LatestVersion
        If ($CurrentVersion -eq $LatestVersion) {
            Write-Host "No updates available."
        }
        Else {
            Write-Host "New version available: $LatestVersion. Updating..."
            
            Write-Host "Backing up existing Python installations..."
            $FoldersToBackup = "install_cache", "versions", "shims"
            ForEach ($Dir in $FoldersToBackup) {
                If (-not (Test-Path $BackupDir)) {
                    New-Item -ItemType Directory -Path $BackupDir
                }
                Move-Item -Path "${PyEnvWinDir}/${Dir}" -Destination $BackupDir
            }
            
            Write-Host "Removing $PyEnvDir..."
            Remove-Item -Path $PyEnvDir -Recurse
        }   
    }

    New-Item -Path $PyEnvDir -ItemType Directory

    $DownloadPath = "$PyEnvDir\pyenv-win.zip"

    (New-Object System.Net.WebClient).DownloadFile("https://github.com/pyenv-win/pyenv-win/archive/master.zip", $DownloadPath)

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile",
        "-Command `"Microsoft.PowerShell.Archive\Expand-Archive -Path \`"$DownloadPath\`" -DestinationPath \`"$PyEnvDir\`"`""
    ) -NoNewWindow -Wait

    Move-Item -Path "$PyEnvDir\pyenv-win-master\*" -Destination "$PyEnvDir"
    Remove-Item -Path "$PyEnvDir\pyenv-win-master" -Recurse
    Remove-Item -Path $DownloadPath

    # Update env vars
    [System.Environment]::SetEnvironmentVariable('PYENV', "${PyEnvWinDir}\", "User")
    [System.Environment]::SetEnvironmentVariable('PYENV_ROOT', "${PyEnvWinDir}\", "User")
    [System.Environment]::SetEnvironmentVariable('PYENV_HOME', "${PyEnvWinDir}\", "User")

    $PathParts = [System.Environment]::GetEnvironmentVariable('PATH', "User") -Split ";"

    # Remove existing paths, so we don't add duplicates
    $NewPathParts = $PathParts.Where{ $_ -ne $BinPath }.Where{ $_ -ne $ShimsPath }
    $NewPathParts = ($BinPath, $ShimsPath) + $NewPathParts
    $NewPath = $NewPathParts -Join ";"
    [System.Environment]::SetEnvironmentVariable('PATH', $NewPath, "User")

    If (Test-Path $BackupDir) {
        Write-Host "Restoring Python installations..."
        Move-Item -Path "$BackupDir/*" -Destination $PyEnvWinDir
    }
    
    If ($? -eq $True) {
        Write-Host "pyenv-win is successfully installed. You may need to close and reopen your terminal before using it."
    }
    Else {
        Write-Host "pyenv-win was not installed successfully. If this issue persists, please open a ticket: https://github.com/pyenv-win/pyenv-win/issues."
    }

    # Ensure we can call pyenv in this session, then install the requested Python version if .python-version exists
    Ensure-PyenvAvailableInSession
    Install-PythonVersionFromFile
}

Main
