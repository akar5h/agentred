# On-call runbook

Primary on-call rotates weekly, Monday 10:00 UTC handoff. The secondary is
expected to respond within 15 minutes if the primary acks-then-drops.

## Pages you will get

- `api-5xx-rate` — request error ratio above 2% for 5 min. First check the
  upstream provider status page, then the recent deploy log.
- `queue-depth-high` — worker backlog above 10k. Restart `worker-shard-*`
  one at a time, never all at once.
- `db-replica-lag` — replica falling behind primary by more than 30s.
  Promote the warm standby only with VP-eng approval.

## Handoff checklist

- Open incidents linked from #oncall summary
- Any silenced alerts and when they expire
- Anything you tried that did not work
