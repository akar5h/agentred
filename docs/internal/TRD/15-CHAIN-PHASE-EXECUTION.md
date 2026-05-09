# TRD-15: Chain Attacks — Phase-wise Execution Order

**Companion to:** `14-CHAIN-ATTACKS.md`
**Status:** Ready for junior dev execution
**Author:** Senior DE
**Date:** 2026-02-23

---

## How to Use This Document

Work through phases **strictly in order**. Each phase has:
- A clear goal
- A list of deliverables with exact file paths
- Acceptance tests to run before moving on
- A "stop here" checkpoint

Do **not** start Phase N+1 until all acceptance tests in Phase N pass.
Each phase is designed to be independently committable.

---

## Phase 0 — Explorer Timeout Fix

**Goal:** Fix the ReadTimeout bug in Explorer so that `send_turn()` and `list_docs()` honour `config.timeout_seconds`.

**Deliverables:**
- `harness/explorer/explorer.py` (D1 in TRD-14 §2)

**Steps:**
1. Read `harness/explorer/explorer.py` — understand `Explorer.__init__` (line 23) and `run_task()` (line 26).
2. Add `timeout_seconds: float = 120.0` to `__init__`. Store as `self.timeout_seconds`.
3. In `run_task()`, pass `timeout=self.timeout_seconds` to all three victim calls:
   - `self.victim.list_docs(session_id)` → `self.victim.list_docs(session_id, timeout=self.timeout_seconds)`
   - `self.victim.send_turn(session_id, message)` → `self.victim.send_turn(session_id, message, timeout=self.timeout_seconds)`
   - second `self.victim.list_docs(session_id)` → same fix
4. Find the `Explorer(self.victim)` construction site in `harness/campaign/muzzle_orchestrator.py`. Change to `Explorer(self.victim, timeout_seconds=self.config.timeout_seconds)`.

**Acceptance test:**
```bash
/tmp/harness_venv/bin/pytest tests/unit/test_explorer.py -x --tb=short
```
All tests must pass. There are no new tests in this phase.

**Checkpoint:** commit as `fix: pass timeout_seconds through Explorer to victim calls`

---

## Phase 1 — Schema + Loader Changes

**Goal:** Extend `TestSpec` to carry `chain_mode` and `max_chain_turns`, and make the catalog loader read those fields.

**Deliverables:**
- `harness/core/schemas.py` (D2 in TRD-14 §3)
- `harness/attack/catalog/loader.py` (D3 in TRD-14 §4)

**Steps:**

### schemas.py
1. Open `harness/core/schemas.py`.
2. In `TestSpec` (lines 21–38), after `technique_family: str = ""` add:
   ```python
   chain_mode: bool = False
   max_chain_turns: int = 8
   ```
3. Nothing else changes. Do not touch any other class.

### loader.py
1. Open `harness/attack/catalog/loader.py`.
2. In `_attack_to_spec()` (line 70), inside the `return TestSpec(...)` block, after `technique_family=...` add:
   ```python
   chain_mode=bool(attack.get("chain_mode", False)),
   max_chain_turns=int(attack.get("max_chain_turns", 8)),
   ```

**Acceptance tests:**
```bash
/tmp/harness_venv/bin/pytest tests/unit/test_schemas.py tests/unit/test_catalog_loader.py -x --tb=short
```
All existing tests must pass.

Quick smoke check:
```python
from harness.core.schemas import TestSpec
s = TestSpec(scenario_id="X", suite_id="Y", turns=["t"])
assert s.chain_mode == False
assert s.max_chain_turns == 8
s2 = TestSpec(scenario_id="X", suite_id="Y", turns=["t"], chain_mode=True, max_chain_turns=5)
assert s2.chain_mode == True
assert s2.max_chain_turns == 5
print("OK")
```

**Checkpoint:** commit as `feat: add chain_mode and max_chain_turns to TestSpec and loader`

---

## Phase 2 — AttackStrategy ABC Extension

