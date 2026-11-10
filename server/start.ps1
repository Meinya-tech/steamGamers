Set-Location -LiteralPath $PSScriptRoot
$env:SG_RUN_BOT = '1'
python app.py
