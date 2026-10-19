"""Install only the checksum-verified, publicly published v0.1.0 hook."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

NAME = "kea-cb-commands-0.1.0-linux-ubuntu-24.04-x86_64-kea-3.2.1"
SHA256 = "4287269544a64fba46ccff98e794c265a7116a64f0bf64f7a918d828f6428402"
COMMIT = "b5a1b8b10e3c45d050527f2727a5959abf470117"
BASE = "https://github.com/rannday/kea-cb-commands/releases/download/v0.1.0/"
DEST = Path("/opt/release")


def download(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main():
    DEST.mkdir()
    release = json.loads(download(
        "https://api.github.com/repos/rannday/kea-cb-commands/releases/tags/v0.1.0"))
    assert release["tag_name"] == "v0.1.0" and not release["draft"]
    api = "https://api.github.com/repos/rannday/kea-cb-commands/git/"
    ref = json.loads(download(api + "ref/tags/v0.1.0"))["object"]
    assert ref["type"] == "tag", "Expected the approved annotated tag"
    tagged = json.loads(download(api + "tags/" + ref["sha"]))["object"]
    assert tagged == {"type": "commit", "sha": COMMIT,
                      "url": api + "commits/" + COMMIT}
    names = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    for suffix in (".tar.gz", ".tar.gz.sha256"):
        assert names[NAME + suffix] == BASE + NAME + suffix
        (DEST / (NAME + suffix)).write_bytes(download(names[NAME + suffix]))
    published = (DEST / (NAME + ".tar.gz.sha256")).read_text().split()
    assert published == [SHA256, NAME + ".tar.gz"]
    archive = DEST / (NAME + ".tar.gz")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == SHA256
    subprocess.run(["sha256sum", "--check", NAME + ".tar.gz.sha256"], cwd=DEST, check=True)
    expected = {"INSTALL.md", "LICENSE", "RELEASE-NOTES.md", "manifest.json",
                "lib/kea/hooks/libdhcp_db_commands.so"}
    with tarfile.open(archive) as source:
        members = source.getmembers()
        assert {member.name for member in members} == {NAME + "/" + p for p in expected}
        assert all(member.isfile() for member in members)
        for member in members:
            target = DEST / member.name.removeprefix(NAME + "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            incoming = source.extractfile(member)
            if incoming is None:
                raise ValueError(f"Archive member has no file content: {member.name}")
            with incoming, target.open("wb") as output:
                shutil.copyfileobj(incoming, output)
    manifest = json.loads((DEST / "manifest.json").read_text())
    print(json.dumps(manifest, indent=2), flush=True)
    library = DEST / "lib/kea/hooks/libdhcp_db_commands.so"
    target = Path("/opt/kea/install/lib/kea/hooks/libdhcp_db_commands.so")
    shutil.copyfile(library, target)
    target.chmod(0o755)
    (DEST / "provenance.json").write_text(json.dumps({
        "release": release["html_url"], "tag": "v0.1.0", "verified_commit": COMMIT,
        "archive": BASE + NAME + ".tar.gz", "sha256": SHA256,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
