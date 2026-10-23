"""Verify package hashes and rerun core models from a fresh D working folder."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    zip_path=ROOT/'output/topic34_content_v13_reproducibility.zip'
    parent=ROOT/'temp';parent.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='portable_v13_',dir=parent))
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target=(work/name).resolve()
            assert target.is_relative_to(work.resolve()),name
        z.extractall(work)
    manifest=json.loads((work/'package_manifest.json').read_text())
    for x in manifest['files']:
        p=work/x['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],x['path']
    project=work/'manuscript_quality_v2';env=os.environ.copy();env['MPLCONFIGDIR']=str(work/'matplotlib_cache')
    commands=[['run_signal_contingent_network.py','--mode','smoke','--limit','120','--output-tag','portable_smoke'],
              ['optimize_grade_blending.py'],['audit_strong_comparators.py'],['verify_exported_policy_designs.py']]
    checks=[]
    for args in commands:
        res=subprocess.run([sys.executable,'-X','utf8',str(project/'scripts'/args[0]),*args[1:]],cwd=project,env=env,capture_output=True,text=True,encoding='utf-8',timeout=1200)
        (work/(args[0]+'.log')).write_text(res.stdout+'\n'+res.stderr,encoding='utf-8')
        assert res.returncode==0,(args[0],res.stderr[-1000:])
        checks.append({'script':args[0],'returncode':res.returncode})
        print(json.dumps(checks[-1]),flush=True)
    old=json.loads((project/'results/signal_policy_export_20261001_v2/smoke_all_runs.json').read_text())
    new=json.loads((project/'results/portable_smoke/smoke_all_runs.json').read_text())
    assert len(old)==len(new)==5
    deltas=[abs(x['worst_cost_model_usd']-y['worst_cost_model_usd']) for x,y in zip(old,new)]
    assert max(deltas)<20.,deltas
    assert all(x['max_constraint_violation']<1e-5 for x in new)
    report={'working_copy':str(work),'package_hashes_pass':True,'file_count':len(manifest['files']),
            'core_reruns':checks,'five_policy_costs_reproduced':True,'maximum_cost_difference_model_usd':max(deltas),
            'scope':'Fresh working directory; same recorded Python/library runtime, not a cross-platform external replication. No source F/E files were modified.'}
    (ROOT/'qa/content_delivery_20261001_v1/portable_bundle_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
