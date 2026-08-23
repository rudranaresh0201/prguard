# Aftershock -- video demo script. Run this live on camera, one block at a time.
$base = "https://governance-agent.onrender.com/cross-repo"
$tmp = "$env:TEMP\aftershock-demo"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

Write-Host "`n=== 1. health check ===" -ForegroundColor Cyan
curl.exe -s "$base/health"
Write-Host ""

Write-Host "`n=== 2. repo-a announces a breaking change ===" -ForegroundColor Cyan
@{
  repo           = "testorg/repo-a"
  symbol         = "chargeDemo"
  old_signature  = "chargeDemo(amount)"
  new_signature  = "chargeDemo(amount,currency)"
  summary        = "video demo"
  severity       = "high"
  pr_url         = "https://github.com/testorg/repo-a/pull/1"
} | ConvertTo-Json | Set-Content -Encoding utf8 "$tmp\announce.json"
$resp = curl.exe -s -X POST "$base/announce" -H "Content-Type: application/json" -d "@$tmp\announce.json"
$resp
$json = $resp | ConvertFrom-Json
$sig = $json.sig
$at = $json.announced_at

Write-Host "`n=== 3. repo-b checks and gets flagged ===" -ForegroundColor Cyan
@{ repo = "testorg/repo-b"; symbols = @("chargeDemo") } | ConvertTo-Json | Set-Content -Encoding utf8 "$tmp\check-b.json"
curl.exe -s -X POST "$base/check" -H "Content-Type: application/json" -d "@$tmp\check-b.json"
Write-Host ""

Write-Host "`n=== 4. repo-a checks its own symbol -- excluded, not reflected back ===" -ForegroundColor Cyan
@{ repo = "testorg/repo-a"; symbols = @("chargeDemo") } | ConvertTo-Json | Set-Content -Encoding utf8 "$tmp\check-a.json"
curl.exe -s -X POST "$base/check" -H "Content-Type: application/json" -d "@$tmp\check-a.json"
Write-Host ""

Write-Host "`n=== 5. verify the genuine record -- valid: true ===" -ForegroundColor Cyan
@{
  repo = "testorg/repo-a"; symbol = "chargeDemo"
  old_signature = "chargeDemo(amount)"; new_signature = "chargeDemo(amount,currency)"
  summary = "video demo"; severity = "high"
  pr_url = "https://github.com/testorg/repo-a/pull/1"
  announced_at = $at; sig = $sig
} | ConvertTo-Json | Set-Content -Encoding utf8 "$tmp\verify-ok.json"
curl.exe -s -X POST "$base/verify" -H "Content-Type: application/json" -d "@$tmp\verify-ok.json"
Write-Host ""

Write-Host "`n=== 6. verify a TAMPERED copy -- valid: false ===" -ForegroundColor Cyan
@{
  repo = "testorg/repo-a"; symbol = "chargeDemo"
  old_signature = "chargeDemo(amount)"; new_signature = "chargeDemo(amount,currency,TAMPERED)"
  summary = "video demo"; severity = "high"
  pr_url = "https://github.com/testorg/repo-a/pull/1"
  announced_at = $at; sig = $sig
} | ConvertTo-Json | Set-Content -Encoding utf8 "$tmp\verify-bad.json"
curl.exe -s -X POST "$base/verify" -H "Content-Type: application/json" -d "@$tmp\verify-bad.json"
Write-Host ""
