#!/usr/bin/env python3
"""Reproducible audit of Researchdata.se dataset 2025-299.

The script verifies the dataset's published checksums, preserves duplicate CSV
headers positionally, and produces descriptive, basis-explicit tables. It does
not infer black-mass prevalence, cross-route compatibility, or a life-cycle
inventory from the single-feed experiment.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"D:\MLWork\topic34\manuscript_quality_v2")
DATASET = PROJECT / "datasets" / "researchdata_se_2025-299_20260930"
DATA_ROOT = DATASET / "2025-299-1"
RESULTS = PROJECT / "results" / "researchdata_2025-299_audit_20260930"


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    if not rows:
        raise ValueError(f"Empty CSV: {path}")
    return rows[0], rows[1:]


def number(value: str) -> float | None:
    if value is None or value.strip() == "":
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def verify_checksums() -> list[dict]:
    manifest = DATASET / "sha256.txt"
    result = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = DATASET / relative.strip()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        result.append(
            {
                "relative_path": relative.strip(),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "verified": actual.lower() == expected.lower(),
                "bytes": path.stat().st_size,
            }
        )
    if not result or not all(row["verified"] for row in result):
        raise RuntimeError("At least one published dataset checksum did not verify")
    return result


def audit_bped_runs() -> tuple[list[dict], dict]:
    path = DATA_ROOT / "data" / "Electrodialysis_experimental_data.csv"
    headers, records = read_csv(path)
    if len(headers) != 46 or len(records) != 23:
        raise ValueError(f"Unexpected BPED schema: {len(headers)} columns, {len(records)} rows")

    parsed = []
    lithium_outlet_fields = [
        "Li rinse distribution%",
        "Li salt distribution%",
        "Li acid distribution%",
        "Li base distribution%",
    ]
    for row in records:
        d = dict(zip(headers, row))
        li_parts = [number(d[key]) for key in lithium_outlet_fields]
        closure = sum(x for x in li_parts if x is not None)
        parsed.append(
            {
                "run": int(d["Run"]),
                "flow_rate_L_h": number(d["Flow rate (L/h)"]),
                "feed_concentration_M": number(d["Feed concentration (M)"]),
                "feed_Li2SO4_molar_fraction": number(d["Feed Li2SO4 molar fraction"]),
                "stack_voltage_V": number(d["Stack voltage (V)"]),
                "Li_rinse_distribution_pct": li_parts[0],
                "Li_salt_distribution_pct": li_parts[1],
                "Li_acid_distribution_pct": li_parts[2],
                "Li_base_distribution_pct": li_parts[3],
                "Li_distribution_sum_pct": closure,
                "Li_distribution_closure_error_pp": closure - 100.0,
                "Na_base_distribution_pct": number(d["Na base distribution%"]),
                "S_acid_distribution_pct": number(d["S acid distribution%"]),
                "S_base_distribution_pct": number(d["S base distribution%"]),
            }
        )
    closure_values = [r["Li_distribution_sum_pct"] for r in parsed]
    summary = {
        "rows": len(parsed),
        "runs": [r["run"] for r in parsed],
        "factor_levels": {
            "flow_rate_L_h": sorted({r["flow_rate_L_h"] for r in parsed}),
            "feed_concentration_M": sorted({r["feed_concentration_M"] for r in parsed}),
            "feed_Li2SO4_molar_fraction": sorted({r["feed_Li2SO4_molar_fraction"] for r in parsed}),
            "stack_voltage_V": sorted({r["stack_voltage_V"] for r in parsed}),
        },
        "Li_base_distribution_pct_min": min(r["Li_base_distribution_pct"] for r in parsed),
        "Li_base_distribution_pct_max": max(r["Li_base_distribution_pct"] for r in parsed),
        "Li_distribution_closure_pct_min": min(closure_values),
        "Li_distribution_closure_pct_max": max(closure_values),
        "Li_distribution_closure_abs_error_pp_max": max(abs(x - 100.0) for x in closure_values),
    }
    return parsed, summary


def audit_solid_composition() -> tuple[list[dict], dict]:
    path = DATA_ROOT / "data" / "Solids_composition_experimental_data.csv"
    headers, records = read_csv(path)
    if len(headers) != 25:
        raise ValueError(f"Unexpected solid composition schema: {len(headers)} columns")

    # Columns D:N are measured digest-solution concentrations; P:Y are
    # author-calculated concentrations on the solid-mass basis. Duplicate
    # labels are intentionally indexed by position rather than DictReader.
    analytes = ["F", "Cu", "Al", "Fe", "P", "Co", "Mn", "Ni", "Li", "Na", "S"]
    solid_rows = []
    for row in records:
        mass_g = number(row[1])
        item = {"sample": row[0], "sample_mass_g": mass_g, "dissolution_volume_L": number(row[2])}
        for j, element in enumerate(analytes):
            solution_value = number(row[3 + j])
            solid_value = number(row[14 + j])
            item[f"{element}_digest_mg_per_kg_solution"] = solution_value
            item[f"{element}_solid_mg_per_kg"] = solid_value
            item[f"{element}_estimated_mass_mg"] = (
                solid_value * mass_g / 1000.0
                if solid_value is not None and mass_g is not None
                else None
            )
        solid_rows.append(item)
    summary = {
        "samples": len(solid_rows),
        "analytes": analytes,
        "basis": "The published solid-basis columns P:Y (mg/kg solid) multiplied by sample mass (g)/1000; not a stage recovery unless paired feed/output boundaries are independently established.",
        "duplicate_header_handled_positionally": True,
        "blank_solid_basis_cells": sum(
            1 for r in solid_rows for el in analytes if r[f"{el}_solid_mg_per_kg"] is None
        ),
    }
    return solid_rows, summary


def audit_current_log() -> tuple[list[dict], dict]:
    path = DATA_ROOT / "data" / "Current_log_experimental_data.csv"
    headers, records = read_csv(path)
    if len(headers) != 5:
        raise ValueError(f"Unexpected current log schema: {headers}")
    valid = []
    blank_rows = 0
    for row in records:
        if not any(cell.strip() for cell in row):
            blank_rows += 1
            continue
        d = dict(zip(headers, row))
        timestamp = datetime.strptime(f"{d['Date']} {d['Time']}", "%Y-%m-%d %H:%M:%S")
        valid.append(
            {
                "test_id": d["Test ID"].strip(),
                "timestamp": timestamp,
                "current_A": number(d["Current (A)" ]),
                "voltage_V": number(d["Voltage (V)" ]),
            }
        )
    groups: dict[str, list[dict]] = {}
    for row in valid:
        if row["test_id"]:
            groups.setdefault(row["test_id"], []).append(row)

    energy_rows = []
    for test_id, samples in sorted(groups.items(), key=lambda pair: int(pair[0].split()[-1])):
        samples.sort(key=lambda r: r["timestamp"])
        energy_Wh = 0.0
        for left, right in zip(samples, samples[1:]):
            dt_h = (right["timestamp"] - left["timestamp"]).total_seconds() / 3600.0
            if dt_h < 0:
                raise ValueError(f"Non-monotone timestamps in {test_id}")
            p0 = left["current_A"] * left["voltage_V"]
            p1 = right["current_A"] * right["voltage_V"]
            energy_Wh += (p0 + p1) / 2.0 * dt_h
        duration_h = (samples[-1]["timestamp"] - samples[0]["timestamp"]).total_seconds() / 3600.0
        energy_rows.append(
            {
                "test_id": test_id,
                "n_readings": len(samples),
                "start": samples[0]["timestamp"].isoformat(sep=" "),
                "end": samples[-1]["timestamp"].isoformat(sep=" "),
                "observed_duration_h": duration_h,
                "observed_interval_energy_Wh": energy_Wh,
                "mean_current_A": sum(r["current_A"] for r in samples) / len(samples),
                "mean_voltage_V": sum(r["voltage_V"] for r in samples) / len(samples),
                "note": "Trapezoidal integration between recorded samples only; excludes unobserved run start/end tails and auxiliaries.",
            }
        )
    summary = {
        "source_rows_excluding_header": len(records),
        "blank_rows": blank_rows,
        "valid_timestamp_rows": len(valid),
        "identified_test_groups": len(groups),
        "integrated_test_rows": len(energy_rows),
        "integration": "E_Wh = sum((I_i V_i + I_{i+1} V_{i+1})/2 * delta_t_hours)",
        "scope_warning": "Measured stack electricity interval only; not normalized per kg product and not a complete process inventory.",
    }
    return energy_rows, summary


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    checksums = verify_checksums()
    runs, run_summary = audit_bped_runs()
    solids, solids_summary = audit_solid_composition()
    energy, energy_summary = audit_current_log()

    write_csv(RESULTS / "bped_run_descriptive_metrics.csv", list(runs[0]), runs)
    write_csv(RESULTS / "solid_sample_basis_audit.csv", list(solids[0]), solids)
    write_csv(RESULTS / "current_log_integrated_energy.csv", list(energy[0]), energy)
    write_csv(RESULTS / "checksum_verification.csv", list(checksums[0]), checksums)
    summary = {
        "run_date": "2026-09-30",
        "catalogue_doi": "10.5878/t5h5-w009",
        "catalogue_id": "Researchdata.se 2025-299, version 1",
        "license": "CC BY 4.0 (catalogue record)",
        "source_raw_path": r"F:\AcademicData\topic34\raw\researchdata_se_2025-299_20260930\researchdata_se_2025-299_original.zip",
        "working_copy": str(DATASET),
        "checksums_all_verified": all(row["verified"] for row in checksums),
        "published_dataset_scope": "NMC811-type black-mass leaching measurements and 23 BPED tests using a synthetic Na2SO4-Li2SO4 feed; laboratory data from Lulea, Sweden.",
        "bped_runs": run_summary,
        "solid_composition": solids_summary,
        "current_log": energy_summary,
        "limits": [
            "One black-mass feed/source; not a representative European lot sample.",
            "BPED experiment uses synthetic sulfate feed; it is not the black-mass leachate feed in every run.",
            "No independent direct-regeneration compatibility labels or assay confusion matrix.",
            "The current/voltage integral omits the intervals before the first and after the last recorded samples and all balance-of-plant loads.",
            "No complete life-cycle inventory is reconstructed from these files.",
        ],
    }
    (RESULTS / "audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutputs: {RESULTS}")


if __name__ == "__main__":
    main()
