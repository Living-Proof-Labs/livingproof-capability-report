<!-- livingproof-verification -->
## walk-hallway@0.1.0 · N=1 · 0.50 m/s · `verification.lock.json @ 5895871`

unitree-g1 · stock does not pass walk-hallway: 0 successes, 0%; overall FAIL. 100% required.

Run Integrity: PASS

**Expected:** The robot starts at the hallway entrance and is commanded to walk straight ahead at 0.5 m/s. It must reach the exit, 5.5 m along the route, within 27 s, staying upright, never touching either wall, and staying within its lateral limit of the centreline.

**Actual · unitree-g1 · stock:** 1 failure, 100%; primary failure: lateral limit exceeded in 1 (trial 1).

| Robot · configuration | Grade | Passed | Needs |
|---|---|---|---|
| unitree-g1 · stock 1.1.1 | **❌ FAIL** | 0 successes, 0% | 100% required |

**Evaluators:** Scenario 1.5.3 · Run Integrity 1.8.6

**Why runs failed · unitree-g1 · stock**
- 1× lateral limit exceeded (primary) — trials 1 — worst 0.5965 m (trial 1)

**Evidence:** [CI run]( · [MCAP, all 1 trials](
- ▶️ trial 1 (fail): [video](

<details><summary>Per-trial failures · unitree-g1 · stock</summary>

**hallway-lateral-limit**

| Trial | Observed (m) | Limit (m) | t (s) |
|---|---|---|---|
| 1 | 0.60 | 0.49 | 10.46 |

**hallway-wall-contact**

| Trial | Contact |
|---|---|
| 1 | touched left wall at 10.54 s |

</details>

<sub>Policy all-required-v1@1.0.0 · catalog <a href="https://github.com/Living-Proof-Labs/robot-capability-specs/commit/57317e617014a6df97bb7fba9d92a890af8d42e5" title="57317e617014a6df97bb7fba9d92a890af8d42e5">v2.3.0</a> · run walk-hallway-unitree-g1-stock-20261126T042453Z · MuJoCo hallway walls are visual only (no collision); from sim-mujoco v1.8.3 a trial ends left_hallway past a wall's outer face · stored decisions, no regrading · simulation evidence, not hardware validation</sub>
<!-- pinned-inputs -->
## Pinned inputs

capability-verifier: resolved (no published commit; tag peeled)
livingproof-sim-mujoco: resolved (no published commit; tag peeled)
robot-capability-specs: resolved (no published commit; tag peeled)
livingproof-worlds: resolved (no published commit; tag peeled)
livingproof-evaluator-scenario: resolved (no published commit; tag peeled)
livingproof-evaluator-run: resolved (no published commit; tag peeled)
livingproof-capability-report: resolved (no published commit; tag peeled)
<!-- /pinned-inputs -->
