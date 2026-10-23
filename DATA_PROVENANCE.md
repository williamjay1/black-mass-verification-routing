# Data provenance and source terms

This repository contains derived analytical inputs, saved outputs, and author generated figures. It does not redistribute complete third-party articles or licensed commercial inventories.

## Source register

| Input | Persistent identifier or location | Terms | Use in this repository |
|---|---|---|---|
| FutuRaM stock and flow and recovery data, batteries, V2 | https://doi.org/10.5281/zenodo.21128664 | CC BY 4.0 | National battery electric vehicle lithium cell waste projections, 2025 to 2050. |
| FutuRaM composition raw data, batteries, version 4 | https://doi.org/10.5281/zenodo.21259059 | CC BY 4.0 | Cell composition and chemistry share context. |
| Urban Mine Platform public API snapshot | https://www.urbanmineplatform.eu/waste-stream/batteries/charts | Public platform terms | Frozen filtered API response. The exact request is in `analysis/datasets/ump_bev_flows_20260930_v1/request_manifest.json`. |
| OPARA-276 cell type data | https://doi.org/10.25532/OPARA-276 | CC BY 4.0 | Ten automotive cell types, black mass yield and composition envelope. |
| OPARA-769 shredder and mill data | https://doi.org/10.25532/OPARA-769 | CC BY 4.0 | Descriptive process variability. |
| GISCO NUTS 2024 label points | https://gisco-services.ec.europa.eu/distribution/v2/nuts/nuts-2024-files.html | Eurostat terms | National origin geometry for distance calculation. The GeoJSON itself is not redistributed. |
| European lithium battery recycling facilities, version 1 | https://doi.org/10.5281/zenodo.13766892 | CC BY 4.0 | Candidate city locations. City options are not verified plant addresses, permits, or current capacity. |
| Purification data underlying the mixed LFP and NMC study | https://doi.org/10.4121/58947ce2-c651-43cc-8e4d-760b2e60adfb | CC BY 4.0 | Six measured precipitation products and original feed metal balances. |
| Complete pathway cost coefficients | https://doi.org/10.1002/aenm.202500699 | Article CC BY-NC | Attributed numeric cost coefficients from the source case. No article text or supplementary file is redistributed. |
| Regulation (EU) 2023/1542 | https://eur-lex.europa.eu/eli/reg/2023/1542/oj | Public legal text | Regulatory context. Not used as a model input. |
| Commission Delegated Regulation (EU) 2025/606 | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202500606 | Public legal text | Regulatory context. Not used as a model input. |

## What is redistributed

- Derived national origin tables and candidate hub distance inputs.
- A frozen, filtered public API snapshot with its request manifest.
- Exported routing and capacity designs, solver bounds, campaign replay tables, product reconstruction tables, and vector figures.
- Analysis code and audit code.

## What is not redistributed

- Complete third-party journal articles or their supplementary files.
- Licensed commercial life cycle inventory.
- Private plant data, permits, or commercial assay specifications.
- Submission correspondence, invitation details, or personalized portal links.
- The journal LaTeX class or manuscript PDFs.

## Attribution and compliance

Users must comply with the original source terms listed above. The author generated derived tables and figures are released under CC BY 4.0 as described in `DATA_LICENSE.md`. The code is released under the MIT License as described in `LICENSE`.

Where a source is marked CC BY 4.0, attribution should retain the original dataset citation. Where a source is marked article CC BY-NC, only the attributed numeric coefficients are used and the article itself is not redistributed.
