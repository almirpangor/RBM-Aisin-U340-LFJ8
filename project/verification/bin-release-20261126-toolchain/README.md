# M32R toolchain and native CI

Owner: `d32061c3-c01f-44f5-aa31-d5ed8f982fc2`.
Task: H03-01, continuation for reproducible native component builds.
Claim: `82d76ac93c4045858b318d0452bffff2`.

## Local observations, 26 November 2026

- The x86 Windows command interpreter starts normally.
- The existing SysGCC GCC, assembler and simulator all fail during process
  creation with Windows error 623. These images have the PE relocation-stripped
  flag and no base-relocation directory. The same verified GCC copied to the
  permitted C: workspace also fails with 623. This is an observed environment
  limitation, not a failed compilation of the application sources.
- The native x64 host compiler `C:\msys64\mingw64\bin\gcc.exe` starts.
  MSYS2 bash fails when creating its BaseNamedObjects directory. No Windows
  policy, global PATH, registry entry or original executable was changed.

The pinned official archive is downloaded from
<https://sysprogs.com/getfile/26/m32r-elf-gcc4.8.0.exe>, linked by the
[publisher's M32R page](https://www.gnutoolchains.com/m32r-elf/).

| Input | Verified value |
| --- | --- |
| Package bytes | 13318935 |
| Package SHA-256 | `86889c4995e7666a4986561d682958a1314ad06d0b86ef262388a6097437711d` |
| Extracted GCC SHA-256 | `a9025e578a69aa99f3ac3f358a3d63d78f624162dd0c071375b7f9f127a76ae1` |
| Container | Sysprogs `XXGNUTOOLCHAINv100`, raw LZMA1 |
| Entries | 1346 ordinary files, 154 directories, 13 aliases |
| Uncompressed ordinary-file bytes | 154109786 |

The archive is a custom container. `ci_m32r_build.py` reads its verified tables
and compressed payload directly, validates bounds/member paths and copies
aliases. It does not execute the installer. Before this parser was integrated,
the decoded bytes of all 1346 ordinary files were compared with the original
F: installation: **1346 identical, zero differences**.

The integrated extraction path was then actually executed:

```powershell
python -u -B tools/ci_m32r_build.py --package F:\RBM-Codex-temp\toolchains\m32r-elf-gcc4.8.0.exe --out local/ci-extract --extract-only
```

Result: `PASS_EXTRACTION_ONLY`; the extracted GCC matched its exact expected
SHA. Inventory SHA-256:
`ec6b46d35bc432e63cda1f6644da734d539f538f8bdd9278b2fc1324ef6fcb68`.
The extraction result is **not** a successful native compilation.

## Native CI behavior

The dedicated workflow starts on a push to `codex/m32r-toolchain-20261126` and
uses a standard `windows-2022` runner. It downloads only the pinned archive,
extracts without installation, compiles both `medium` and `small` controller
objects, runs their real M32R CPU simulator tests, compiles the H03 bridge
modules, and runs the additional component CPU checks for each model.

Without `--base-h03`, the bridge artifact is explicitly a
`component_object_without_H03_identity`. It has no invented `m32r_base` and does
not use the filename of a fully qualified H03 build manifest. With an actual
H03 input, `--base-h03 PATH` selects the public bridge builder, which validates
that input against the project registry.

CI uploads the actual report, logs, objects and simulator ELFs even after a
failure. `PASS_COMPONENTS_ONLY` requires actual completed build commands and
CPU checks. `hardware_verified:false`, `bench_pair_ready:false` and
`flashable_image:null` remain explicit. This workflow does not emit a TCM BIN
or claim a working Bosch/TCM pair.

The initial native CI execution has not yet been observed when this report is
committed. Its workflow run, conclusions and artifact IDs must be recorded by
the integrator after publication. A prepared workflow is not a passing build.

## Next use

```powershell
python -u -B tools/ci_m32r_build.py --out local/ci-m32r
# With a real, accessible H03:
python -u -B tools/ci_m32r_build.py --out local/ci-m32r-h03 --base-h03 local/inputs/LFJ8-T-D.bin
```

The M32R Windows toolchain files remain unchanged. No ECU/TCM was programmed.
