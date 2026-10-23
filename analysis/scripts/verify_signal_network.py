"""Independent arithmetic and edge checks for the revised network model."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from run_signal_contingent_network import Config,signals

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/signal_contingent_20261001_v1'

def main():
    tests=[]
    for p in (0.,.01,.2,.5,.8,1.):
        for mode in ('none','screen','confirmation','cascade','perfect'):
            for eta in (0.,1.):
                c=Config(policy=mode,bad_error_dependence=eta,conservative_joint_s=True)
                _,g,b,fee=signals(p,c)
                assert np.all(g>=-1e-14) and np.all(b>=-1e-14)
                assert np.isclose(g.sum(),p) and np.isclose(b.sum(),1-p)
                tests.append({'p':p,'policy':mode,'eta':eta,'mass_conservation':True})
    # Bayes formula independently rearranged and tested at equality.
    for p in (.01,.2,.5,.8,.99):
        for s in (.8,.95,.99):
            for rho in (.01,.05,.1,.2):
                f=rho*p*s/((1-rho)*(1-p))
                if f<=1:
                    q=(1-p)*f/(p*s+(1-p)*f)
                    assert abs(q-rho)<1e-12
    rows=[]
    data=json.loads((OUT/'full_all_runs.json').read_text())
    cd,ch,cp=22010.,30840.,36000.
    for r in data:
        c=Config(**r['config'])
        assert r['max_constraint_violation']<1e-5
        capacity=sum(x['capacity_tpy'] for x in r['capacity'])
        for sc in r['scenarios']:
            # Full cost is reconstructed from saved terminal masses; false
            # positives consume fallback plus the separately stated sunk part.
            expected=(sc['direct_compatible_t']*cd+sc['false_positive_fallback_t']*(c.sunk_cost_fraction*cd+c.fallback_cost_multiplier*cp)
                      +sc['hydro_primary_t']*ch+sc['pyro_primary_t']*cp+sc['assay_cost_model_usd']+sc['transport_tkm']*c.transport_per_tkm)
            assert abs(expected-sc['total_cost_model_usd'])<.01
            assert abs(sc['total_terminal_input_equivalent_t']-sc['unique_input_t'])<1e-5
            assert abs(sc['total_process_input_equivalent_t']-sc['unique_input_t']-c.failed_direct_capacity_fraction*sc['false_positive_fallback_t'])<1e-5
            rows.append({'policy':c.policy,'p':sc['p_compatible'],'reconstructed_cost_usd':expected,'reported_cost_usd':sc['total_cost_model_usd'],
                         'reserved_capacity_tpy':capacity,'all_checks_pass':True})
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'independent_arithmetic_checks.csv',index=False)
    # Nonunique capacity ties do not justify unique site recommendations.
    summary={'signal_edge_test_count':len(tests),'reconstructed_scenario_count':len(rows),
             'all_checks_pass':True,'decision_claim':'scenario reliability/cost/capacity frontiers, not unique actual EU sites or investments'}
    (OUT/'verification_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
