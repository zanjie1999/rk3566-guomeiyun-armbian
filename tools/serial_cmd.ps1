param(
    [Parameter(Mandatory = $true)][string]$Cmd,
    [int]$WaitMs = 2500,
    [string]$Port = "COM36",
    [int]$Baud = 1500000
)

$ErrorActionPreference = "Stop"

$sp = New-Object System.IO.Ports.SerialPort($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$sp.Handshake = [System.IO.Ports.Handshake]::None
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.ReadTimeout = 200
$sp.Encoding = [System.Text.Encoding]::ASCII

$sp.Open()
Start-Sleep -Milliseconds 150
$sp.DiscardInBuffer()

# eat any pending prompt / half-typed line
$sp.Write("`r")
Start-Sleep -Milliseconds 250
$null = $sp.ReadExisting()

$payload = $Cmd.Replace("`r`n", "`n").Replace("`n", "`r") + "`r"
$sp.Write($payload)

$acc = ""
$deadline = (Get-Date).AddMilliseconds($WaitMs)
while ((Get-Date) -lt $deadline) {
    $chunk = $sp.ReadExisting()
    if ($null -ne $chunk -and $chunk.Length -gt 0) { $acc = $acc + $chunk }
    Start-Sleep -Milliseconds 60
}

$sp.Close()
$sp.Dispose()

$out = $acc -replace "`e\[[0-9;?]*[a-zA-Z]", ""
$out.TrimEnd()
