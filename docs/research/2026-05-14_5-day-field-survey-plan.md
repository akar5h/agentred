---
date: 2026-05-14
status: plan, hard time-box
window: 2026-05-15 → 2026-05-19 (5 working days)
owner: akarsh
deliverable: one synthesis doc + one decision (which harness to extend for MUZZLE)
no-go: coding the MUZZLE plug-in, production polish, public artifacts
---

# 5-Day Field Harness Survey — Pre-work for `jakk` v0.1

## Why this week exists

Before productizing the grafted/MUZZLE engine as `jakk` (a CLI you point at your
MCP host), study how the existing MCP-security research field actually wires
real installed clients (Claude Code, Cursor) up to automated attack
infrastructure. Reuse what's already engineered. Steal canary detection.
Identify what's missing.

End-of-week, we should be able to answer four questions:

1. Which published harness do we extend for the v0.1 MUZZLE plug-in (or do we
   build our own from parts)?
2. What's the baseline static-attack ASR on Claude Code and Cursor that
   MUZZLE-adaptive needs to beat?
3. What detection methodology do we adopt (likely MCPHunt-style canaries —
   confirm by inspection)?
4. What's the v0.1 scope we're committing to, given what we now know exists?

## Hard scope rails

In-scope this week:
- Clone, bring up, and run experiments in published MCP-security codebases
- Document patterns we'd reuse
- Reproduce ONE published ASR number as a sanity check
- Internal write-ups

Out-of-scope this week:
- Coding any MUZZLE plug-in into a harness
- Building any new attack
- Production polish (Docker, packaging, README copy, demo GIF)
- Public artifacts (no blog, no tweet, no HN draft)
- Reimplementing TIP / AdapTools from paper
- Anything that doesn't route back to one of the four questions above

## The five codebases (all verified runnable via prior search)

| Project | Repo | Why it matters |
|---|---|---|
| **MCPSecBench** | `AIS2Lab/MCPSecBench` | THE real-client driving template. Tests Claude Desktop, OpenAI, Cursor. 17 static attacks. GUI automation via image-matching (brittle). |
| **MSB** | `dongsenzhang/MSB` | ICLR 2026. Cleanest 12-attack taxonomy. 9 agents × 10 domains × 405 tools. Dataset on HuggingFace. |
| **MCPTox** | `zhiqiangwang4/MCPTox-Benchmark` | Tests against 45 real community MCP servers + 353 authentic tools. 20 LLM agents. AAAI. |
| **MCPHunt** | open-source per paper (URL tbd Day 1) | Canary methodology + CRS stratification. The detection layer to steal. |
| **mcp-breach-to-fix-labs** | `PawelKozy/mcp-breach-to-fix-labs` | Community-grade craft for security demos. 88★. Cursor/Claude Code battle-tested. Docker Compose. The polish bar for v0.1. |

Targets in our local env:
- **Claude Code** (CLI, already installed, MCP support via `claude mcp ...`)
- **Cursor** (already installed, MCP config at `~/.cursor/mcp.json`)

Not testing this week: Claude Desktop, Continue, Windsurf. Add later if v0.1
scope expands.

## Day-by-day breakdown

### Day 1 — Mon 2026-05-15 — Clone + bring-up status (4-6 hours)

Goal: every repo on disk, status documented, ONE attack fires against Cursor.

Tasks:
1. Create `~/dev/mcp-survey/` workdir. Clone all 5 repos.
2. Confirm local MCP plumbing (`claude mcp list`, Cursor settings → MCP).
3. Bring up MCPSecBench first; fall back to PawelKozy if their deps explode.
4. Fire ONE attack from whichever came up against installed Cursor.
5. Write `docs/research/2026-05-15_field-harness-survey.md` — Day 1 status.

End-of-day deliverable:
- `2026-05-15_field-harness-survey.md` with 5-row status table + one attack
  result against Cursor (succeeded / blocked / unclear).

Stop conditions:
- After status doc is written, regardless of how many repos came up.
- Do NOT start Day 2 work today.

### Day 2 — Tue 2026-05-16 — MCPSecBench deep dive (6-8 hours)

Goal: understand how MCPSecBench drives Cursor end-to-end, reproduce ONE
published number.

Tasks:
1. Read `MCPSecBench/main.py` — note exactly how it: writes Cursor config,
   restarts the client, detects when a tool call fires, captures the result.
2. Identify image-matching points; sketch the file-tail replacement we'd build
   for v0.1 (do NOT build it — just note where it would go).
3. Run their full attack suite against Cursor on the current installed version.
   Document which attacks fire, ASR per attack, any breakage.
4. Pick ONE of their published numbers (e.g., shadowing ASR on Cursor) and
   confirm your local reproduction lands in the same neighborhood (±10pp).
5. Append findings to `2026-05-15_field-harness-survey.md` under a Day 2
   section.

End-of-day deliverable:
- Day 2 section in survey doc.
- One reproduced ASR number with diff vs paper.
- Note on which MCPSecBench files are reusable vs need replacement.

