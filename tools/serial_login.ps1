param(
    [string]$Port = "COM36",
    [int]$Baud = 1500000,
    [string]$User = "root",
    [string]$Pass = "1",
    [string]$Shell = "bash",
    [int]$GapMs = 12000
)

$ErrorActionPreference = "Stop"

$sp = New-Object System.IO.Ports.SerialPort($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$sp.Handshake = [System.IO.Ports.Handshake]::None
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.ReadTimeout = 300
$sp.Encoding = [System.Text.Encoding]::ASCII

$sp.Open()
Start-Sleep -Milliseconds 200

function Drain([int]$ms) {
    $acc = ""
    $deadline = (Get-Date).AddMilliseconds($ms)
    while ((Get-Date) -lt $deadline) {
        $c = $sp.ReadExisting()
        if ($c) { $acc += $c }
        Start-Sleep -Milliseconds 80
    }
    return $acc
}

$log = ""

# press enter once to get a fresh prompt (safe at login: prompt, NOT at password prompt
# only if we are at "login:" -- caller should ensure that)
$sp.Write("`r")
$log += Drain(2500)

foreach ($step in @($User, $Pass, $Shell)) {
    $sp.Write($step + "`r")
    $log += Drain($GapMs)
}

$sp.Close()
$sp.Dispose()

$out = $log -replace "`e\[[0-9;?]*[a-zA-Z]", ""
$out.TrimEnd()
