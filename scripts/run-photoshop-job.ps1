param(
    [string]$ServiceUrl = "http://127.0.0.1:8765",
    [string]$BatchId = "",
    [string]$JobId = "",
    [int]$WaitSeconds = 30,
    [string]$PhotoshopExe = ""
)

$ErrorActionPreference = "Stop"

if ($BatchId -eq "" -or $JobId -eq "") {
    $nextUrl = "$ServiceUrl/v1/photoshop/jobs/next"
    if ($BatchId -ne "") {
        $nextUrl = "$nextUrl?batch_id=$([uri]::EscapeDataString($BatchId))"
    }
    $next = Invoke-RestMethod -Method Get -Uri $nextUrl
    if ($next.status -eq "empty") {
        Write-Host "No queued Photoshop jobs."
        exit 0
    }
    $BatchId = $next.batch_id
    $JobId = $next.job_id
}

$body = @{
    wait_seconds = $WaitSeconds
    photoshop_exe = $PhotoshopExe
} | ConvertTo-Json

$runUrl = "$ServiceUrl/v1/photoshop/jobs/$([uri]::EscapeDataString($BatchId))/$([uri]::EscapeDataString($JobId))/run"
$result = Invoke-RestMethod -Method Post -Uri $runUrl -Body $body -ContentType "application/json"
$result | ConvertTo-Json -Depth 8
