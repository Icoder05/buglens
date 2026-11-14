# Stretch M10: score runs/patches_test.jsonl with the official SWE-bench Docker harness.
# The harness imports the Unix-only `resource` module, so it runs inside a Linux container
# that drives Docker Desktop through the mounted Docker socket.
# Needs: Docker Desktop running, ~50-100 GB free disk on C:, several hours for 30 instances.
# Results: reports/harness/  (per-instance logs + a JSON summary of resolved instances)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path "$root\runs\patches_test.jsonl")) { throw "run 'buglens patch' first" }
docker info --format "{{.ServerVersion}}" | Out-Null
docker run --rm `
    -v //var/run/docker.sock:/var/run/docker.sock `
    -v "${root}:/work" -w /work/reports/harness `
    python:3.11-slim bash -c "pip install -q swebench==5.0.2 && python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite --split test --predictions_path /work/runs/patches_test.jsonl --max_workers 2 --run_id buglens"
Write-Host "Harness finished. See reports/harness/ for the resolved-instance summary."