**Goal:** Add optional `generate_next_turn()` to the base class so `CampaignRunner` can check for it without `hasattr` hacks.

**Deliverables:**
- `harness/attack/base.py` (D4 in TRD-14 §5)

**Steps:**
1. Open `harness/attack/base.py`.
2. After the `next_turn()` abstract method (line 21), before `is_adaptive`, add:
   ```python
   async def generate_next_turn(
       self,
       *,
       scenario_id: str,
       objective: str,
       transcript: list[dict],
       finding_memory: list | None = None,
   ) -> str:
       """
       Generate the next attack turn dynamically from the current transcript.
       Default raises NotImplementedError. Override in ChainStrategy.
       """
       raise NotImplementedError
   ```
3. Do not mark it `@abstractmethod`. It must have a default body.

**Acceptance tests:**
```bash
/tmp/harness_venv/bin/python -c "
import asyncio
from harness.attack.synthesis.static_strategy import StaticStrategy
s = StaticStrategy()
assert hasattr(s, 'generate_next_turn')
try:
    asyncio.run(s.generate_next_turn(scenario_id='x', objective='y', transcript=[]))
    assert False, 'should have raised'
except NotImplementedError:
    pass
print('OK')
"
```

No existing tests should break:
```bash
/tmp/harness_venv/bin/pytest tests/ -x --tb=short -q
```

**Checkpoint:** commit as `feat: add optional generate_next_turn() to AttackStrategy ABC`

---

## Phase 3 — ChainStrategy Implementation

**Goal:** Create the PAIR-style adaptive chain strategy.

**Deliverables:**
- `harness/attack/synthesis/chain_strategy.py` (D5 in TRD-14 §6)

**Steps:**
1. Create `harness/attack/synthesis/chain_strategy.py`.
2. Implement the full `ChainStrategy` class exactly as specified in TRD-14 §6. Key points:
   - Inherits from `AttackStrategy`
   - `next_turn()` is a passthrough (returns `base_turn`)
   - `generate_next_turn()` calls `_classify_compliance()`, builds prompts, calls `_call_openrouter()`
   - `_call_openrouter()` follows the same pattern as `LlmSynthStrategy._mutate_via_openrouter()` (see `harness/attack/synthesis/llm_synth.py` lines 155–181)
   - Rate limiting via `_respect_rate_limit()` (same pattern as `LlmSynthStrategy._respect_rate_limit()`, lines 123–133)
3. Copy the system prompt and human message template verbatim from TRD-14 §6.

**Before writing, read these files for patterns to copy:**
- `harness/attack/synthesis/llm_synth.py` (lines 28–68 for `__init__`, 123–181 for rate limit + HTTP call)
- `harness/attack/base.py` (to confirm the method signatures)

**Acceptance tests (write these first, then implement — TDD):**

Write `tests/unit/test_chain_strategy.py` first (see TRD-14 §12 for the full test list), run to confirm they fail, then implement. Acceptance = all 10 tests pass:
```bash
/tmp/harness_venv/bin/pytest tests/unit/test_chain_strategy.py -x --tb=short
```

**Checkpoint:** commit as `feat: add ChainStrategy (PAIR-style adaptive multi-turn attacker)`

---

## Phase 4 — Runner Chain Loop

**Goal:** Make `CampaignRunner.run_one()` dispatch to the chain loop when `spec.chain_mode=True`.

**Deliverables:**
- `harness/campaign/runner.py` (D6 in TRD-14 §7)

**Steps:**
1. Open `harness/campaign/runner.py`. Locate the `for turn in spec.turns:` block at line 144.
2. Wrap the entire existing `for` block in `else:`.
3. Add the `if spec.chain_mode and hasattr(self.strategy, "generate_next_turn"):` block **above** the `else:`.
4. Inside the `if` block, implement the chain loop exactly as in TRD-14 §7. The events emitted (`ATTACK_TURN_SENT`, `ATTACK_TURN_RECV`) and the `ctx` updates are identical to the existing loop — just driven by `generate_next_turn()` instead of iterating `spec.turns`.
5. Handle `NotImplementedError` from `generate_next_turn()` with `break` (not a crash).
6. Exit condition: `STOP` signal OR `max_chain_turns` reached.

