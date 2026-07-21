#!/usr/bin/env bash
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
AUDIT="data/audits/selection_challenger_resolution"
mkdir -p "$AUDIT"

cleanup_and_publish() {
  rm -f data/lake/batches/__selection_challenger_reconstructed_players.csv
  git rm -f .github/workflows/run-frozen-challenger-resolution-once.yml \
    .github/workflows/resolve-selection-challengers.yml \
    ops/resolve-selection-challengers-trigger.txt \
    ops/resolve-selection-challengers-trigger-branch.txt 2>/dev/null || true
  git config user.name "synthetic-xi-bot"
  git config user.email "actions@users.noreply.github.com"
  git add "$AUDIT" data/audits/scope_correct_coverage \
    data/model_readiness/player_window_coverage.csv \
    data/model_readiness/selection_challenger_reconstructed_minutes.csv \
    data/model_readiness/selection_sufficiency_all_players.csv \
    data/model_readiness/selection_sufficiency_unresolved_players.csv \
    data/model_readiness/selection_sufficiency_priority_fixtures.csv \
    data/model_readiness/coverage_priority_fixtures.csv \
    data/model_readiness/selection_sufficiency_status.json \
    data/model_readiness/scientific_validation_status.json \
    data/simulations/complete_final_v1 2>/dev/null || true
  git add -f data/lake/selection_challenger_evidence 2>/dev/null || true
  if ! git diff --cached --quiet; then
    git commit -m "science: resolve frozen selection challengers and rebuild final gate"
    for attempt in 1 2 3 4 5; do
      git fetch origin main
      if git rebase -X theirs origin/main && git push origin HEAD:main; then
        return 0
      fi
      git rebase --abort 2>/dev/null || true
      sleep $((attempt * 4))
    done
    return 1
  fi
}

unresolved_count=$(($(wc -l < data/model_readiness/selection_sufficiency_unresolved_players.csv)-1))
if [[ "$unresolved_count" -ne 41 ]]; then
  printf '{"status":"one_shot_skipped","reason":"frozen_challenger_count_not_41","observed":%s}\n' \
    "$unresolved_count" > "$AUDIT/one_shot_skip_status.json"
  cleanup_and_publish
  exit 0
fi

cp data/model_readiness/selection_sufficiency_unresolved_players.csv \
  "$AUDIT/frozen_unresolved_before.csv"
cp data/model_readiness/selection_sufficiency_status.json \
  "$AUDIT/frozen_selection_status_before.json"
sha256sum data/model_readiness/selection_frontier_all_candidates.csv \
  scripts/build_selection_sufficiency_gate.py \
  scripts/build_selection_frontier.py > "$AUDIT/frozen_model_inputs.sha256"

rm -f ops/use-final-daily-calls.flag
pipeline_code=0
python scripts/scientific/extract_selection_challenger_fixture_evidence.py || pipeline_code=$?
if [[ "$pipeline_code" -eq 0 ]]; then
  python scripts/scientific/reconstruct_selection_challenger_minutes.py || pipeline_code=$?
fi
if [[ "$pipeline_code" -eq 0 ]]; then
  python scripts/scientific/build_scope_correct_coverage_v3.py || pipeline_code=$?
fi
if [[ "$pipeline_code" -eq 0 ]]; then
  python scripts/scientific/shadow_scope_correct_selection.py || pipeline_code=$?
  python scripts/scientific/promote_scope_correct_coverage.py || pipeline_code=$?
  rm -f data/lake/batches/__selection_challenger_reconstructed_players.csv
  python scripts/build_selection_sufficiency_gate.py || pipeline_code=$?
  python scripts/scientific/audit_selection_challenger_uncertainty.py || pipeline_code=$?
  python scripts/build_scientific_status.py || pipeline_code=$?
fi

if [[ "$pipeline_code" -eq 0 ]]; then
  sha256sum -c "$AUDIT/frozen_model_inputs.sha256" || pipeline_code=$?
fi
if [[ "$pipeline_code" -eq 0 ]]; then
  python scripts/scientific/release_complete_final_when_ready.py \
    --simulations 10000 --validation-simulations 2000 || pipeline_code=$?
fi

PIPELINE_CODE="$pipeline_code" python - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

def load(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.exists() else {}
selection=load('data/model_readiness/selection_sufficiency_status.json')
scientific=load('data/model_readiness/scientific_validation_status.json')
release=load('data/simulations/complete_final_v1/release_gate_status.json')
audit=load('data/audits/selection_challenger_resolution/uncertainty_bound_audit.json')
status={
    'status':'selection_challenger_resolution_completed',
    'generated_at_utc':datetime.now(timezone.utc).isoformat(),
    'pipeline_exit_code':int(os.environ['PIPELINE_CODE']),
    'selection_sufficiency_gate_passed':bool(selection.get('selection_sufficiency_gate_passed',False)),
    'unresolved_players':selection.get('unresolved_players'),
    'final_team_comparison_allowed':bool(scientific.get('final_team_comparison_allowed',False)),
    'complete_final_release_status':release.get('status'),
    'uncertainty_audit_passed':bool(audit.get('audit_passed',False)),
    'model_parameters_changed':bool(audit.get('model_parameters_changed',False)),
    'thresholds_changed':bool(audit.get('selection_thresholds_changed',False)),
}
Path('data/audits/selection_challenger_resolution/final_resolution_status.json').write_text(
    json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(status,ensure_ascii=False,indent=2))
PY

cleanup_and_publish || pipeline_code=90

python - <<'PY'
import json
from pathlib import Path
status=json.loads(Path('data/audits/selection_challenger_resolution/final_resolution_status.json').read_text())
assert status['pipeline_exit_code'] == 0, status
assert status['selection_sufficiency_gate_passed'] is True, status
assert status['unresolved_players'] == 0, status
assert status['final_team_comparison_allowed'] is True, status
assert status['uncertainty_audit_passed'] is True, status
assert status['model_parameters_changed'] is False, status
assert status['thresholds_changed'] is False, status
PY
