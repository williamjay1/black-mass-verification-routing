# Verification aware routing and finite lot capacity certification for black mass recycling

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23637928.svg)](https://doi.org/10.5281/zenodo.23637928)

This repository is the public data and code package for the manuscript:

> Wang, S.; Zhang, J. Verification aware routing and finite lot capacity certification for black mass recycling. 2026, invited submission.

It contains the derived inputs, analysis code, saved solver outputs, campaign stress results, product qualification results, and vector figures needed to reproduce the reported conditional design boundaries. It does not contain third-party article PDFs, licensed commercial life cycle inventory, private plant data, or submission correspondence.

## What the study does

The workflow links an imperfect assay signal to four decisions:

1. whether a black mass lot is admitted to direct recycling;
2. how observed signals are routed across direct, hydrometallurgical, and pyrometallurgical routes;
3. how much integer hub capacity and fallback reserve are required for a finite campaign;
4. how much measured recovered inventory can be credited before downstream conversion.

The model is nonanticipative: operators observe the assay outcome, not the latent compatibility state. Capacity reliability uses a one sided Bernstein certificate with a declared independent campaign mass. Product qualification is reconstructed from a public measured purification workbook and is kept separate from feed routing.

## Repository layout

```text
.
├── analysis/
│   ├── datasets/        derived network inputs and frozen public API snapshot
│   ├── scripts/         analysis and audit code
│   ├── results/         exported designs, solver outputs, stress and product results
│   └── figures/         vector figures used in the manuscript
├── datasets/
│   └── upgrade/         route cost registry and candidate hub nodes
├── CITATION.cff
├── DATA_LICENSE.md
├── DATA_PROVENANCE.md
├── LICENSE
├── MANIFEST.sha256
├── README.md
└── requirements.txt
```

The `analysis/` directory preserves the relative paths used by the scripts. Run commands from `analysis/`, not from the repository root.

## Reproduce the saved results

Python 3.12 is required. The recorded run used Python 3.12.10 and the versions in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd analysis

python -B scripts/inventions_engineering_baselines.py
python -B scripts/stress_campaign_dependence.py
python -B scripts/verify_exported_policy_designs.py
```

The scripts write to `analysis/results/` and may create a `qa/` folder for independent verification output. Timestamps and runtime fields in regenerated manifests will differ from the archived files.

Expected checks from the archived run:

- 6,492 independent engineering checks passed.
- 32 exported policy designs and 96 profiles verified.
- 85,561 centralized layouts evaluated per policy.
- 51 of 52 simple product baseline conditions matched within tolerance.
- 280 campaign cells and 1,146,880 repetitions.
- 1,991 of 4,096 mean load confirmation overflows at 10 t and 80% compatible feed.
- 637 of 4,096 mean load sequential overflows at the same condition.
- Zero overflow for both certified 10 t designs at the same condition.

The scripts that fetch or capture external sources, such as `fetch_*.py`, `capture_inventions_journal.py`, and `extract_tudelft_public_ods.py`, are included for provenance. They require the original external source locations or network access and are not needed for the offline reproduction above. Raw acquisition is not repeated by the three verification commands.

## Data and code availability

The public source datasets are identified by persistent identifiers in the manuscript and in `DATA_PROVENANCE.md`. This repository redistributes derived analytical tables and a frozen public API snapshot, not the complete third-party source archives. No licensed commercial background inventory is included. No new laboratory, human participant, or private company data were collected.

## Licenses

- Code in `analysis/scripts/` and the repository automation files: MIT, see `LICENSE`.
- Derived data tables, result tables, and figures created by the authors: CC BY 4.0, see `DATA_LICENSE.md`.
- Third-party source data: original terms apply, see `DATA_PROVENANCE.md`.

## Citation

Archived at Zenodo:

- Version 1.0.0 DOI: https://doi.org/10.5281/zenodo.23637928
- Concept DOI for all versions: https://doi.org/10.5281/zenodo.23637927

```text
Wang, S.; Zhang, J. Verification aware routing and finite lot capacity certification
for black mass recycling. Version 1.0.0. Zenodo, 2026.
https://doi.org/10.5281/zenodo.23637928
```

Use the version DOI for the exact released snapshot and the concept DOI when referring to all versions.

## Contact

Junjie Zhang, corresponding author: junjiezhang2024@shisu.edu.cn

Siyu Wang: wangsiyu@shisu.edu.cn

