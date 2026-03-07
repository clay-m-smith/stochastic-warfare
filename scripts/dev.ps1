$api = Start-Process -NoNewWindow -PassThru -FilePath "uv" -ArgumentList "run", "uvicorn", "api.main:app", "--reload"
$frontend = Start-Process -NoNewWindow -PassThru -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory "frontend"

try {
    Wait-Process -Id $api.Id, $frontend.Id
} finally {
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue
}
