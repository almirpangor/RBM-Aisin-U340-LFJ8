"""Build real M32R components on Windows; never emit or qualify a TCM BIN."""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_URL = "https://sysprogs.com/getfile/26/m32r-elf-gcc4.8.0.exe"
PACKAGE_SHA256 = "86889c4995e7666a4986561d682958a1314ad06d0b86ef262388a6097437711d"
PACKAGE_BYTES = 13318935
GCC_SHA256 = "a9025e578a69aa99f3ac3f358a3d63d78f624162dd0c071375b7f9f127a76ae1"
MAGIC = b"XXGNUTOOLCHAINv100\0\0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def member_path(root, name):
    path = PurePosixPath(name.replace("\\", "/"))
    if not path.parts or path.is_absolute() or ":" in name or ".." in path.parts:
        raise ValueError("Unsafe toolchain member: " + name)
    destination = root.joinpath(*path.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Toolchain member leaves extraction directory")
    return destination


def unpack(package, destination, inventory_path):
    """Read the pinned Sysprogs v100 container, without running its installer.

    The LZMA SDK stream in this package omits an end marker. The complete
    package SHA and the exact sum of declared file sizes guard its integrity.
    """
    data = package.read_bytes()
    if len(data) != PACKAGE_BYTES or digest(data) != PACKAGE_SHA256:
        raise ValueError("The toolchain package does not match the pinned official archive")
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[:2] != b"MZ" or data[pe:pe+4] != b"PE\0\0":
        raise ValueError("Expected the original PE installer container")
    section_count = struct.unpack_from("<H", data, pe+6)[0]
    optional_bytes = struct.unpack_from("<H", data, pe+20)[0]
    if not 1 <= section_count <= 96:
        raise ValueError("Invalid PE section count")
    sections = pe + 24 + optional_bytes
    overlay = max(struct.unpack_from("<I", data, sections+i*40+20)[0] +
                  struct.unpack_from("<I", data, sections+i*40+16)[0]
                  for i in range(section_count))
    if data[overlay:overlay+20] != MAGIC or struct.unpack_from("<I", data, overlay+20)[0] != 1:
        raise ValueError("Unsupported Sysprogs archive format")
    count, aliases, names_offset, names_bytes = struct.unpack_from("<4I", data, overlay+24)
    payload_offset, payload_bytes = struct.unpack_from("<II", data, overlay+44)
    if (count, aliases, names_offset, names_bytes, payload_offset, payload_bytes) != (
            1500, 13, 24368, 68964, 93332, 12807299):
        raise ValueError("Unexpected metadata in the pinned toolchain archive")
    if (data[overlay+40:overlay+44] != b"LZMA" or overlay+payload_offset+payload_bytes != len(data)
            or names_offset != 264+count*16+aliases*8 or names_offset+names_bytes != payload_offset):
        raise ValueError("Archive tables or payload exceed the verified container")
    names = data[overlay+names_offset:overlay+names_offset+names_bytes]

    def read_name(index):
        if not 0 <= index < len(names):
            raise ValueError("Invalid archive name offset")
        end = names.find(b"\0", index)
        if end < 0:
            raise ValueError("Unterminated archive member name")
        name = names[index:end].decode("utf-8")
        member_path(destination, name)
        return name

    entries = []
    for index in range(count):
        name_offset, flags, size = struct.unpack_from("<IIQ", data, overlay+264+index*16)
        if flags not in (0, 1) or (flags == 1 and size):
            raise ValueError("Unsupported archive member flags")
        entries.append((read_name(name_offset), flags, size))
    alias_entries = [tuple(read_name(value) for value in struct.unpack_from(
        "<II", data, overlay+264+count*16+index*8)) for index in range(aliases)]
    total_size = sum(entry[2] for entry in entries)
    if total_size != 154109786:
        raise ValueError("Unexpected total uncompressed toolchain size")
    payload = data[overlay+payload_offset:]
    prop = payload[0]
    lc, rest = prop % 9, prop // 9
    lp, pb = rest % 5, rest // 5
    dictionary = struct.unpack_from("<I", payload, 1)[0]
    if (lc, lp, pb, dictionary) != (3, 0, 2, 67108864):
        raise ValueError("Unsupported pinned LZMA properties")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
        "id": lzma.FILTER_LZMA1, "dict_size": dictionary, "lc": lc, "lp": lp, "pb": pb}])
    content = decoder.decompress(payload[5:], max_length=total_size+1)
    if len(content) != total_size or decoder.unused_data:
        raise ValueError("Toolchain payload size mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    inventory = {}
    position = 0
    for name, flags, size in entries:
        path = member_path(destination, name)
        if flags:
            path.mkdir(parents=True, exist_ok=True)
            continue
        chunk = content[position:position+size]
        position += size
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(chunk)
        inventory[name.replace("\\", "/")] = {"bytes": size, "sha256": digest(chunk)}
    for name, source in alias_entries:
        target = member_path(destination, name)
        source_path = member_path(destination, source)
        if not source_path.is_file():
            raise ValueError("Archive alias refers to an unavailable file")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        inventory[name.replace("\\", "/")] = {
            "alias_of": source.replace("\\", "/"), "bytes": target.stat().st_size,
            "sha256": digest(target.read_bytes()),
        }
    compiler = destination / "bin/m32r-elf-gcc.exe"
    if digest(compiler.read_bytes()) != GCC_SHA256:
        raise ValueError("Extracted compiler does not match the verified local original")
    save(inventory_path, inventory)
    return compiler, {"package_sha256": PACKAGE_SHA256, "package_bytes": len(data),
                      "files": count-154, "directories": 154, "aliases": aliases,
                      "uncompressed_file_bytes": total_size, "compiler_sha256": GCC_SHA256,
                      "inventory_sha256": digest(inventory_path.read_bytes()),
                      "installer_executed": False}


def get_package(args, output):
    if args.package is not None:
        return args.package.resolve()
    destination = output / "downloads/m32r-elf-gcc4.8.0.exe"
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(PACKAGE_URL, headers={"User-Agent": "RBM-M32R-CI/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(PACKAGE_BYTES+1)
    if len(data) != PACKAGE_BYTES or digest(data) != PACKAGE_SHA256:
        raise ValueError("Downloaded toolchain package hash/size mismatch")
    destination.write_bytes(data)
    return destination


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_model(args, compiler, model, output, environment):
    destination = output / model
    destination.mkdir(parents=True, exist_ok=True)
    log_path = output / ("logs/"+model+".log")
    result = {"compiler_memory_model": model, "passed": False,
              "artifact_kind": "component_objects_and_cpu_simulation", "commands": [],
              "hardware_verified": False, "flashable_image": None}

    def run(command):
        result["commands"].append([str(value) for value in command])
        process = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                 stderr=subprocess.STDOUT, timeout=1200)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)

    with log_path.open("w", encoding="utf-8") as log:
        try:
            run([sys.executable, "-u", "-B", str(ROOT/"controller/build_target.py"), "m32r",
                 "--cc", str(compiler), "--out", str(destination/"controller"),
                 "--memory-model", model])
            builder = load_module("ci_lfj8_builder", ROOT/"targets/lfj8/build.py")
            if args.base_h03 is not None:
                run([sys.executable, "-u", "-B", str(ROOT/"targets/lfj8/build.py"),
                     "--output", str(destination/"bridge"), "--m32r-cc", str(compiler),
                     "--m32r-memory-model", model, "--base-9e1c", str(args.base_h03.resolve())])
                result["bridge_scope"] = "H03 identity checked by public builder; not a final image"
            else:
                with TemporaryDirectory(prefix="rbm-ci-bridge-") as directory, redirect_stdout(log):
                    obj, metadata = builder.build_embedded(compiler, Path(directory), "m32r", "m2",
                                                           use_9e1c_base=True, memory_model=model)
                    bridge = destination/"bridge"
                    bridge.mkdir(exist_ok=True)
                    builder.publish(obj, bridge)
                    save(bridge/"component-build-manifest.json", {
                        "artifact_kind": "component_object_without_H03_identity",
                        "m32r_base": None, "artifacts": {obj.name: {**builder.summary(obj), **metadata}},
                        "hardware_verified": False, "flashable_image": None,
                    })
                result["bridge_scope"] = "H03 modules compiled; source image identity not checked"
            integrated = load_module("ci_integrated_h03", ROOT/"tools/check_integrated_h03.py")
            sys.path.insert(0, str(ROOT/"targets/lfj8"))
            import check_h03_link as link
            checks = destination/"components"
            checks.mkdir(exist_ok=True)
            component_args = argparse.Namespace(gcc=compiler, controller=destination/"controller/rbm_u340e_m32r_be.o",
                                                out=checks)
            with integrated.link_configuration(link), redirect_stdout(log):
                link.TARGET = [flag.replace("-mmodel=medium", "-mmodel="+model) for flag in link.TARGET]
                component_result = integrated.components(component_args)
            component_result.update(compiler_memory_model=model, hardware_verified=False, flashable_image=None)
            save(checks/"summary.json", component_result)
            if not component_result["passed"]:
                raise ValueError("M32R component CPU checks failed")
            result["passed"] = True
            result["status"] = "PASS_COMPONENTS_ONLY"
        except Exception as error:
            traceback.print_exc(file=log)
            result.update(status="FAILED", error=str(error), error_type=type(error).__name__)
    result["log_sha256"] = digest(log_path.read_bytes())
    result["files"] = {path.relative_to(destination).as_posix(): {"bytes": path.stat().st_size,
                       "sha256": digest(path.read_bytes())} for path in destination.rglob("*")
                       if path.is_file() and path.name != "result.json"}
    save(destination/"result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path, help="Use the pinned archive already present locally")
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--base-h03", type=Path, help="Optional actual H03 input for the public bridge builder")
    args = parser.parse_args()
    output = args.out.resolve()
    (output/"logs").mkdir(parents=True, exist_ok=True)
    report = {"artifact_kind": "M32R_component_build_and_CPU_checks", "status": "RUNNING",
              "toolchain_url": PACKAGE_URL, "models": {}, "hardware_verified": False,
              "bench_pair_ready": False, "flashable_image": None,
              "driver_sha256": digest(Path(__file__).read_bytes())}
    try:
        report["source_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        package = get_package(args, output)
        compiler, toolchain = unpack(package, output/"toolchain", output/"logs/toolchain-inventory.json")
        report["toolchain"] = toolchain
        if args.extract_only:
            report["status"] = "PASS_EXTRACTION_ONLY"
            save(output/"report.json", report)
            print(json.dumps(report, ensure_ascii=False))
            return 0
        environment = dict(os.environ, PATH=str(compiler.parent)+os.pathsep+os.environ.get("PATH", ""),
                           PYTHONIOENCODING="utf-8")
        version = subprocess.check_output([compiler, "--version"], env=environment, text=True, timeout=30)
        report["compiler_version"] = version.splitlines()[0]
        for model in ("medium", "small"):
            report["models"][model] = build_model(args, compiler, model, output, environment)
            save(output/"report.json", report)
        passed = all(result["passed"] for result in report["models"].values())
        report["status"] = "PASS_COMPONENTS_ONLY" if passed else "FAILED"
    except Exception as error:
        report.update(status="FAILED", error=str(error), error_type=type(error).__name__)
        (output/"logs/failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    save(output/"report.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "models"}, ensure_ascii=False))
    return 0 if report["status"] == "PASS_COMPONENTS_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
