from __future__ import annotations

import base64
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path

from manage import APP, command

PACKAGE = "@azure/msal-browser"
VERSION = "4.30.0"
INTEGRITY = "sha512-HBBKfbZkMVzzF5bofvS1cXuNHFVc+gt4/HOnCmG/0hsHuZRJvJvDg/+7nTwIpoqvJc8BQp5o23rBUfisOLxR+w=="


def vendor() -> dict:
    metadata = json.loads(command(["npm", "view", f"{PACKAGE}@{VERSION}", "name", "version", "license", "dist", "--json"]))
    if (metadata["name"], metadata["version"], metadata["license"]) != (PACKAGE, VERSION, "MIT"):
        raise ValueError("Unexpected Microsoft Authentication Library package identity or license.")
    destination = APP / "static/vendor"
    destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="customer-service-msal-") as temporary:
        packed = json.loads(command([
            "npm", "pack", f"{PACKAGE}@{VERSION}", "--ignore-scripts", "--json",
            "--pack-destination", temporary,
        ]))[0]
        archive = Path(temporary) / packed["filename"]
        digest = "sha512-" + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
        if digest != INTEGRITY or hashlib.sha1(archive.read_bytes()).hexdigest() != metadata["dist"]["shasum"]:
            raise ValueError("MSAL archive integrity differs from the pinned reviewed package.")
        with tarfile.open(archive) as package:
            for member, output in {
                "package/lib/msal-browser.min.js": "msal-browser.min.js",
                "package/LICENSE": "MSAL-LICENSE.txt",
            }.items():
                info = package.getmember(member)
                if not info.isfile():
                    raise ValueError("MSAL asset is not a regular archive file.")
                content = package.extractfile(info).read()
                target = destination / output
                if target.is_symlink() or (target.exists() and target.read_bytes() != content):
                    raise ValueError("Refusing to replace a different existing vendored asset.")
                target.write_bytes(content)
    receipt = {
        "package": PACKAGE, "version": VERSION, "license": "MIT",
        "publisher": "Microsoft", "source": metadata["dist"]["tarball"], "integrity": INTEGRITY,
        "files": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                  for name in ("msal-browser.min.js", "MSAL-LICENSE.txt")},
    }
    (destination / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(vendor(), indent=2))
