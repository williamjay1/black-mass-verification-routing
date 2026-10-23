"""Verify package hashes and rerun core models from a fresh D working folder."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    zip_path=ROOT/'output/topic34_inventions_v14_reproducibility_r2.zip'
    parent=ROOT/'temp';parent.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='portable_inventions_v14_',dir=parent))
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target=(work/name).resolve()
            assert target.is_relative_to(work.resolve()),name
        z.extractall(work)
    manifest=json.loads((work/'package_manifest.json').read_text())
    for x in manifest['files']:
        p=work/x['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],x['path']
    project=work/'manuscript_quality_v2';env=os.environ.copy();env['MPLCONFIGDIR']=str(work/'matplotlib_cache')
    compare=['results/inventions_campaign_stress_20261023_v2/fixed_policy_campaign_replay.csv',
             'results/inventions_campaign_stress_20261023_v2/certified_handling_limits.csv',
             'results/inventions_engineering_baselines_20261023_v1/centralized_heuristic_comparison.csv',
             'results/inventions_engineering_baselines_20261023_v1/fixed_routing_capacity_reblocking.csv',
             'results/inventions_engineering_baselines_20261023_v1/product_greedy_52_conditions.csv',
             'results/inventions_engineering_baselines_20261023_v1/post_stoichiometry_impurity_removal_requirements.csv']
    original={p:hashlib.sha256((project/p).read_bytes()).hexdigest() for p in compare}
    commands=[['stress_campaign_dependence.py'],['inventions_engineering_baselines.py'],
              ['verify_exported_policy_designs.py'],['audit_inventions_delivery.py']]
    checks=[]
    for args in commands:
        res=subprocess.run([sys.executable,'-X','utf8',str(project/'scripts'/args[0]),*args[1:]],cwd=project,env=env,capture_output=True,text=True,encoding='utf-8',timeout=1200)
        (work/(args[0]+'.log')).write_text(res.stdout+'\n'+res.stderr,encoding='utf-8')
        assert res.returncode==0,(args[0],res.stderr[-1000:])
        checks.append({'script':args[0],'returncode':res.returncode})
        print(json.dumps(checks[-1]),flush=True)
    for p,h in original.items():assert hashlib.sha256((project/p).read_bytes()).hexdigest()==h,p
    report={'working_copy':str(work),'package_hashes_pass':True,'file_count':len(manifest['files']),
            'core_reruns':checks,'six_core_csvs_bitwise_reproduced':True,'compared_csvs':compare,
            'scope':'Fresh working directory; same recorded Python/library runtime, not a cross-platform external replication. No source F/E files were modified.'}
    (ROOT/'qa/inventions_delivery_20261023_v1/portable_bundle_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
