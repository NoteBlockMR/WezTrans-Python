param([string]$Destination = (Join-Path $PSScriptRoot 'python32'))
$ErrorActionPreference = 'Stop'
$version = '3.12.10'
$expectedHash = '084B9EB24CB848605C895D05B738FBC2572EFC8B4C18C415A824065864A2B853'
$python = Join-Path $Destination 'python.exe'
if (Test-Path -LiteralPath $python -PathType Leaf) {
    & $python -c "import struct, sys; sys.exit(0 if struct.calcsize('P') == 4 else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'The existing interpreter is not 32-bit Python.' }
    Write-Host "32-bit Python is already installed at $Destination"
    exit 0
}
if (Test-Path -LiteralPath $Destination) {
    throw "The destination already exists but has no python.exe: $Destination"
}
$archive = Join-Path ([IO.Path]::GetTempPath()) ("weztrans-python32-" + [Guid]::NewGuid().ToString('N') + '.zip')
try {
    Write-Host "Downloading official Python $version 32-bit embedded distribution..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$version/python-$version-embed-win32.zip" -OutFile $archive -UseBasicParsing
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Downloaded Python archive failed the SHA-256 integrity check.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination
    & $python -c "import struct, sys; sys.exit(0 if struct.calcsize('P') == 4 else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'The installed interpreter did not pass validation.' }
} finally {
    if (Test-Path -LiteralPath $archive -PathType Leaf) { Remove-Item -LiteralPath $archive -Force }
}
