"""Archive small official FutuRaM definitions with checksum checks."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
import fitz

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(r"F:\AcademicData\topic34\raw\futuram_ump_method_documents_v2_20260930")
OUT = ROOT / "datasets" / "futuram_ump_method_documents_v2_20260930"
NAMES = ("UMPSupportingDoc_BAT_V1.pdf", "UMP_Glossary.xlsx",
         "UMP_ReadMe_AboutFiles.pdf", "Load_CSV_data.pdf")

def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    metadata_path = RAW / "zenodo_21128664_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_bytes())
    else:
        response = requests.get("https://zenodo.org/api/records/21128664", timeout=45)
        response.raise_for_status()
        metadata_path.write_bytes(response.content)
        os.chmod(metadata_path, 0o444)
        metadata = response.json()
    assert metadata["metadata"]["license"]["id"] == "cc-by-4.0"
    registry = {f["key"]: f for f in metadata["files"]}
    manifest = {"record": "10.5281/zenodo.21128664", "version": "V2",
                "publication_date": metadata["metadata"]["publication_date"],
                "license": "CC BY 4.0", "files": []}
    for name in NAMES:
        dest = RAW / name
        item = registry[name]
        if dest.exists():
            content = dest.read_bytes()
        else:
            response = requests.get(item["links"]["self"], timeout=(15, 90))
            response.raise_for_status()
            content = response.content
            dest.write_bytes(content)
            os.chmod(dest, 0o444)
        md5 = hashlib.md5(content).hexdigest()
        assert "md5:"+md5 == item["checksum"], f"Checksum mismatch {name}"
        assert len(content) == item["size"], f"Length mismatch {name}"
        manifest["files"].append({"file": name, "url": item["links"]["self"],
                                  "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                                  "raw_path": str(dest), "bytes": len(content),
                                  "md5": md5, "sha256": hashlib.sha256(content).hexdigest()})
        if name.endswith(".pdf"):
            with fitz.open(dest) as doc:
                text = "\n".join(f"\n--- PAGE {i+1} ---\n"+page.get_text() for i, page in enumerate(doc))
            (OUT / (name[:-4]+".txt")).write_text(text, encoding="utf-8")
        (OUT / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Verified {name}: {len(content)} bytes", flush=True)

if __name__ == "__main__":
    main()
