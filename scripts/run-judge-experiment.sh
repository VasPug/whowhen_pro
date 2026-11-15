#!/usr/bin/env bash
set -euo pipefail

# Never enable shell tracing here: API keys must remain out of terminal logs.
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_root"
offline=false
for arg in "$@"; do
  if [[ "$arg" == "--offline" ]]; then offline=true; fi
done
if [[ "$offline" == false && -z "${OPENROUTER_API_KEY:-}" ]]; then
  if [[ -t 0 ]]; then
    read -r -s -p 'OpenRouter API key (hidden; not saved): ' OPENROUTER_API_KEY
    printf '\n'
    export OPENROUTER_API_KEY
  fi
  if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    printf 'Set OPENROUTER_API_KEY, or pass --offline for a synthetic test.\n' >&2
    exit 1
  fi
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import whowhen_eval, yaml, PIL, litellm' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements-experiment.lock
  .venv/bin/python -m pip install --no-deps -e .
fi
exec .venv/bin/python -m whowhen_eval.experiment run --config configs/judge-harness.yaml "$@"
