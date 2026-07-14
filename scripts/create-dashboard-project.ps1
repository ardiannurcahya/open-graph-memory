param(
    [string]$EnvFile = ".env",
    [string]$BaseUrl = "http://localhost:3000/api",
    [string]$ProjectName = "Dashboard Project",
    [string]$OutputFile = "project-connection.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$adminLine = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^ADMIN_API_KEY=' } | Select-Object -First 1
if (-not $adminLine) {
    throw "ADMIN_API_KEY not found in $EnvFile"
}

$adminKey = ($adminLine -replace '^ADMIN_API_KEY=', '').Trim().Trim('"').Trim("'")
if (-not $adminKey) {
    throw "ADMIN_API_KEY empty in $EnvFile"
}

$uri = "$($BaseUrl.TrimEnd('/'))/v1/projects"
$body = @{ name = $ProjectName } | ConvertTo-Json -Compress
$headers = @{ "X-API-Key" = $adminKey }

$data = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body
if (-not $data.id -or -not $data.api_key) {
    throw "Create project returned empty id/api_key"
}

$data | ConvertTo-Json -Compress | Set-Content -LiteralPath $OutputFile

"Project ID: $($data.id)"
"API Key: $($data.api_key)"
"Saved: $((Resolve-Path -LiteralPath $OutputFile).Path)"
