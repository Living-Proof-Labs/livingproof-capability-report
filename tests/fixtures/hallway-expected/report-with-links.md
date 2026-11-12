<!-- livingproof-verification -->
## walk-hallway@0.1.0 · N=20 · 0.50 m/s · pass bar 18/20 · `verification.lock.json @ abcdef1`

unitree-g1 · stock does not pass walk-hallway: 12 successes, 60%; overall FAIL. 90% required.

| Robot · configuration | Grade | Passed | Needs |
|---|---|---|---|
| unitree-g1 · stock 1.1.0 | **❌ FAIL** | 12 successes, 60% | 90% required |

**Why runs failed · unitree-g1 · stock**
- 3× lateral limit exceeded — worst: 0.62 > 0.49 m at 10.26 s (seed 18)
- 3× touched a wall — worst: touched left wall at 4.50 s (seed 12)
- 1× exit not reached in time — worst: not reached by 27.00 s (seed 15)
- 1× other first failures; see the per-seed details

**Evidence:** [CI run](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7) · [evidence](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7/artifacts/1) · [MCAP, all trials](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7/artifacts/2)
- ▶️ seed 4 (fail): [video](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7/artifacts/5)
- ▶️ seed 1 (pass): [video](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7/artifacts/3) · [MCAP](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/actions/runs/7/artifacts/4)

<details><summary>Per-seed failures · unitree-g1 · stock</summary>

**hallway-exit-reached**

| Seed | Observed (s) | Limit (s) | t (s) |
|---|---|---|---|
| 15 | — | 27.00 | 27.00 |

**hallway-lateral-limit**

| Seed | Observed (m) | Limit (m) | t (s) |
|---|---|---|---|
| 4 | 0.62 | 0.49 | 10.26 |
| 7 | 0.62 | 0.49 | 10.26 |
| 9 | 0.62 | 0.49 | 10.26 |
| 18 | 0.62 | 0.49 | 10.26 |

**hallway-wall-contact**

| Seed | Contact |
|---|---|
| 5 | touched left wall at 4.50 s |
| 7 | touched left wall at 4.50 s |
| 12 | touched left wall at 4.50 s |

**hallway-fall**

| Seed | Observed (m) | Limit (m) | t (s) |
|---|---|---|---|
| 14 | 0.41 | 0.50 | 6.20 |

</details>

<sub>Policy all-required-v1@1.0.0 · catalog v1.6.0 @ b4ba31e · run run-1 · stored decisions, no regrading · simulation evidence, not hardware validation</sub>
