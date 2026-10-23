"""Capture public FutuRaM UMP BEV waste-generation responses without overwrites.

These are modelled end-of-life lithium-rechargeable product masses in BEV
applications (t/year). The platform's separate 'Battery pack' product is
excluded. They are not collection, black mass, chemistry shares or throughput.
Raw HTTP response bytes are preserved read-only on F. Derived tables and
request/provenance records are written on D. The API snapshot is dated and
is not asserted byte-identical to the separately archived Zenodo V2 model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://www.urbanmineplatform.eu/api"
EU27 = ("AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN",
        "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX",
        "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE")
BEV = tuple(f"BATTinELV_BEV_{size}kWh" for size in (25, 45, 60, 80, 100))
PRODUCT = "Lithium based batteries, rechargeable"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture(session: requests.Session, method: str, url: str,
            body: dict | None, path: Path) -> dict:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite raw material: {path}")
    started = now()
    response = session.request(method, url, json=body, timeout=(15, 60))
    path.write_bytes(response.content)
    os.chmod(path, 0o444)
    record = {"retrieved_at_utc": started, "url": url, "method": method,
              "request_json": body, "http_status": response.status_code,
              "content_type": response.headers.get("Content-Type"),
              "etag": response.headers.get("ETag"),
              "last_modified": response.headers.get("Last-Modified"),
              "raw_path": str(path), "bytes": len(response.content),
              "sha256": hashlib.sha256(response.content).hexdigest()}
    response.raise_for_status()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="20260930_v1")
    parser.add_argument("--scenario", default="BAU")
    args = parser.parse_args()
    raw = Path(r"F:\AcademicData\topic34\raw") / f"ump_bev_flows_{args.tag}"
    out = ROOT / "datasets" / f"ump_bev_flows_{args.tag}"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Academic-public-data-audit/1.0",
                            "Accept": "application/json"})
    manifest = {"created_utc": now(), "python": platform.python_version(),
                "raw_directory": str(raw), "output_directory": str(out),
                "data_kind": "modelled lithium-rechargeable product waste in BEV applications",
                "unit": "t/year (website chart label)",
                "spatial_scope": "EU-27 (explicit country ISO3 list)",
                "application_filter": list(BEV),
                "chemistry_scope": "lithium-based rechargeable family; no NMC/LFP split",
                "scenario": args.scenario,
                "source": "https://www.urbanmineplatform.eu/waste-stream/batteries/charts",
                "related_dataset_doi": "10.5281/zenodo.21128664",
                "related_dataset_version": "V2 (2026-07-02)",
                "api_zenodo_identity": "not verified; live service snapshot used explicitly",
                "related_dataset_license": "CC BY 4.0; API terms to be checked before redistribution",
                "requests": [], "errors": []}
    manifest_path = out / "request_manifest.json"

    def checkpoint() -> None:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for key, endpoint in (("countries", "lexique/getCountry"),
                          ("applications", "lexique/getSubCategories?wasteStream=BATTERIES")):
        try:
            record = capture(session, "GET", f"{API}/{endpoint}", None,
                             raw / f"metadata_{key}.json")
            manifest["requests"].append(record)
        except Exception as exc:
            manifest["errors"].append({"key": key, "error": repr(exc)})
        checkpoint()

    rows = []
    groups = [(code, [code]) for code in EU27] + [("EU27_check", list(EU27))]
    for index, (code, countries) in enumerate(groups, start=1):
        body = {"idScenario": args.scenario, "idLocations": countries,
                "idSubCategorys": list(BEV), "idProducts": ["battLiRechargeable"],
                "idComponents": [], "idMaterials": [], "idElements": [],
                "isOrdered": False}
        path = raw / f"{args.scenario}_BEV_{code}.json"
        try:
            record = capture(session, "POST", f"{API}/batteries/stacked-column/BATTERIES_GENERATED",
                             body, path)
            manifest["requests"].append(record)
            data = json.loads(path.read_bytes())
            if not isinstance(data, list) or not data:
                raise ValueError(f"Expected nonempty annual records, received {type(data)}")
            for item in data:
                value = float(item[PRODUCT])
                year = int(item["year"])
                if not 2010 <= year <= 2050 or value < 0:
                    raise ValueError(f"Invalid year or negative mass: {item}")
                rows.append({"country_iso3": code, "year": year,
                             "scenario": args.scenario, "bev_lithium_battery_waste_t": value,
                             "raw_sha256": record["sha256"]})
            print(f"{index}/{len(groups)} {args.scenario} {code}: {len(data)} years", flush=True)
        except Exception as exc:
            manifest["errors"].append({"key": code, "error": repr(exc)})
            print(f"ERROR {code}: {exc}", flush=True)
        checkpoint()
        time.sleep(0.6)

    frame = pd.DataFrame(rows)
    frame.to_csv(out / "eu27_bev_lithium_battery_waste_all_reported_years.csv", index=False)
    if len(frame):
        country = frame.loc[frame.country_iso3.isin(EU27)]
        totals = country.groupby("year")["bev_lithium_battery_waste_t"].sum()
        aggregate = frame.loc[frame.country_iso3.eq("EU27_check")].set_index("year")["bev_lithium_battery_waste_t"]
        audit = pd.DataFrame({"country_sum_t": totals, "api_aggregate_t": aggregate})
        audit["absolute_difference_t"] = (audit.country_sum_t - audit.api_aggregate_t).abs()
        audit.to_csv(out / "country_sum_audit.csv")
        manifest["country_count_acquired"] = int(country.country_iso3.nunique())
        manifest["aggregate_max_abs_difference_t"] = float(audit.absolute_difference_t.max())
        complete_years = country.groupby("year").country_iso3.nunique()
        manifest["complete_eu27_years"] = complete_years.loc[complete_years.eq(27)].index.tolist()
        manifest["complete"] = (country.country_iso3.nunique() == 27 and
                                  all(complete_years.get(y, 0) == 27 for y in range(2025, 2051)) and len(aggregate) == 41 and
                                  not manifest["errors"] and
                                  audit.absolute_difference_t.max() < 1e-6)
        print(audit.loc[[2025, 2030, 2035, 2040, 2050]].to_string(), flush=True)
    checkpoint()
    if not manifest.get("complete", False):
        raise SystemExit("Capture incomplete or aggregate audit failed; inspect manifest")


if __name__ == "__main__":
    main()
