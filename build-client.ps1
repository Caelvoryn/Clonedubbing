$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force dist | Out-Null
    & $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll '/out:dist\Clonedubbing.exe' Client.cs
    if ($LASTEXITCODE) { throw 'Client build failed' }
    & $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll '/resource:dist\Clonedubbing.exe,client.exe' '/out:dist\ClonedubbingSetup.exe' Installer.cs
    if ($LASTEXITCODE) { throw 'Installer build failed' }
} finally { Pop-Location }
