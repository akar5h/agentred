#!/usr/bin/env bash
set -e

ENGAGEMENT="hr-budget-$(date +%Y%m%d-%H%M%S)"
BASE_URL="http://localhost:8000"
echo "=== HR AI Budget Campaign: $ENGAGEMENT ==="
echo "Goal: max traces, ~\$3 budget"
echo ""

# -------------------------------------------------------
# Phase 1: ALL 10 catalogs, non-adaptive (near-zero cost)
# Just fires static catalog turns — no LLM synthesis
# -------------------------------------------------------
echo ">>> PHASE 1: Static catalog sweep (10 suites, ~54 scenarios)"
echo ""

for CAT in harness/attack/library/hr_ai/*.json; do
  NAME=$(basename "$CAT" .json)
  echo "  [$NAME] running..."
  python scripts/run_campaign.py \
    --catalog "$CAT" \
    --base-url "$BASE_URL" \
    --hr-ai \
    --no-muzzle \
    --runs-per-scenario 1 \
    --engagement-id "$ENGAGEMENT" \
    2>&1 | tail -1 || echo "  [$NAME] had errors (continuing)"
done

echo ""
echo ">>> PHASE 1 COMPLETE"
echo ""

# -------------------------------------------------------
# Phase 2: Top 3 catalogs, adaptive chain + 1 MUZZLE cycle
# These have upload + chat + memory surfaces = most diverse
# -------------------------------------------------------
echo ">>> PHASE 2: Adaptive runs (3 suites, 1 cycle each)"
echo ""

ADAPTIVE_CATALOGS=(
  "harness/attack/library/hr_ai/indirect_injection_v1.json"
  "harness/attack/library/hr_ai/memory_poisoning_v1.json"
  "harness/attack/library/hr_ai/score_manipulation_v1.json"
)

for CAT in "${ADAPTIVE_CATALOGS[@]}"; do
  NAME=$(basename "$CAT" .json)
  echo "  [$NAME] adaptive run..."
  python scripts/run_campaign.py \
    --catalog "$CAT" \
    --base-url "$BASE_URL" \
    --hr-ai \
    --adaptive \
    --max-muzzle-cycles 1 \
    --top-k-vessels 2 \
    --runs-per-scenario 1 \
    --engagement-id "$ENGAGEMENT" \
    2>&1 | tail -1 || echo "  [$NAME] had errors (continuing)"
done

echo ""
echo "=== CAMPAIGN COMPLETE ==="
echo "Engagement: $ENGAGEMENT"
echo "Reports: reports/$ENGAGEMENT/"
echo ""

# Quick summary
python -c "
import csv, json, os, glob

edir = 'reports/$ENGAGEMENT'
total = success = partial = blocked = infra = 0
for f in glob.glob(os.path.join(edir, '**', 'runs.jsonl'), recursive=True):
    with open(f) as fh:
        for line in fh:
            if not line.strip(): continue
            r = json.loads(line)
            total += 1
            s = r.get('status', '')
            if s == 'Success': success += 1
            elif s == 'Partial': partial += 1
            elif s == 'Blocked': blocked += 1
            elif s == 'InfraFail': infra += 1

print(f'Total scenarios: {total}')
print(f'  Success:   {success}')
print(f'  Partial:   {partial}')
print(f'  Blocked:   {blocked}')
print(f'  InfraFail: {infra}')
print(f'  Hit rate:  {100*success//max(total,1)}%')
"
