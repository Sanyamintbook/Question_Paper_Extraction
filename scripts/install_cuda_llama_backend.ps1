# Installs the official CUDA 12.4 llama.cpp build beside the existing CPU build.
# It does not delete or overwrite H:\Documents\Surya OCR\tools\llama.cpp.

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $scriptRoot 'tools\llama.cpp-cuda'
$release = 'b10516'
$buildNumber = '10516'
$stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$binaryZip = Join-Path $destination 'llama-bin-cuda.zip'
$runtimeZip = Join-Path $destination 'llama-cudart.zip'

New-Item -ItemType Directory -Force -Path $destination | Out-Null

$binaryUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$release/llama-b$buildNumber-bin-win-cuda-12.4-x64.zip?cachebust=$stamp"
$runtimeUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$release/cudart-llama-bin-win-cuda-12.4-x64.zip?cachebust=$stamp"

Invoke-WebRequest -Uri $binaryUrl -OutFile $binaryZip
Invoke-WebRequest -Uri $runtimeUrl -OutFile $runtimeZip

Expand-Archive -LiteralPath $binaryZip -DestinationPath $destination -Force
Expand-Archive -LiteralPath $runtimeZip -DestinationPath $destination -Force

$server = Get-ChildItem -LiteralPath $destination -Recurse -Filter 'llama-server.exe' |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $server) {
    throw 'CUDA llama-server.exe was not found after extraction.'
}

& $server --list-devices

Write-Host "CUDA backend installed: $server"
Write-Host 'Restart the Surya OCR UI. The runner will automatically enable partial GPU offload.'
