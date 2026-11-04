#!/bin/bash -l
# Runs the pipeline for one profile on Explorer (DuckDB backend, config/explorer.yml).
#
# From the repository folder on a login node, with .venv set up (README, "Running on Explorer"):
#   bash scripts/explorer_job.sbatch sample_1pct
#   SHARP_TIME=12:00:00 bash scripts/explorer_job.sbatch full
#   SHARP_FROM=4_matching bash scripts/explorer_job.sbatch full     (resume a failed run)
# Run this way, the script submits itself with the time limit from SHARP_TIME (default 08:00:00)
# and the Slurm log in <extracts_dir>/logs/, never in the repository: an error message can quote
# a value from the data. Plain `sbatch --export=ALL,PROFILE=full scripts/explorer_job.sbatch` also
# works (time from the line below); the job then writes its log to the same folder itself.
#SBATCH --job-name=sharp
#SBATCH --partition=short
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=/dev/null
set -eo pipefail

logs_folder() {
    local extracts
    extracts="$(PYTHONNOUSERSITE=1 .venv/bin/python -c 'from runner import config; print(config.load().extracts_dir)')"
    if [[ -z "$extracts" ]]; then
        echo "config/explorer.yml (backend: duckdb) is needed to run on Explorer." >&2
        exit 1
    fi
    mkdir -p "$extracts/logs"
    echo "$extracts/logs"
}

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    profile="${1:?usage: bash scripts/explorer_job.sbatch <sample_1pct|sample_30pct|full>}"
    logs="$(logs_folder)"
    exec sbatch --time="${SHARP_TIME:-08:00:00}" --job-name="sharp-$profile" \
        --output="$logs/sharp-$profile-%j.log" --export=ALL,PROFILE="$profile" "$0"
fi

cd "$SLURM_SUBMIT_DIR"
module load anaconda3/2024.06
export PYTHONNOUSERSITE=1
source .venv/bin/activate
set -u
logs="$(logs_folder)"
exec >>"$logs/sharp-${PROFILE:-unset}-$SLURM_JOB_ID.log" 2>&1
: "${PROFILE:?set PROFILE: bash scripts/explorer_job.sbatch <profile>}"
echo "job $SLURM_JOB_ID on $(hostname): profile $PROFILE, ${SLURM_CPUS_PER_TASK:-?} CPUs, ${SLURM_MEM_PER_NODE:-?} MB"
python -m runner --profile "$PROFILE" ${SHARP_FROM:+--from "$SHARP_FROM"}
