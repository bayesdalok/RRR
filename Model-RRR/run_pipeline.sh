#!/usr/bin/env bash
# Runs the full rural-risk-radar pipeline, scripts 00-12, in order.
# All 13 scripts are expected to exit 0 given the consistent xlsx source
# data (rural-risk-radar_1.xlsx) — see docs/PROGRESS_LOG.md for the earlier
# PDF-sourced run where scripts 01 and 10 were expected to fail.
set -e
cd "$(dirname "$0")"

for script in scripts/0[0-9]_*.py scripts/1[012]_*.py; do
    echo ""
    echo "=================================================================="
    echo "Running $script"
    echo "=================================================================="
    python3 "$script"
done

echo ""
echo "Pipeline complete. Open reports/rural_risk_radar_dashboard.html to view results."
