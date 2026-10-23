"""Independent conditional-lot simulation; no EU/assay validation claim."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from run_signal_contingent_network import Config,signals

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/capacity_verification_20261001_v1'
DATA=ROOT/'datasets/futuram_network_inputs_20260930_v1'

def simulate(run,lot,reps=4096):
    c=Config(**run['config']);org=pd.read_csv(DATA/f'national_origins_{c.year}.csv')
    hubs=pd.read_csv(DATA/'candidate_hubs.csv').sort_values('hub_id').reset_index(drop=True)
    hi={h:i for i,h in enumerate(hubs.hub_id)};route={'D':0,'H':1,'P':2}
    caps=np.zeros((len(hubs),3))
    for x in run['capacity']:caps[hi[x['hub_id']],route[x['route']]]=x['capacity_tpy']
    policies=run['signal_contingent_nominal_policy_flows'];rows=[]
    rng=np.random.default_rng(34034)
    for p in (.2,.5,.8):
        labels,g,b,_=signals(p,c);signalmap={s:i for i,s in enumerate(labels)}
        loads=np.zeros((reps,len(hubs),3))
        for o in org.itertuples():
            channels=[x for x in policies if x['origin_id']==o.origin_id]
            probabilities=[];loadindex=[]
            for channel in channels:
                sig=signalmap[channel['signal']];fraction=channel['nominal_if_all_input_had_signal_t']/o.reference_black_mass_tpy
                for state,prob in (('good',g[sig]),('bad',b[sig])):
                    probabilities.append(prob*fraction)
                    loadindex.append((hi[channel['hub_id']],route[channel['route']],state))
            pr=np.asarray(probabilities);assert abs(pr.sum()-1)<1e-7
            pr/=pr.sum();full=int(o.reference_black_mass_tpy//lot);rem=o.reference_black_mass_tpy-full*lot
            counts=rng.multinomial(full,pr,size=reps)*lot
            if rem>1e-10:counts=counts+rng.multinomial(1,pr,size=reps)*rem
            for i,(j,k,state) in enumerate(loadindex):
                if k==0 and state=='bad':
                    loads[:,j,0]+=counts[:,i]*c.failed_direct_capacity_fraction
                    loads[:,j,2]+=counts[:,i]
                else:loads[:,j,k]+=counts[:,i]
        exceed=(loads>caps[None,:,:]+1e-7).any(axis=(1,2))
        rows.append({'policy':c.policy,'p':p,'maximum_lot_t':lot,'design_capacity_lot_t':c.maximum_independent_lot_t,
                     'repetitions':reps,'sample_overflow_share':float(exceed.mean()),'overflow_count':int(exceed.sum()),
                     'maximum_process_input_t':float(loads.sum(axis=(1,2)).max()),'reserved_capacity_tpy':float(caps.sum()),
                     'simulation_role':'conditional model check; independent lots/allocated channel sampling assumed, no empirical reliability estimate'})
    return rows

def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    base=json.loads((ROOT/'results/signal_policy_export_20261001_v2/smoke_all_runs.json').read_text())
    for r in base:
        if r['config']['policy'] in ('confirmation','cascade'):rows.extend(simulate(r,10.))
    path=ROOT/'results/signal_capacity_20261001_v4/capacity_all_runs.json'
    if not path.exists():raise FileNotFoundError('certified-capacity designs not complete')
    for r in json.loads(path.read_text()):
        if r['config']['maximum_independent_lot_t']==10 and r['config']['policy'] in ('confirmation','cascade'):rows.extend(simulate(r,10.))
    pd.DataFrame(rows).to_csv(OUT/'conditional_lot_overflow_checks.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':main()
