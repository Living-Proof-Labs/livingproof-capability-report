"""Record this consumer's build using the pinned common library."""
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from livingproof_common.versioning import Consumer, record_build


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        consumer = Consumer("livingproof-capability-report", root / "src/livingproof_capability_report", (
            "https://github.com/living-proof-labs/livingproof-capability-report",
            "https://github.com/living-proof-labs/livingproof-capability-report.git",
            "git@github.com:living-proof-labs/livingproof-capability-report.git",
        ))
        build_data.setdefault("artifacts", []).append(
            record_build(root, self.metadata.version, consumer))
