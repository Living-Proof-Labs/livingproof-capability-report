"""Fetch exact reviewed common-library release artifacts for packaging only."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

BASE = "https://github.com/Living-Proof-Labs/livingproof-common/releases/download/v1.0.0/"
FILES = {
    "livingproof_common-1.0.0-py3-none-any.whl":
        "8b7795748b54eeb89610f3716245f45db48ac0474465a5abbf974e7075c1476c",
    "python3-livingproof-common_1.0.0_all.deb":
        "2c8902d5a2353917f47f851395dd2cfaf5f4314697ba052acdf8bc56d6fcf0c2",
}


def fetch(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, expected in FILES.items():
        target = destination / filename
        content = target.read_bytes() if target.exists() else urlopen(
            BASE + filename, timeout=60).read()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Common library release checksum mismatch: " + filename)
        target.write_bytes(content)


if __name__ == "__main__":
    fetch(Path(__file__).resolve().parents[1] / "dist")
