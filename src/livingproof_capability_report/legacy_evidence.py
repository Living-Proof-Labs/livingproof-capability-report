"""Legacy evidence reader for stored ``livingproof-hallway-*`` bundles.

The check names, short labels and failure sentences in this module are frozen.
They exist so evidence already recorded in that format stays readable.
No writer in this package emits that format.
"""

_CHECKS = (
    {
        "id": "hallway-exit-reached",
        "version": "1.0.0",
        "what": "exit not reached in time",
        "kind": "exit",
        "limits": ("time_limit", "exit_segment"),
    },
    {
        "id": "hallway-lateral-limit",
        "version": "1.0.0",
        "what": "lateral limit exceeded",
        "kind": "lateral",
        "limits": ("lateral_limit",),
    },
    {
        "id": "hallway-wall-contact",
        "version": "1.0.0",
        "what": "touched a wall",
        "kind": "wall",
        "limits": (),
    },
    {
        "id": "hallway-fall",
        "version": "1.0.0",
        "what": "fell",
        "kind": "fall",
        "limits": ("fall_height",),
    },
)
_BY_ID = {item["id"]: item for item in _CHECKS}
_NOTE = (
    "MuJoCo hallway walls are visual only (no collision); from sim-mujoco v1.8.3 a trial "
    "ends left_hallway past a wall's outer face"
)


def _spec(check):
    return _BY_ID.get(check)


def known(check):
    return check in _BY_ID


def order():
    return [item["id"] for item in _CHECKS]


def kind(check):
    spec = _spec(check)
    return spec["kind"] if spec else None


def what(check):
    spec = _spec(check)
    return spec["what"] if spec else None


def limit_keys(check):
    spec = _spec(check)
    return spec["limits"] if spec else ()


def is_contact(check):
    return kind(check) == "wall"


def is_exit(check):
    return kind(check) == "exit"


def is_fall(check):
    return kind(check) == "fall"


def position(check):
    """Frozen check order. A check this reader does not know sorts after those."""
    names = order()
    return names.index(check) if check in _BY_ID else len(names)


def failure_words(failure, fmt, num):
    """Frozen sentence for one stored failure, or None when the check is not this format."""
    check = failure.get("check")
    if not known(check):
        return None
    t = f" at {fmt(failure['t'])} s" if failure.get("t") is not None else ""
    if is_contact(check):
        depth = f" ({fmt(failure['observed'], decimals=3)} m in)" if failure.get("observed") else ""
        side = (failure.get("wall") or "").removeprefix("wall-")
        return f"touched {'the ' + side + ' wall' if side else 'a wall'}{t}{depth}"
    if is_exit(check):
        via = failure.get("via")
        if isinstance(via, str) and via.startswith("wall-"):
            return f"left the hallway through the {via.removeprefix('wall-')} wall{t}"
        if via == "exit-outside-segment":
            return f"crossed the exit line outside the exit segment{t}"
        if failure.get("observed") is None:
            return f"did not reach the exit within {fmt(failure.get('limit'))} s"
        return (
            f"reached the exit at {fmt(failure['observed'], failure.get('limit'))} s > "
            f"{fmt(failure.get('limit'), failure['observed'])} s"
        )
    observed, limit = failure.get("observed"), failure.get("limit")
    if observed is None:
        return f"{check} not measured"
    if kind(check) == "lateral":
        return f"drifted {fmt(observed, limit)} m > {num(limit)} m from the centreline{t}"
    if is_fall(check):
        return f"base dropped to {fmt(observed, limit)} m < {num(limit)} m{t}"
    return None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _legacy_run(report, summary):
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    for rid in summary.get("result_ids") or []:
        result = results.get(rid)
        if not isinstance(result, dict):
            continue
        for item in result.get("assessments") or []:
            if isinstance(item, dict) and known(item.get("evaluator")):
                return True
    for failure in summary.get("failures") or []:
        if isinstance(failure, dict) and known(failure.get("check")):
            return True
    return False


def mujoco_note(report, summary):
    """The stored simulator record, for a bundle this reader understands.

    The world id is not consulted. The note applies when the simulator record
    says MuJoCo and lists the walls it simulated, and the run still uses the
    frozen check names.
    """
    if not _legacy_run(report, summary):
        return None
    results = {r["id"]: r for r in report["source_bundle"]["results"]}
    for rid in summary.get("result_ids") or []:
        simulator = _dict(_dict(results.get(rid, {}).get("provenance")).get("simulator"))
        walls = simulator.get("walls")
        if (
            _dict(simulator.get("simulator")).get("id") == "mujoco"
            and isinstance(walls, list)
            and walls
        ):
            return _NOTE
    return None