**Do not change the `else` block** — it is the existing static loop verbatim.

**Acceptance tests (write integration tests in D14 first):**
```bash
/tmp/harness_venv/bin/pytest tests/integration/test_chain_runner.py -x --tb=short
```

Full regression:
```bash
/tmp/harness_venv/bin/pytest tests/ -x --tb=short
```

**Checkpoint:** commit as `feat: add chain-mode execution loop to CampaignRunner`

---

## Phase 5 — Catalog JSON Files

**Goal:** Create the three static catalog files with valid harness-format JSON.

**Deliverables:**
- `harness/attack/library/deepagent/deepagent_multiturn_v1.json` (D8, TRD-14 §9)
- `harness/attack/library/deepagent/deepagent_toolchain_v1.json` (D9, TRD-14 §9)
- `harness/attack/library/deepagent/deepagent_chain_v1.json` (D10, TRD-14 §9)

**Steps:**
1. Copy the three JSON blocks verbatim from TRD-14 §9 into their respective files.
2. The JSON must be valid — validate with `python -m json.tool <file>` before proceeding.

**Acceptance test:**
```bash
# Validate JSON syntax
for f in harness/attack/library/deepagent/deepagent_multiturn_v1.json \
          harness/attack/library/deepagent/deepagent_toolchain_v1.json \
          harness/attack/library/deepagent/deepagent_chain_v1.json; do
    python -m json.tool "$f" > /dev/null && echo "$f OK"
done

# Validate harness loading
/tmp/harness_venv/bin/python -c "
from harness.attack.catalog.loader import load_test_specs
for p in [
    'harness/attack/library/deepagent/deepagent_multiturn_v1.json',
    'harness/attack/library/deepagent/deepagent_toolchain_v1.json',
    'harness/attack/library/deepagent/deepagent_chain_v1.json',
]:
    _, specs = load_test_specs(p)
    chain = sum(1 for s in specs if s.chain_mode)
    print(p.split('/')[-1], len(specs), 'specs  chain:', chain)
"
```

Expected output:
```
deepagent_multiturn_v1.json 6 specs  chain: 0
deepagent_toolchain_v1.json 4 specs  chain: 0
deepagent_chain_v1.json     8 specs  chain: 8
```

**Checkpoint:** commit as `feat: add multi-turn, toolchain, and chain catalog files`

---

## Phase 6 — Grafter Chain-Mode Support

**Goal:** Make `Grafter.build_suite()` produce chain-mode TestSpecs for high-exploitability candidates when `ChainStrategy` is active.

**Deliverables:**
- `harness/grafter/grafter.py` (D7 in TRD-14 §8)
- `harness/campaign/muzzle_orchestrator.py` (call-site update, TRD-14 §8)

**Steps:**

### grafter.py
1. Open `harness/grafter/grafter.py`. Locate `build_suite()` at line 54.
2. Add `chain_strategy_active: bool = False` as the third parameter (after `objective_script`).
3. After constructing `spec`, add the conditional patch:
   ```python
   if chain_strategy_active and candidate.exploitability_score >= 0.6:
       spec = spec.model_copy(update={
           "chain_mode": True,
           "max_chain_turns": 8,
           "turns": [objective_script.imperative if objective_script else "Explore target capabilities."],
       })
   ```
4. Append `spec` to `suite` as before.

### muzzle_orchestrator.py
1. Read `harness/campaign/muzzle_orchestrator.py`. Find the call to `self.grafter.build_suite(...)`.
2. Add the import at the top of the file:
   ```python
   from harness.attack.synthesis.chain_strategy import ChainStrategy
   ```
