# Runs every Gemini-dependent step in order; resumable (LLM answers are cached on disk).
# If the free daily quota runs out, steps stop early and save partial results: rerun tomorrow.
# Log: data/llm_pipeline.log
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$log = "data/llm_pipeline.log"

function Step($name, [string[]]$cmd) {
    "`n=== $(Get-Date -Format s) START $name ===" | Out-File $log -Append -Encoding utf8
    & uv run --no-sync buglens @cmd 2>&1 | Where-Object { $_ -notmatch "Batches|warn" } |
        Out-File $log -Append -Encoding utf8
    "=== $(Get-Date -Format s) END $name (exit $LASTEXITCODE) ===" | Out-File $log -Append -Encoding utf8
}

# 1. Onboarding summaries + cited guides for the 3 demo repos
foreach ($r in "pallets/flask", "psf/requests", "django/django") {
    Step "summarize $r" @("summarize", "--repo", $r)
    Step "guide $r" @("guide", "--repo", $r)
}
# 2. S7: S5 -> Gemini rerank
Step "S7 test" @("llm", "--system", "S7", "--split", "test")
# 3. Summaries for the other test repos (RQ4 coverage), then S6b
foreach ($r in "astropy/astropy", "matplotlib/matplotlib", "mwaskom/seaborn", "pydata/xarray",
               "pylint-dev/pylint", "pytest-dev/pytest", "scikit-learn/scikit-learn",
               "sphinx-doc/sphinx", "sympy/sympy") {
    Step "summarize $r" @("summarize", "--repo", $r)
}
Step "S6b test" @("rerank", "--system", "S6b", "--split", "test")
# 4. Stretch M10: S8 and patches (the Docker harness is NOT run)
Step "S8 test" @("llm", "--system", "S8", "--split", "test")
Step "patches" @("patch", "--system", "S8", "--limit", "30")
# 5. Evaluation + report
Step "onboard-eval" @("onboard-eval")
Step "report" @("report")
"LLM PIPELINE DONE" | Out-File $log -Append -Encoding utf8
