param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$ServiceUrl = "http://127.0.0.1:8765",
    [string]$BatchId = "manual-ps-test",
    [string]$PhotoId = "manual-photo",
    [string]$Scene = "portrait",
    [string]$Aesthetic = "natural",
    [string]$UserSuggestion = "",
    [switch]$Run,
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"

$body = @{
    batch_id = $BatchId
    photo_id = $PhotoId
    input_path = $InputPath
    scene = $Scene
    aesthetic = $Aesthetic
    operations = @()
    user_suggestion = $UserSuggestion
    run = [bool]$Run
    wait_seconds = $WaitSeconds
} | ConvertTo-Json -Depth 8

$result = Invoke-RestMethod `
    -Method Post `
    -Uri "$ServiceUrl/v1/photos/photoshop-retouch" `
    -Body $body `
    -ContentType "application/json"

$result | ConvertTo-Json -Depth 12