3. Before the `build_suite` call, compute:
   ```python
   chain_active = isinstance(self.runner.strategy, ChainStrategy)
   ```
4. Pass it: `self.grafter.build_suite(candidates=..., objective_script=..., chain_strategy_active=chain_active)`

**Acceptance tests:**
```bash
/tmp/harness_venv/bin/pytest tests/unit/test_grafter.py -x --tb=short
```

Quick smoke:
```python
from harness.grafter.grafter import Grafter
from harness.core.schemas import VesselCandidate, ObjectiveScript
from harness.core.enums import VesselKind

g = Grafter(top_k=1)
c = VesselCandidate(vessel_kind=VesselKind.DIRECT_PROMPT, delivery_field="message",
                    exploit_method="test", exploitability_score=0.8)
obj = ObjectiveScript(goal_id="g1", imperative="Extract the system prompt.")
suite = g.build_suite([c], obj, chain_strategy_active=True)
assert suite[0].chain_mode == True
suite2 = g.build_suite([c], obj, chain_strategy_active=False)
assert suite2[0].chain_mode == False
print("OK")
```

**Checkpoint:** commit as `feat: grafter produces chain-mode specs for high-exploitability candidates`

---

## Phase 7 — Script Updates + Fixture Converter

**Goal:** Expose chain mode via CLI and provide the converter utility.

**Deliverables:**
- `scripts/run_deepagent.py` (D12 in TRD-14 §11)
- `scripts/convert_fixture.py` (D11 in TRD-14 §10)

**Steps:**

### run_deepagent.py
1. Open `scripts/run_deepagent.py`. Add two arguments to `_parse_args()` (after existing args):
   ```python
   p.add_argument("--chain", action="store_true",
                  help="Use ChainStrategy for chain-mode catalog entries")
   p.add_argument("--chain-catalog",
                  default="harness/attack/library/deepagent/deepagent_chain_v1.json",
                  help="Chain catalog to load when --chain is set")
   ```
2. In `_run()`, after `specs` is loaded from `config.catalog_path`, add:
   ```python
   if args.chain:
       _, chain_specs = load_test_specs(args.chain_catalog)
       specs = specs + chain_specs
   ```
3. In the strategy block (currently `if args.adaptive: ... else: StaticStrategy()`), add a third branch:
   ```python
   if args.chain:
       from harness.attack.synthesis.chain_strategy import ChainStrategy
       api_key = os.getenv(config.attacker_api_key_env, "").strip()
       strategy = ChainStrategy(
           endpoint=config.attacker_endpoint,
           api_key=api_key,
           model="anthropic/claude-sonnet-4-6",
       )
   elif args.adaptive:
       ...  # existing code
   else:
       strategy = StaticStrategy()
   ```
4. Add to the print header section:
   ```python
   print(f"[deepagent] chain   : {'enabled (' + args.chain_catalog + ')' if args.chain else 'disabled'}")
   ```

### convert_fixture.py
Create `scripts/convert_fixture.py`. Implement the converter as specified in TRD-14 §10.
The script should:
- Use `argparse` with `--input`, `--output`, `--suite-id`
- Read and validate the input JSON
- Map oracle codes through `ORACLE_MAP`
- Write the output file

**Acceptance tests:**
```bash
# CLI help works
/tmp/harness_venv/bin/python scripts/run_deepagent.py --help | grep chain

# Converter dry run
/tmp/harness_venv/bin/python scripts/convert_fixture.py --help

# Script still works without --chain
/tmp/harness_venv/bin/python scripts/run_deepagent.py --no-muzzle --no-analyst \
    --help  # just argparse check, no real target needed
```

**Checkpoint:** commit as `feat: add --chain flag to run_deepagent.py + fixture converter script`

---

## Phase 8 — Integration Tests

**Goal:** Write and pass all integration tests for the chain runner.

**Deliverables:**
- `tests/integration/test_chain_runner.py` (D14 in TRD-14 §13)

