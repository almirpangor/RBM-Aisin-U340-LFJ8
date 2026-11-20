"""Упаковать версию проекта и проверенные файлы сборки с манифестом SHA-256."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_SIZES = {"tcm_h03": 524_288, "ecu_e4m3": 851_968}


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


def verify_firmware_pair(produced: list[tuple[dict, bytes]]) -> None:
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
        labels = (item["file"], item["path"], item["status"])
        if any("OFFLINE_ONLY" in label.upper() for label in labels) or content.startswith(b"\x7fELF"):
            raise ValueError(f"Проверочный образ или ELF не подходит для комплекта BIN: {role}")
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
    for item in record["artifacts"]:
        file = record_path.parent / item["file"]
        content = file.read_bytes()
        if sha256(content).hexdigest() != item["sha256"]:
            raise ValueError(f"Файл сборки отличается от проверенного: {file}")
        produced.append((item, content))
    if firmware_pair:
        verify_firmware_pair(produced)

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        manifest = {key: value for key, value in record.items() if key != "artifacts"}
        manifest["source_commit"] = commit
        manifest["files"] = []
        with ZipFile(BytesIO(source_archive)) as source:
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
        help="Проверить наличие BIN ролей tcm_h03 и ecu_e4m3 и статусы их проверок",
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
