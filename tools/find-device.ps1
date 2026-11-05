param(
    [string]$Subnet = "192.168.1",
    [string]$Want = "armbian",
    [string]$User = "root"
)

# 在局域网里找到目标设备：ping 扫全网段 -> 过滤 22 端口 -> SSH 读 hostname
$ErrorActionPreference = "SilentlyContinue"

$dir = "C:\Users\sparkle\.workbuddy\tmp"
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$ap = Join-Path $dir "askpass.cmd"
if (-not (Test-Path $ap)) { Set-Content -Path $ap -Value "@echo 1" -Encoding ascii }
$env:SSH_ASKPASS = $ap
$env:SSH_ASKPASS_REQUIRE = "force"
$env:DISPLAY = "localhost:0"

# 1. ping 扫描
$pings = 1..254 | ForEach-Object {
    $p = New-Object System.Net.NetworkInformation.Ping
    [pscustomobject]@{ IP = "$Subnet.$_"; Task = $p.SendPingAsync("$Subnet.$_", 500) }
}
[Threading.Tasks.Task]::WaitAll(($pings | ForEach-Object { $_.Task })) | Out-Null
$alive = @($pings | Where-Object { $_.Task.Result.Status -eq 'Success' } | ForEach-Object { $_.IP })
Write-Output ("alive: " + $alive.Count)

# 2. 过滤 22 端口
function Test-Port($ip, $port, $ms = 800) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $t = $c.BeginConnect($ip, $port, $null, $null)
        if ($t.AsyncWaitHandle.WaitOne($ms)) { $c.EndConnect($t); $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}
$ssh = @($alive | Where-Object { Test-Port $_ 22 })
Write-Output ("ssh open: " + ($ssh -join " "))

# 3. 认 hostname
foreach ($ip in $ssh) {
    $h = ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o LogLevel=ERROR `
             -o ConnectTimeout=6 -o PreferredAuthentications=password -o PubkeyAuthentication=no `
             "$User@$ip" "hostname" 2>$null
    if ($h -and ($h -join "") -match $Want) {
        Write-Output ("FOUND " + $ip)
        exit 0
    }
}
Write-Output "NOT FOUND"
exit 1