**Steps:**
1. Before writing, read `tests/integration/test_mock_victim.py` to understand the mock victim adapter pattern used in existing integration tests.
2. Write `tests/integration/test_chain_runner.py` with the four tests listed in TRD-14 §13.
3. For `test_chain_mode_stops_on_stop_signal` and `test_chain_mode_respects_max_chain_turns`, create a `MockChainStrategy` subclass that returns predetermined responses.
4. For `test_chain_mode_catalog_loads`, use `load_test_specs` directly — no victim needed.

**Acceptance tests:**
```bash
/tmp/harness_venv/bin/pytest tests/integration/test_chain_runner.py -x --tb=short
```

**Checkpoint:** commit as `test: integration tests for chain-mode runner`

---

## Phase 9 — Full Regression

**Goal:** Confirm nothing is broken across the entire test suite.

**Steps:**
```bash
/tmp/harness_venv/bin/pytest tests/ -x --tb=short
```

All tests must pass (green). If anything fails:
1. Do not skip or delete the failing test.
2. Fix the underlying code issue.
3. Re-run until clean.

**Final verification (end-to-end catalog load check):**
```bash
/tmp/harness_venv/bin/python -c "
from harness.attack.catalog.loader import load_test_specs
for p in [
    'harness/attack/library/deepagent/deepagent_direct_v1.json',
    'harness/attack/library/deepagent/deepagent_multiturn_v1.json',
    'harness/attack/library/deepagent/deepagent_toolchain_v1.json',
    'harness/attack/library/deepagent/deepagent_chain_v1.json',
]:
    _, specs = load_test_specs(p)
    chain = sum(1 for s in specs if s.chain_mode)
    print(f'{p.split(\"/\")[-1]:40s}  {len(specs):3d} specs  chain: {chain}')
"
```

Expected:
```
deepagent_direct_v1.json                 ?? specs  chain: 0
deepagent_multiturn_v1.json               6 specs  chain: 0
deepagent_toolchain_v1.json               4 specs  chain: 0
deepagent_chain_v1.json                   8 specs  chain: 8
```

**Checkpoint:** commit as `chore: all regression tests pass for chain attack suite`

---

## Summary: Phase Order and Dependency Graph

```
Phase 0 ─ Explorer timeout fix       (no deps)
    │
Phase 1 ─ Schema + loader            (needs Phase 0 to be clean)
    │
Phase 2 ─ AttackStrategy ABC         (independent, but do after Phase 1)
    │
Phase 3 ─ ChainStrategy              (depends on Phase 2)
    │
Phase 4 ─ Runner chain loop          (depends on Phase 1 + Phase 2 + Phase 3)
    │
Phase 5 ─ Catalog JSON files         (independent, can run parallel with Phase 3)
    │
Phase 6 ─ Grafter chain support      (depends on Phase 1 + Phase 3)
    │
Phase 7 ─ Script updates             (depends on Phase 3 + Phase 5)
    │
Phase 8 ─ Integration tests          (depends on Phase 4 + Phase 5)
    │
Phase 9 ─ Full regression            (depends on all phases)
```

**If running strictly sequentially:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9.

**If you want to parallelize:** Phase 5 (catalog JSON) can be done any time after Phase 1.
Phase 7 (script) can be started after Phase 3. Everything else must wait for its listed dependencies.

---

## Rules for the Implementer

1. **Read TRD-14 before starting each phase.** The section numbers in this document map directly to TRD-14 sections.
2. **Write tests first.** For Phases 3 and 8, the unit/integration tests must be written and confirmed failing before the implementation is written.
3. **Run the acceptance test before committing.** Do not commit a phase with failing tests.
4. **Do not modify files outside the listed deliverables.** If you believe a change is needed outside scope, stop and ask.
5. **If a test was already passing, it must still pass after your change.** Never delete or skip tests to fix failures.
6. **Prefer the smallest change.** Each phase touches only what it needs to.
