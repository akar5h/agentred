#!/usr/bin/env bash
set -e

ENGAGEMENT_ID="gart-trd24-$(date +%Y%m%d-%H%M%S)"
echo "Engagement ID: $ENGAGEMENT_ID"
echo "Budget run: 5 catalogs, 2 cycles, 2 vessels"

CATALOGS="
harness/attack/library/hr_ai/memory_poisoning_v1.json
harness/attack/library/hr_ai/direct_injection_v1.json
harness/attack/library/hr_ai/indirect_injection_v1.json
harness/attack/library/hr_ai/tenant_boundary_v1.json
harness/attack/library/hr_ai/score_manipulation_v1.json
"

COUNT=0
TOTAL=5
for CAT in $CATALOGS; do
  COUNT=$((COUNT + 1))
  NAME=$(basename "$CAT" .json)
  echo ""
  echo "=== [$COUNT/$TOTAL] $NAME ==="
  echo ""
  python scripts/run_campaign.py \
    --catalog "$CAT" \
    --base-url http://localhost:8000 \
    --hr-ai \
    --adaptive \
    --max-muzzle-cycles 2 \
    --top-k-vessels 2 \
    --engagement-id "$ENGAGEMENT_ID" \
    2>&1 || echo "WARN: $NAME had errors (continuing)"
  echo "--- $NAME complete ---"
done

echo ""
echo "=== ALL 5 CATALOGS COMPLETE ==="
echo "Engagement: $ENGAGEMENT_ID"
echo "Reports: reports/$ENGAGEMENT_ID/"
