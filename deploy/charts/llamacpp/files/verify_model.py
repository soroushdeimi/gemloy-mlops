"""Check the existing mounted weight file without modifying it."""

import sys
from pathlib import Path


def verify_model(path: Path, expected_size: int):
    if not path.is_file():
        raise ValueError(f"Model file missing or not a regular file: {path}")
    actual = path.stat().st_size
    if actual != expected_size:
        raise ValueError(
            f"Model size mismatch: expected {expected_size} bytes, found {actual}: {path}"
        )


if __name__ == "__main__":
    try:
        verify_model(Path(sys.argv[1]), int(sys.argv[2]))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    print("Existing model file and byte size verified", flush=True)
