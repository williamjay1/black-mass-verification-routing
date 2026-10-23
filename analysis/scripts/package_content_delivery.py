"""Non-destructive, selected scientific reproduction package on D drive."""
from pathlib import Path
import csv,hashlib,json,platform,zipfile
from datetime import datetime,timezone
import numpy,pandas,scipy,matplotlib,openpyxl

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'

def main():
    files=[]
    def add(path,arc=None):
        assert path.is_file(),path
        files.append((path,arc or 'manuscript_quality_v2/'+path.relative_to(ROOT).as_posix()))
    for name in ('main_content_v13.tex','supplement_content_v13.tex','README_content_delivery.md','submission_materials.md'):
        add(ROOT/name)
    for folder in ('scripts','datasets/futuram_network_inputs_20260930_v1','datasets/ump_bev_flows_20260930_v1','figures/content_v13'):
        for p in sorted((ROOT/folder).glob('*')):
            if p.is_file() and p.suffix in ('.py','.csv','.json','.pdf'):add(p)
    for folder in ('signal_contingent_20261001_v1','signal_policy_export_20261001_v2','signal_capacity_20261001_v4','signal_reservation_premium_20261001_v1','capacity_verification_20261001_v1','qualified_product_mfa_20261001_v1','qualified_blending_20261001_v1','strong_comparators_20261001_v1','content_revision_20261001_v1'):
        for p in sorted((ROOT/'results'/folder).glob('*')):
            if p.is_file() and p.suffix in ('.csv','.json'):add(p)
    for name in ('journal_literature_refresh_20261001.md','content_review_20261001.md','content_revision_response_20261001.md'):
        add(ROOT/'qa'/name)
    for name in ('audit_summary.json','numeric_claim_trace.csv','exported_policy_independent_checks.csv'):
        add(ROOT/'qa/content_delivery_20261001_v1'/name)
    add(ROOT.parent/'results/clarivate_mjl_access_audit_2026-08-29.md','journal_evidence/clarivate_mjl_access_audit_2026-08-29.md')
    for name in ('route_parameter_registry_2026-09-26.csv','eu27_candidate_hub_nodes_2026-09-26.csv'):
        add(ROOT.parent/'datasets/upgrade'/name,'datasets/upgrade/'+name)
    for name in ('main_content_v13.pdf','supplement_content_v13.pdf'):
        add(ROOT/'output/pdf'/name)
    raw=Path(r'F:\AcademicData\topic34\raw\ump_bev_flows_20260930_v1')
    for p in sorted(raw.glob('*.json')):
        add(p,'manuscript_quality_v2/datasets/ump_bev_flows_20260930_v1/raw_snapshot/'+p.name)
    assert len({a for p,a in files})==len(files)
    manifest={'generated_utc':datetime.now(timezone.utc).isoformat(),
              'python':platform.python_version(),
              'libraries':{m.__name__:m.__version__ for m in (numpy,pandas,scipy,matplotlib,openpyxl)},
              'scientific_scope':'Conditional engineering planning with public workload projections and separately reconstructed measured product balances; no real EU profitability, actual CAM yield, instrument validation, or comparative LCA.',
              'source_licenses':'Attributions and source-specific limitations are retained. FutuRaM/OPARA CC BY 4.0, geometry/inventory source provenance retained; no protected journal full text, complete 4TU raw archive, or paid LCI redistributed. No blanket license over third-party material.',
              'files':[{'path':a,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,a in files]}
    dest=OUT/'topic34_content_v13_reproducibility.zip'
    assert not dest.exists(),'Choose a new package version; do not overwrite an existing delivery.'
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for p,a in files:z.write(p,a)
        z.writestr('package_manifest.json',json.dumps(manifest,indent=2))
    print(json.dumps({'package':str(dest),'bytes':dest.stat().st_size,'file_count':len(files),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'libraries':manifest['libraries']},indent=2))

if __name__=='__main__':main()
