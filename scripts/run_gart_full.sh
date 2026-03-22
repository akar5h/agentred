#!/usr/bin/env bash
set -e

ENGAGEMENT_ID="gart-hr-full-$(date +%Y%m%d-%H%M%S)"
echo "Engagement ID: $ENGAGEMENT_ID"

CATALOGS="
harness/attack/library/hr_ai/indirect_injection_v1.json
harness/attack/library/hr_ai/direct_injection_v1.json
harness/attack/library/hr_ai/tool_injection_v1.json
harness/attack/library/hr_ai/data_exfiltration_v1.json
harness/attack/library/hr_ai/tenant_boundary_v1.json
harness/attack/library/hr_ai/memory_poisoning_v1.json
harness/attack/library/hr_ai/score_manipulation_v1.json
harness/attack/library/hr_ai/search_exfil_v1.json
harness/attack/library/hr_ai/multi_agent_split_v1.json
harness/attack/library/hr_ai/adaptive_multi_turn_v1.json
"

COUNT=0
TOTAL=10
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
    --max-muzzle-cycles 3 \
    --top-k-vessels 3 \
    --engagement-id "$ENGAGEMENT_ID" \
    2>&1 || echo "WARN: $NAME had errors (continuing)"
  echo "--- $NAME complete ---"
done

echo ""
echo "=== ALL 10 CATALOGS COMPLETE ==="
echo "Engagement: $ENGAGEMENT_ID"
echo "Reports: reports/$ENGAGEMENT_ID/"
