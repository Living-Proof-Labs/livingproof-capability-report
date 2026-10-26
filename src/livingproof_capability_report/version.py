"""Supply this consumer's context to the released shared version library."""
from pathlib import Path

from livingproof_common.versioning import Consumer, current_version as shared_version

PACKAGE = "livingproof-capability-report"
PUBLIC_ORIGINS = (
    "https://github.com/living-proof-labs/livingproof-capability-report",
    "https://github.com/living-proof-labs/livingproof-capability-report.git",
    "git@github.com:living-proof-labs/livingproof-capability-report.git",
)


def current_version(package_dir=None):
    package_dir = Path(package_dir) if package_dir else Path(__file__).resolve().parent
    return shared_version(Consumer(PACKAGE, package_dir, PUBLIC_ORIGINS))
