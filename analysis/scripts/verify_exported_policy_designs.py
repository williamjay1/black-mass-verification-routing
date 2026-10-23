"""Independent exported-policy audit; does not import the optimizer code."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'datasets/futuram_network_inputs_20260930_v1'
OUT=ROOT/'qa/content_delivery_20261001_v1'

def independent_signal(c,p):
    policy=c['policy']
    if policy=='none':return {'untested':(p,1-p)},0.
    if policy=='cascade':
        ss,fs,sc,fc=[c[x] for x in ('screen_s','screen_f','confirm_s','confirm_f')]
        sj=max(0,ss+sc-1) if c['conservative_joint_s'] else ss*sc
        fj=fs*fc+c['bad_error_dependence']*(min(fs,fc)-fs*fc)
        return {'both_positive':(p*sj,(1-p)*fj),
                'screen_positive_confirm_negative':(p*(ss-sj),(1-p)*(fs-fj)),
                'screen_negative':(p*(1-ss),(1-p)*(1-fs))},c['screen_fee']+c['confirm_fee']*(p*ss+(1-p)*fs)
    if policy=='perfect':s,f,fee=1.,0.,c['confirm_fee']
    else:
        prefix='screen' if policy=='screen' else 'confirm'
        s,f,fee=[c[prefix+x] for x in ('_s','_f','_fee')]
    return {'positive':(p*s,(1-p)*f),'negative':(p*(1-s),(1-p)*(1-f))},fee

def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    distance=pd.read_csv(DATA/'national_origin_hub_geodesic_matrix.csv')
    ds={(r.origin_id,r.hub_id):r.distance_km for r in distance.itertuples()}
    inputs=[]
    for file in ('signal_policy_export_20261001_v2/smoke_all_runs.json','signal_capacity_20261001_v4/capacity_all_runs.json','signal_reservation_premium_20261001_v1/premium_all_runs.json'):
        inputs.extend([(file,i,r) for i,r in enumerate(json.loads((ROOT/'results'/file).read_text()))])
    for file,i,r in inputs:
        c=r['config'];org=pd.read_csv(DATA/f"national_origins_{c['year']}.csv")
        supply=dict(zip(org.origin_id,org.reference_black_mass_tpy));total=sum(supply.values())
        cap={(x['hub_id'],x['route']):x['capacity_tpy'] for x in r['capacity']}
        premium=sum(cap.values())*c.get('incremental_reservation_premium_per_tpy',0.)
        policy=r['signal_contingent_nominal_policy_flows']
        for label in r['signal_labels']:
            for origin,S in supply.items():
                nominal=sum(x['nominal_if_all_input_had_signal_t'] for x in policy if x['signal']==label and x['origin_id']==origin)
                assert abs(nominal-S)<1e-5,(file,i,label,origin)
        for scenario in r['scenarios']:
            p=scenario['p_compatible'];signal,fee=independent_signal(c,p)
            loads={};processing=0.;tkm=0.;unique=0.
            for x in policy:
                g,b=signal[x['signal']];nominal=x['nominal_if_all_input_had_signal_t'];pi=g+b
                unique+=pi*nominal;tkm+=pi*nominal*ds[(x['origin_id'],x['hub_id'])]*c['distance_multiplier']
                if x['route']=='D':
                    processing+=nominal*(g*22010+b*(c['sunk_cost_fraction']*22010+c['fallback_cost_multiplier']*36000))
                    for route,coeff in [('D',g+c['failed_direct_capacity_fraction']*b),('P',b)]:
                        key=(x['hub_id'],route);loads[key]=loads.get(key,0)+coeff*nominal
                    assert b/pi<=c['risk_cap']+1e-8
                else:
                    processing+=pi*nominal*{'H':30840,'P':36000}[x['route']]
                    key=(x['hub_id'],x['route']);loads[key]=loads.get(key,0)+pi*nominal
            reconstructed=processing+fee*total+tkm*c['transport_per_tkm']+premium
            assert abs(reconstructed-scenario['total_cost_model_usd'])<.01,(file,i,p,reconstructed,scenario['total_cost_model_usd'])
            assert abs(unique-total)<1e-5
            # Mean-load exports predate the optional reliability certificate.
            # Absence is valid only for the declared zero-lot specification.
            kappa=r.get('certified_mean_capacity_fraction')
            if kappa is None:
                assert c.get('maximum_independent_lot_t',0.)==0.,(file,i,'missing certificate')
                kappa=1.
            for key,load in loads.items():assert load<=kappa*cap.get(key,0)+1e-5,(file,i,p,key,load)
            rows.append({'source':file,'run_id':i,'p':p,'reconstructed_cost':reconstructed,
                         'cost_residual':reconstructed-scenario['total_cost_model_usd'],
                         'unique_input_residual':unique-total,'capacity_constraints_pass':True})
    pd.DataFrame(rows).to_csv(OUT/'exported_policy_independent_checks.csv',index=False)
    print(json.dumps({'run_count':len(inputs),'profile_count':len(rows),'all_pass':True,'max_abs_cost_residual':max(abs(x['cost_residual']) for x in rows)}))

if __name__=='__main__':main()
