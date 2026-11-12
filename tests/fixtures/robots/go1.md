<!-- livingproof-verification -->
## walk-hallway@0.1.0 · N=20 · 0.50 m/s · pass bar 18/20 · `verification.lock.json @ 2fe5d4f`

unitree-go1 · playground does not pass walk-hallway: 15 successes, 75%; overall FAIL. 90% required.

**Expected:** The robot starts at the hallway entrance and is commanded to walk straight ahead at 0.5 m/s. It must reach the exit, 5.5 m along the route, within 27 s, staying upright, never touching either wall, and staying within its lateral limit of the centreline.

**Actual · unitree-go1 · playground:** 5 failures, 25%; primary failure: lateral limit exceeded in 5 (seeds 1, 3, 9, 16, 20).

| Robot · configuration | Grade | Passed | Needs |
|---|---|---|---|
| unitree-go1 · playground 1.0.0 | **❌ FAIL** | 15 successes, 75% | 90% required |

**Why runs failed · unitree-go1 · playground**
- 5× lateral limit exceeded (primary) — seeds 1, 3, 9, 16, 20 — worst 0.7282 m (seed 16)

<details><summary>Per-seed failures · unitree-go1 · playground</summary>

**hallway-exit-reached**

| Seed | Observed (s) | Limit (s) | t (s) |
|---|---|---|---|
| 16 | — | 27.00 | 10.14 |

**hallway-lateral-limit**

| Seed | Observed (m) | Limit (m) | t (s) |
|---|---|---|---|
| 1 | 0.66 | 0.61 | 10.60 |
| 3 | 0.69 | 0.61 | 10.40 |
| 9 | 0.65 | 0.61 | 10.72 |
| 16 | 0.73 | 0.61 | 9.04 |
| 20 | 0.62 | 0.61 | 11.12 |

**hallway-wall-contact**

| Seed | Contact |
|---|---|
| 1 | touched left wall at 10.30 s |
| 3 | touched left wall at 10.10 s |
| 9 | touched left wall at 10.42 s |
| 16 | touched left wall at 8.74 s |
| 20 | touched left wall at 10.84 s |
| 20 | touched left wall at 11.08 s |

</details>

<sub>Policy all-required-v1@1.0.0 · catalog v1.9.0 @ d677bd9 · run walk-hallway-unitree-go1-playground-local-sim-mujoco-v1.8.3 · MuJoCo hallway walls are visual only (no collision); from sim-mujoco v1.8.3 a trial ends left_hallway past a wall's outer face · stored decisions, no regrading · simulation evidence, not hardware validation</sub>
