"""Verify the exact handoff, then publish its Git tree and release attachments."""
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
import json
import os
import subprocess
import zipfile

repo = Path.cwd()
output = Path(os.environ["RUNNER_TEMP"]) / "rbm-u340e-assets"
output.mkdir()
archive = output / "RBM_U340E_H03_E4M3_OFFLINE_ONLY.zip"
expected_digest = "c11433e314545be7e00f7b17d4568ed1fdead929a281736481aa2b3ab6804b25"
parts = sorted((repo / "transfer").glob(archive.name + ".*"))
if [p.suffix for p in parts] != [f".{i:03d}" for i in range(1, 41)]:
    raise ValueError("Incomplete archive transfer")
with archive.open("xb") as out:
    for part in parts:
        out.write(part.read_bytes())
if archive.stat().st_size != 61488013 or sha256(archive.read_bytes()).hexdigest() != expected_digest:
    raise ValueError("The published archive differs from the verified local handoff")

env = dict(os.environ, GIT_INDEX_FILE=str(output / "handoff.index"),
           GIT_AUTHOR_NAME="RB Motors", GIT_COMMITTER_NAME="RB Motors",
           GIT_AUTHOR_EMAIL="75029237+almirpangor@users.noreply.github.com",
           GIT_COMMITTER_EMAIL="75029237+almirpangor@users.noreply.github.com")
def git(args, data=None):
    return subprocess.check_output(["git", *args], input=data, env=env).decode().strip()

entries = []
def add(path, data):
    sha = git(["hash-object", "-w", "--stdin"], data)
    if sha != sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest():
        raise ValueError(path)
    entries.append(f"100644 blob {sha}\t{path}".encode() + b"\0")

with zipfile.ZipFile(archive) as z:
    names = z.namelist()
    checks = {}
    for line in z.read("SHA256SUMS.txt").decode("utf-8").splitlines():
        digest, path = line.split("  ", 1)
        if path in checks:
            raise ValueError(path)
        checks[path] = digest
    if len(names) != 2644 or len(names) != len(set(names)) or set(names) != set(checks) | {"SHA256SUMS.txt"}:
        raise ValueError("File manifest differs from archive")
    for path in names:
        if PurePosixPath(path).is_absolute() or {".git", ".."} & set(PurePosixPath(path).parts):
            raise ValueError(path)
        data = z.read(path)
        if path != "SHA256SUMS.txt" and sha256(data).hexdigest() != checks[path]:
            raise ValueError(path)
        add(path, data)
    manifest = json.loads(z.read("release.json"))
    if manifest["bench_pair_ready"] or manifest["status"] != "OFFLINE_ONLY" or len(manifest["bin_files"]) != 2:
        raise ValueError("Unexpected release scope")
    sums = [f"{expected_digest}  {archive.name}"]
    for item in manifest["bin_files"]:
        data = z.read(item["path"])
        if sha256(data).hexdigest() != item["sha256"] or len(data) != item["bytes"]:
            raise ValueError(item["path"])
        name = PurePosixPath(item["path"]).name
        (output / name).write_bytes(data)
        sums.append(f"{item['sha256']}  {name}")
    (output / "release.json").write_bytes(z.read("release.json"))
    (output / "SPEC_AUDIT_RU.txt").write_bytes(z.read("СВЕРКА_ТЗ.txt"))
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
add("README.md", (repo / "publish/HANDOFF.md").read_bytes())
git(["update-index", "-z", "--index-info"], b"".join(entries))
tree = git(["write-tree"])
parent = "70b6d601fd5dda4e7d7b94d9ba2a65864c132e1a"
branch = "delivery/u340e-20261126-offline"
ref = "refs/heads/" + branch
head = git(["ls-remote", "--heads", "origin", ref])
if head:
    commit = head.split()[0]
    git(["fetch", "--no-tags", "origin", ref])
    if git(["rev-parse", "FETCH_HEAD^{tree}"]) != tree:
        raise ValueError("The release branch already has different content")
else:
    commit = git(["commit-tree", tree, "-p", parent, "-m",
                  "Publish the verified U340E H03 and Bosch E4M3 offline handoff"])
    git(["push", "origin", commit + ":" + ref])
print("Verified 2644 files, both firmware images and archive", expected_digest, "at commit", commit, flush=True)
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
    out.write(f"commit={commit}\nassets={output}\n")
