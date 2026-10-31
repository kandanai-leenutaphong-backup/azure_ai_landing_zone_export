"""Record and verify an explicitly synthetic local artefact without network access."""

from pathlib import Path
from tempfile import TemporaryDirectory

from webres import Catalogue, Provenance, now_iso, sha256_bytes


def main() -> None:
    with TemporaryDirectory(prefix="web-resource-example-") as directory:
        root = Path(directory)
        payload = b"Synthetic local reference. No web acquisition.\n"
        artefact = root / "reference.txt"
        artefact.write_bytes(payload)
        catalogue = Catalogue(root / "manifest.json")
        catalogue.record(Provenance(
            source_url="", retrieved_at=now_iso(), status=0, content_type="text/plain",
            sha256=sha256_bytes(payload), bytes=len(payload), subject="offline-example",
            function="local-fixture", artefact=catalogue.key_for(artefact),
            notes="Synthetic fixture; no publisher or remote retrieval claimed.",
        ))
        catalogue.save()
        loaded = Catalogue(root / "manifest.json")
        assert loaded.entries["reference.txt"]["sha256"] == sha256_bytes(artefact.read_bytes())
        print("PASS: synthetic catalogue persisted and read back; network unused")


if __name__ == "__main__":
    main()