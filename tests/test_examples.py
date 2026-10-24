from pathlib import Path

from livingproof_capability_report import grade, load_bundle


def test_released_producer_compatibility_matrix():
    report = grade(load_bundle(Path(__file__).parents[1] / "examples/bundle/manifest.json"))
    actual = {d["result_id"]: d["status"] for d in report["decisions"]}
    assert actual == {
        "v1.1.1-pass": "PASS", "v1.2.0-pass": "PASS",
        "v1.1.1-slow": "PASS", "v1.2.0-slow": "FAIL",
        "v1.1.1-fail": "FAIL", "v1.2.0-fail": "FAIL",
        "v1.1.1-insufficient": "INSUFFICIENT_EVIDENCE",
        "v1.2.0-insufficient": "INSUFFICIENT_EVIDENCE",
    }
    assert len(report["groups"]) == 4
    assert report["source_bundle"]["producer"]["version"] == "1.1.0"
