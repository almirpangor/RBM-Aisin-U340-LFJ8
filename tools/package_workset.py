"""Упаковать версию проекта и проверенные файлы сборки с манифестом SHA-256."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

if __package__:
    from .inspect_lfj8_tcm import H03_PART_NUMBER, IMAGE_SIZE, inspect
else:
    from inspect_lfj8_tcm import H03_PART_NUMBER, IMAGE_SIZE, inspect


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_SIZES = {"tcm_h03": IMAGE_SIZE, "ecu_e4m3": 851_968}
H03_BOOT_MARKERS = {0x008000: b"\x5a\xa5", 0x07FFFE: b"\xa5\x5a"}
# This platform identifier is present in the pinned S04 and the derived Bosch builds.
BOSCH_ID_OFFSET = 0x0A844A
BOSCH_ID = b"ME7.9.71/720/4415EN.2/"


def git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def archive_path(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
        raise ValueError(f"Некорректный путь в архиве: {name!r}")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError(f"Некорректный путь в архиве: {name!r}")
    return normalized


def write_file(archive: ZipFile, name: str, content: bytes) -> dict:
    name = archive_path(name)
    if name in archive.namelist():
        raise ValueError(f"Повторяющийся путь: {name}")
    entry = ZipInfo(name)
    entry.compress_type = ZIP_DEFLATED
    archive.writestr(entry, content)
    return {"path": name, "bytes": len(content), "sha256": sha256(content).hexdigest()}


def offline_report_hashes(report: object) -> set[str]:
    hashes = set()
    if not isinstance(report, dict):
        return hashes
    for entry in (report, report.get("bosch_candidate_frame_probe")):
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if not isinstance(status, str) or "OFFLINE_ONLY" not in status.upper():
            continue
        # These fields identify a firmware image, unlike source or base digests.
        for field in ("sha256", "bosch_sha256", "image_sha256"):
            digest = entry.get(field)
            if isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                hashes.add(digest.lower())
    return hashes


def offline_firmware_hashes(source: ZipFile) -> set[str]:
    hashes = set()
    for name in source.namelist():
        suffix = PurePosixPath(name).suffix.lower()
        if suffix == ".bin" and "OFFLINE_ONLY" in name.upper():
            hashes.add(sha256(source.read(name)).hexdigest())
        elif name.startswith("verification/") and suffix == ".json":
            hashes.update(offline_report_hashes(json.loads(source.read(name))))
    return hashes


def reference_firmware_hashes(source: ZipFile) -> dict[str, str]:
    # Read the records at source_commit, using the same snapshot as the archived code.
    registry = json.loads(source.read("data/sources.json"))
    audit = json.loads(source.read("data/e4m3-diff.json"))
    hashes = {entry["sha256"]: name for name, entry in audit["files"].items()}
    hashes.update((entry["sha256"], entry["id"])
                  for entry in (*registry["firmware"], *registry["supporting_materials"]))
    return hashes


def verify_firmware_pair(produced: list[tuple[dict, bytes]], offline_hashes: set[str],
                         reference_hashes: dict[str, str]) -> None:
    firmware = [(item, content) for item, content in produced
                if PurePosixPath(item["path"]).suffix.lower() == ".bin"
                or item["role"] in FIRMWARE_SIZES]
    if len(firmware) != len(FIRMWARE_SIZES) or {item["role"] for item, _ in firmware} != FIRMWARE_SIZES.keys():
        raise ValueError("Требуется по одному BIN для tcm_h03 и ecu_e4m3")
    for item, content in firmware:
        role = item["role"]
        if (PurePosixPath(item["path"]).suffix.lower() != ".bin"
                or len(content) != FIRMWARE_SIZES[role]):
            raise ValueError(f"Неверное расширение или размер BIN для {role}")
        status = item.get("status")
        if not isinstance(status, str):
            raise ValueError(f"Не указан статус выпуска для образа {role}")
        status = status.upper()
        if ("UNQUALIFIED" in status or "ADDRESS_MODEL_ONLY" in status
                or ((role == "tcm_h03" or "bench_pair_ready" in item)
                    and item.get("bench_pair_ready") is not True)):
            raise ValueError(f"Образ {role} не прошёл выпускную программную квалификацию")
        labels = (item["file"], item["path"], item["status"])
        if any("OFFLINE_ONLY" in label.upper() for label in labels) or content.startswith(b"\x7fELF"):
            raise ValueError(f"Проверочный образ или ELF не подходит для комплекта BIN: {role}")
        if item["sha256"] in offline_hashes:
            raise ValueError(f"Образ {role} совпадает по SHA-256 с проверочным OFFLINE_ONLY")
        reference = reference_hashes.get(item["sha256"])
        if reference is not None:
            raise ValueError(f"Образ {role} совпадает по SHA-256 с исходником {reference}")
        if role == "tcm_h03":
            if not inspect(content, H03_PART_NUMBER)["matches_expected_id"]:
                raise ValueError(f"В образе {role} отсутствует штатный идентификатор {H03_PART_NUMBER}")
            for offset, marker in H03_BOOT_MARKERS.items():
                if not content.startswith(marker, offset):
                    raise ValueError(f"Неверный маркер запуска H03 по адресу 0x{offset:06X}")
        elif not content.startswith(BOSCH_ID, BOSCH_ID_OFFSET):
            raise ValueError(f"В образе {role} отсутствует идентификатор {BOSCH_ID.decode('ascii')}")
        if (item.get("build_verified") is not True or item.get("model_verified") is not True
                or type(item.get("hardware_verified")) is not bool):
            raise ValueError(f"Требуются подтверждения сборки и модели и отдельный статус стенда: {role}")


def create_workset(record_path: Path, output: Path, *, firmware_pair: bool = False) -> str:
    record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    commit = git("rev-parse", "--verify", f"{record['source_commit']}^{{commit}}").decode().strip()
    if commit != record["source_commit"]:
        raise ValueError("В записи сборки требуется полный SHA коммита")
    source_archive = git("archive", "--format=zip", commit)
    produced = []
    build_manifests = set()
    for item in record["artifacts"]:
        file = record_path.parent / item["file"]
        content = file.read_bytes()
        if sha256(content).hexdigest() != item["sha256"]:
            raise ValueError(f"Файл сборки отличается от проверенного: {file}")
        produced.append((item, content))
        if firmware_pair and item["role"] in FIRMWARE_SIZES:
            build_manifests.add(file.with_name("manifest.json"))
    buffer = BytesIO()
    with ZipFile(BytesIO(source_archive)) as source, ZipFile(buffer, "w") as archive:
        if firmware_pair:
            offline_hashes = offline_firmware_hashes(source)
            for build_manifest in sorted(build_manifests):
                if build_manifest.is_file():
                    offline_hashes.update(offline_report_hashes(json.loads(build_manifest.read_bytes())))
            verify_firmware_pair(produced, offline_hashes, reference_firmware_hashes(source))
        manifest = {key: value for key, value in record.items() if key != "artifacts"}
        manifest["source_commit"] = commit
        manifest["files"] = []
        for name in sorted(source.namelist()):
            if name.endswith("/"):
                continue
            item = write_file(archive, f"source/{name}", source.read(name))
            manifest["files"].append(item)
        for item, content in produced:
            entry = write_file(archive, item["path"], content)
            entry.update(role=item["role"], status=item["status"])
            if firmware_pair and item["role"] in FIRMWARE_SIZES:
                for field in ("build_verified", "model_verified", "hardware_verified"):
                    entry[field] = item[field]
            manifest["files"].append(entry)
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        write_file(archive, "MANIFEST.json", manifest_bytes)

    with ZipFile(buffer) as archive:
        for item in manifest["files"]:
            data = archive.read(item["path"])
            if len(data) != item["bytes"] or sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Проверка записи архива не прошла: {item['path']}")
    content = buffer.getvalue()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(content)
    return sha256(content).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="JSON с идентификацией проверенной сборки")
    parser.add_argument("output", type=Path, help="Путь к новому ZIP")
    parser.add_argument(
        "--firmware-pair", action="store_true",
        help="Проверить два целевых BIN, их идентификаторы и статусы проверок",
    )
    arguments = parser.parse_args()
    try:
        digest = create_workset(arguments.record.resolve(), arguments.output.resolve(),
                                firmware_pair=arguments.firmware_pair)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Сборка комплекта остановлена: {error}\n")
    print(f"{arguments.output} SHA-256 {digest}")


if __name__ == "__main__":
    main()
