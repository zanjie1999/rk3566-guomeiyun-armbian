param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Cmd,
    [string]$Dev = "192.168.1.210",
    [string]$User = "root",
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = "Continue"

$dir = "C:\Users\sparkle\.workbuddy\tmp"
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$ap = Join-Path $dir "askpass.cmd"
if (-not (Test-Path $ap)) { Set-Content -Path $ap -Value "@echo 1" -Encoding ascii }

$env:SSH_ASKPASS = $ap
$env:SSH_ASKPASS_REQUIRE = "force"
$env:DISPLAY = "localhost:0"

$out = ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL `
           -o PreferredAuthentications=password -o PubkeyAuthentication=no `
           -o ConnectTimeout=10 -o LogLevel=ERROR `
           "$User@$Dev" $Cmd 2>&1

$code = $LASTEXITCODE
$out | ForEach-Object { "$_" }
if ($code -ne 0) { "### EXIT=$code" }
