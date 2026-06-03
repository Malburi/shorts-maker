# Shorts Maker — 백엔드 + 프론트엔드 동시 실행
$root = $PSScriptRoot

# Check OPENAI_API_KEY
if (-not $env:OPENAI_API_KEY) {
    Write-Host "⚠  OPENAI_API_KEY 환경변수가 없습니다." -ForegroundColor Yellow
    $env:OPENAI_API_KEY = Read-Host "OpenAI API Key를 입력하세요"
}

# Backend
Write-Host "`n▶ 백엔드 시작 (http://localhost:8000)..." -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    Set-Location "$using:root\backend"
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
}

Start-Sleep -Seconds 2

# Frontend
Write-Host "▶ 프론트엔드 시작 (http://localhost:5173)..." -ForegroundColor Cyan
$frontendJob = Start-Job -ScriptBlock {
    Set-Location "$using:root\frontend"
    npm run dev
}

Write-Host "`n✅ 실행 중! 브라우저에서 http://localhost:5173 을 열어주세요" -ForegroundColor Green
Write-Host "   Ctrl+C 로 종료`n" -ForegroundColor Gray

try {
    while ($true) {
        Receive-Job $backendJob, $frontendJob
        Start-Sleep -Seconds 2
    }
} finally {
    Stop-Job $backendJob, $frontendJob
    Remove-Job $backendJob, $frontendJob
}
