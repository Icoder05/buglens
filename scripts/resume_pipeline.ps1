# Runs every remaining non-LLM step in order; safe to rerun (all steps are cached/resumable).
# Log: data/pipeline.log
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$log = "data/pipeline.log"

function Step($name, [string[]]$cmd) {
    "`n=== $(Get-Date -Format s) START $name ===" | Out-File $log -Append -Encoding utf8
    & uv run --no-sync buglens @cmd 2>&1 | Where-Object { $_ -notmatch "Batches|warn" } |
        Out-File $log -Append -Encoding utf8
    "=== $(Get-Date -Format s) END $name (exit $LASTEXITCODE) ===" | Out-File $log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { "PIPELINE FAILED at $name" | Out-File $log -Append; exit 1 }
}

Step "dense index test" @("index", "--split", "test", "--retriever", "dense")
foreach ($s in "dev", "test") {
    foreach ($sys in "S2", "S3") { Step "$sys $s" @("retrieve", "--system", $sys, "--split", $s) }
}
if (-not (Test-Path "data/models/coderankembed-ft/config.json")) { Step "finetune" @("finetune") }
foreach ($s in "dev", "test") {
    Step "ft index $s" @("index", "--split", $s, "--retriever", "dense", "--model", "data/models/coderankembed-ft")
    foreach ($sys in "S4", "S5", "A1") { Step "$sys $s" @("retrieve", "--system", $sys, "--split", $s) }
}
Step "S6 test" @("rerank", "--system", "S6", "--split", "test")
Step "S6 dev" @("rerank", "--system", "S6", "--split", "dev")
foreach ($sys in "S1", "S2", "S3", "S4", "S5", "S6", "A1") { Step "eval $sys" @("eval", "--system", $sys, "--split", "test") }
Step "errors" @("errors", "--system", "S6", "--n", "20")
Step "report" @("report")
foreach ($r in "pallets/flask", "psf/requests", "django/django") { Step "onboard $r" @("onboard", "--repo", $r) }
Step "onboard-eval" @("onboard-eval")
"PIPELINE DONE" | Out-File $log -Append -Encoding utf8