### Day 3 — Wed 2026-05-17 — MSB or MCPTox deep dive (6-8 hours)

Goal: understand the other major attack taxonomy + how it scales to broader
MCP server ecosystem.

Decision rule: pick MSB if Day 2's question is "what attacks should jakk's
catalog include?", pick MCPTox if it's "how do we test against arbitrary
community MCP servers."

Tasks:
1. Read whichever's `README` + main attack-loop code.
2. Bring up their pipeline. Run against Claude Code or OpenAI tool-loop (not
   Cursor — already covered by Day 2). API-level victim is fine for these.
3. Compare their taxonomy to MCPSecBench's 17 — note overlaps and gaps.
4. Append Day 3 section to survey doc.

End-of-day deliverable:
- Day 3 section.
- Side-by-side taxonomy comparison (MSB's 12 vs MCPSecBench's 17 vs MCPTox's
  10).

### Day 4 — Thu 2026-05-18 — MCPHunt canary detection focus (3-4 hours, half day)

Goal: extract MCPHunt's detection layer cleanly so MUZZLE can adopt it.

Tasks:
1. Find MCPHunt's repo (start from arxiv 2604.27819 PDF, may need to email
   authors if URL absent).
2. Read their canary code. Document: the canary format library
   (`sk_live_*`, `AKIA*`, `ghp_*`...), the detection function, the CRS
   stratification logic.
3. Sketch — IN PROSE, NOT CODE — what a `grafted/detection/canary.py` module
   would look like, modeled on MCPHunt's pattern.
4. Don't run their full benchmark. Focus only on the detection layer.

Optional Day 4 afternoon: skim PawelKozy's repo. 10 incident reproducers,
Docker Compose layouts, README structure. 1-2 hours max. Capture what the
polish bar looks like; do not try to match it yet.

End-of-day deliverable:
- Day 4 section.
- Prose sketch of canary detection module.
- Notes on PawelKozy's craft conventions.

### Day 5 — Fri 2026-05-19 — Synthesis + decision (6-8 hours)

Goal: one synthesis doc, one decision, ready to start coding Monday.

Tasks:
1. Write `docs/research/2026-05-19_field-survey-synthesis.md`:
   - Methodology comparison table across the 4 harnesses
   - MUZZLE 7-step loop mapped onto where each step replaces or extends the
     static-catalog approach in MCPSecBench / MSB / MCPTox
   - Static baseline numbers (from Day 2 reproduction) we'll compare against
   - Decision: which harness do we extend? (best guess pre-week: MCPSecBench)
   - Open questions deferred to v0.1 build phase
2. One paragraph: "Given what we learned, v0.1 ship looks like X, with Y as
   the headline number."
3. Email TIP and AdapTools authors today if not done already (5 min each):
   - Xudong Pan (xdpan@fudan.edu.cn), Min Yang (m_yang@fudan.edu.cn) — TIP
   - Che Wang (chewang@stu.pku.edu.cn) — AdapTools
   - Standard ask: "I'm reproducing your work for a public OSS tool, would
     you share code privately or coordinate release?"
4. Update [[memory]] with the chosen harness + baseline numbers as a project
   memory entry.

End-of-week deliverable:
- `2026-05-19_field-survey-synthesis.md`
- One named decision (harness to extend)
- One named baseline number (reproduced from MCPSecBench)
- Three emails sent

## Success criteria for the week

- [ ] 3-of-5 repos brought up end-to-end. (5/5 ideal, 2/5 means something
      systemic is wrong with our env.)
- [ ] 1 published ASR number reproduced within ±10pp on Cursor or Claude
      Code.
- [ ] MUZZLE → MCP harness integration path written down in prose.
- [ ] Canary detection design sketched.
- [ ] One decision: which harness do we extend or do we build from parts.

If 4-of-5 hit, the week was productive. If <2, stop and reassess.

## Open questions deferred to mid-week

Resolve at end-of-Day-2, not now:

- API-level fallback acceptable for Day 3 if Cursor automation is too brittle?
- Should we add Claude Desktop to the target set if MCPSecBench gives us most
  of that for free?
- Is one-shot attack ASR sufficient for the baseline, or do we need
  multi-turn baselines for fair MUZZLE comparison? (Probably one-shot is fine
  for a first pass.)

## Anti-pattern alarms

Stop and ask if you find yourself:

- Building a MUZZLE plug-in this week (that's next week)
- Improving an existing repo's code instead of just running it
- Spending >2 hours getting one repo's deps to work — switch to fallback
- Drifting into "let me also try X benchmark I just heard about"
- Writing public-facing content (blog, tweet) — all internal this week
- Reading TIP or AdapTools papers more than once

## Files this plan produces

End of week, the `docs/research/` tree gains:

```
docs/research/
├── 2026-05-14_5-day-field-survey-plan.md     ← THIS DOC
├── 2026-05-15_field-harness-survey.md        ← Day 1 + appended through Day 4
└── 2026-05-19_field-survey-synthesis.md      ← Day 5 final
```

No code changes to `grafted/` this week. Survey work is read-only against
existing repos plus markdown writes here.
