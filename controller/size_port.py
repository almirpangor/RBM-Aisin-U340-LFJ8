"""M32R-only size adjustments to already verified, disposable donor copies."""
from pathlib import Path
from hashlib import sha256

from hydraulic_port import replace_once


def apply_m32r_size_port(source_dir: Path) -> dict:
    records = []
    for filename, signatures in (
        ("factory_phase_modes.c", ("static FactoryQueuedPhase getq(", "static void putq(")),
        ("factory_learning.c", ("static void inc(", "static int down_observer(")),
    ):
        records.append(adjust_file(source_dir / filename, signatures))
    return {"adjustments": records}


def adjust_file(path: Path, signatures: tuple[str, ...]) -> dict:
    original = path.read_text(encoding="utf-8")
    adjusted = original
    for signature in signatures:
        adjusted = replace_once(adjusted, signature, "__attribute__((noinline)) " + signature)
    # Preserve bodies, types and tables. Explicit call boundaries reduce
    # duplication and register pressure in M32R GCC 4.8.0 output.
    path.write_text(adjusted, encoding="utf-8", newline="\n")
    return {
        "file": path.name,
        "functions": [signature.split()[-1][:-1] for signature in signatures],
        "change": "noinline attribute only; staged copy, original vendor unchanged",
        "before_lf_sha256": sha256(original.replace("\r\n", "\n").encode()).hexdigest(),
        "after_lf_sha256": sha256(adjusted.replace("\r\n", "\n").encode()).hexdigest(),
    }
