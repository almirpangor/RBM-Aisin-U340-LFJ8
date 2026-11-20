"""Exercise the H03 foreground wait candidate against the stock flag clear."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
WAIT = 0x8150
CLEAR = 0x815C
CONTINUE = 0x8160
STOCK_WAIT = bytes.fromhex("E4804ADE2094F000B080FFFE60002004")
FIXTURE = r"""
    .section .entry,"ax"
    .global _start
_start:
    ld24 sp,#0x9ffffc
    ld24 lr,#0x123400
    ld24 r1,#0x654321
    ld24 r2,#0x789abc
    mvtaclo r2
    ldi r2,#0x40+CARRY
    mvtc r2,psw
#if READY
    ld24 r4,#0x804ade
    ldi r0,#1
    stb r0,@r4
#endif
    bra phase_wait_site

    .section .wait,"ax"
phase_wait_site:
    bra.l rbm_h03_phase_wait_hook

    .section .clear,"ax"
    .global h03_stock_phase_clear
h03_stock_phase_clear:
    .incbin "clear.dat"
    bra check_return

    .text
    .global rbm_h03_phase_wait_callback
rbm_h03_phase_wait_callback:
    ld24 r0,#0x804ade
    ldub r1,@r0
    ld24 r2,#calls
    ld r3,@r2
    addi r3,#1
    st r3,@r2
#if !READY
    bnez r1,fail
    ldi r1,#3
    bne r3,r1,callback_return
    ldi r1,#1
    stb r1,@r0
#endif
callback_return:
    ldi r0,#0
    mvtaclo r0
    mvtachi r0
    ldi r1,#1
#if CARRY
    cmpu r0,r1
#else
    cmpu r1,r0
#endif
    jmp lr

check_return:
    mvfc r3,psw
    and3 r3,r3,#1
    ldi r2,#CARRY
    bne r3,r2,fail
    bnez r0,fail
    ld24 r2,#0x654321
    bne r1,r2,fail
    ld24 r2,#0x804ade
    bne r4,r2,fail
    ldub r2,@r4
    bnez r2,fail
    ld24 r2,#0x123400
    bne lr,r2,fail
    ld24 r2,#0x9ffffc
    bne sp,r2,fail
    mvfaclo r3
    ld24 r2,#0x789abc
    bne r3,r2,fail
    ld24 r2,#calls
    ld r3,@r2
    ldi r2,#(3-2*READY)
    bne r3,r2,fail
    ldi r1,#0
    bra finish
fail:
    ldi r1,#1
finish:
    ldi r0,#1
    trap #0

    .data
    .p2align 2
calls:
    .long 0
"""
LAYOUT = """ENTRY(_start)
SECTIONS {
  .entry 0x1000 : { *(.entry) }
  .wait 0x8150 : { *(.wait) }
  .clear 0x815c : { *(.clear) }
  .text 0x60000 : { *(.text) }
  .data 0x100000 : { *(.data) }
}
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the wait fixture")
    wait_code = rom[WAIT:CONTINUE]
    if wait_code != STOCK_WAIT:
        raise ValueError("Unexpected instructions at the H03 foreground wait")
    with TemporaryDirectory(prefix="rbm-h03-wait-") as directory:
        work = Path(directory)
        shutil.copyfile(HERE / "h03_phase_wait_hook.S", work / "hook.S")
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "clear.dat").write_bytes(wait_code[CLEAR - WAIT:])
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        results = []
        for ready in (0, 1):
            for carry in (0, 1):
                subprocess.run(
                    [compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld",
                     f"-DREADY={ready}", f"-DCARRY={carry}", "fixture.S", "hook.S", "-o", "fixture.elf"],
                    cwd=work, check=True, capture_output=True, timeout=15,
                )
                subprocess.run([simulator, "--memory-size", "16M", "fixture.elf"],
                               cwd=work, check=True, capture_output=True, timeout=15)
                results.append({"initial_ready": bool(ready), "initial_carry": carry,
                                "callback_calls": 1 if ready else 3, "stock_flag_cleared": True})
    return {"base": identity, "wait": f"0x{WAIT:06X}", "stock_clear": f"0x{CLEAR:06X}",
            "native_continuation": f"0x{CONTINUE:06X}", "cases": results,
            "scope": "Mock callback and RAM flag. Original clear instruction executed.",
            "hardware_executed": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve())
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
