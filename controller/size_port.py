"""M32R-only size adjustments to already verified, disposable donor copies."""
from pathlib import Path
from hashlib import sha256

from hydraulic_port import replace_once


def apply_m32r_size_port(source_dir: Path) -> dict:
    path = source_dir / "factory_phase_modes.c"
    original = path.read_text(encoding="utf-8")
    adjusted = original
    for signature in ("static FactoryQueuedPhase getq(", "static void putq("):
        adjusted = replace_once(adjusted, signature, "__attribute__((noinline)) " + signature)
    # Preserve bodies, types and tables. Sharing these aggregate accessors
    # avoids M32R GCC 4.8.0 expanding their copies at each call site.
    path.write_text(adjusted, encoding="utf-8", newline="\n")
    return {
        "file": path.name,
        "functions": ["getq", "putq"],
        "change": "noinline attribute only; staged copy, original vendor unchanged",
        "before_lf_sha256": sha256(original.replace("\r\n", "\n").encode()).hexdigest(),
        "after_lf_sha256": sha256(adjusted.replace("\r\n", "\n").encode()).hexdigest(),
    }
