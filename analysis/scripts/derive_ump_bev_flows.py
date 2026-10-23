"""Reanalyse intact archived API responses; never impute absent early years.

The first capture parser expected 41 years from every country. UMP actually
returns different historical start dates. This derivation preserves all
reported records and restricts the EU27 network supply to years with all 27
countries explicitly reported. Missing records are not silently zero-filled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fetch_ump_bev_flows import EU27, PRODUCT, ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="20260930_v1")
    parser.add_argument("--scenario", default="BAU")
    args = parser.parse_args()
    raw = Path(r"F:\AcademicData\topic34\raw") / f"ump_bev_flows_{args.tag}"
    out = ROOT / "datasets" / f"ump_bev_flows_{args.tag}"
    manifest = json.loads((out / "request_manifest.json").read_text(encoding="utf-8"))
    records = {Path(r["raw_path"]).name: r for r in manifest["requests"]}
    rows, inventory = [], []
    for code in (*EU27, "EU27_check"):
        name = f"{args.scenario}_BEV_{code}.json"
        path = raw / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == records[name]["sha256"], f"Raw checksum mismatch {name}"
        data = json.loads(path.read_bytes())
        years = [int(item["year"]) for item in data]
        assert len(set(years)) == len(years), f"Duplicate years {code}"
        for item in data:
            value = float(item[PRODUCT])
            assert value >= 0 and 2010 <= int(item["year"]) <= 2050
            rows.append({"country_iso3": code, "year": int(item["year"]),
                         "scenario": args.scenario, "bev_lithium_battery_waste_t": value,
                         "reported_in_api": True, "raw_sha256": digest})
        inventory.append({"country_iso3": code, "reported_year_count": len(years),
                          "first_year": min(years), "last_year": max(years),
                          "unreported_years": ";".join(str(y) for y in range(2010, 2051) if y not in years)})
    frame = pd.DataFrame(rows)
    country = frame.loc[frame.country_iso3.isin(EU27)].copy()
    aggregate = frame.loc[frame.country_iso3.eq("EU27_check")].set_index("year").bev_lithium_battery_waste_t
    counts = country.groupby("year").country_iso3.nunique()
    totals = country.groupby("year").bev_lithium_battery_waste_t.sum(min_count=1)
    audit = pd.DataFrame({"countries_reporting": counts, "country_sum_t": totals,
                          "api_aggregate_t": aggregate})
    audit["absolute_difference_t"] = (audit.country_sum_t-audit.api_aggregate_t).abs()
    # Agreement of a partial historical sum is diagnostic only. Analysis
    # years must have all 27 explicit country records, even if values are zero.
    full = audit.loc[audit.countries_reporting.eq(27)].copy()
    assert set(range(2025, 2051)).issubset(set(full.index)), "Incomplete selected years"
    assert full.absolute_difference_t.max() < 1e-6, "EU27 aggregate checksum failed"
    frame.to_csv(out / "eu27_bev_lithium_battery_waste_all_reported_years.csv", index=False)
    country.loc[country.year.ge(2025)].to_csv(out / "eu27_bev_lithium_battery_waste_2025_2050.csv", index=False)
    pd.DataFrame(inventory).to_csv(out / "reported_year_coverage.csv", index=False)
    audit.to_csv(out / "complete_country_sum_audit.csv")
    summary = {"derived_at_utc": datetime.now(timezone.utc).isoformat(),
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "raw_capture": str(out / "request_manifest.json"),
               "resolution": "Sparse historical records accepted; absence never treated as zero",
               "countries": len(EU27), "network_analysis_period": "2025-2050",
               "explicit_country_years_in_analysis": int(len(country.loc[country.year.ge(2025)])),
               "complete_country_years": full.index.tolist(),
               "aggregate_max_absolute_difference_t": float(full.absolute_difference_t.max()),
               "verified_supply_slice": True,
               "supply_interpretation": "FutuRaM lithium-rechargeable product mass reported under BEV application filters; pack structural and auxiliary battery products excluded; not collected black mass",
               "supersedes_mislabeled_working_files": ["eu27_bev_pack_waste_all_reported_years.csv", "eu27_bev_pack_waste_2025_2050.csv"],
               "selected_totals_t": {str(y): float(aggregate.loc[y]) for y in (2025, 2030, 2035, 2040, 2050)}}
    (out / "derivation_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
