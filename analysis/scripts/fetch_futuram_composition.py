"""Acquire a versioned, openly licensed small FutuRaM composition workbook."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

RAW = Path(r"F:\AcademicData\topic34\raw\futuram_composition_zenodo21259059_v4_20260930")
OUT = Path(__file__).resolve().parents[1] / "datasets" / "futuram_composition_v4_20260930"
NAME = "Raw_Dataset_Composition_Batteries_V4.xlsx"
EXPECTED_MD5 = "39ac39d38b56db88e44b79a4792a1d07"

def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = RAW / NAME
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite raw data {dest}")
    url = f"https://zenodo.org/records/21259059/files/{NAME}?download=1"
    response = requests.get(url, timeout=(15, 120))
    response.raise_for_status()
    dest.write_bytes(response.content)
    os.chmod(dest, 0o444)
    md5 = hashlib.md5(response.content).hexdigest()
    manifest = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "url": url, "doi": "10.5281/zenodo.21259059", "version": "v4",
                "published": "2026-07-08", "license": "CC BY 4.0",
                "license_source": "https://zenodo.org/records/21259059",
                "raw_path": str(dest), "bytes": len(response.content),
                "md5": md5, "repository_md5": EXPECTED_MD5,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "checksum_verified": md5 == EXPECTED_MD5}
    (OUT / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    assert md5 == EXPECTED_MD5, "Repository MD5 mismatch"

if __name__ == "__main__":
    main()
