"""Strong fixed-design and source-aggregate comparators; no new fitted data."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/strong_comparators_20261001_v1'
AW={'Ni':58.6934,'Co':58.933194,'Mn':54.938044}
RATIO={'Ni':.6,'Co':.2,'Mn':.2}
MW=6.94+sum(AW[e]*RATIO[e] for e in AW)+2*15.999

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    runs=json.loads((ROOT/'results/signal_reservation_premium_20261001_v1/premium_all_runs.json').read_text())
    def pick(policy,b,h):
        return next(x for x in runs if x['config']['policy']==policy and x['config']['maximum_independent_lot_t']==b and x['config']['incremental_reservation_premium_per_tpy']==h)
    zero=pick('cascade',10.,0.);joint=pick('cascade',10.,500.);baseline=pick('none',10.,500.)
    frozen_capacity=sum(x['capacity_tpy'] for x in zero['capacity'])
    frozen=zero['worst_cost_model_usd']+500*frozen_capacity
    result={'frozen_zero_premium_policy_plus_premium_model_usd':frozen,
            'frozen_capacity_tpy':frozen_capacity,
            'joint_incumbent_model_usd':joint['worst_cost_model_usd'],
            'joint_capacity_tpy':sum(x['capacity_tpy'] for x in joint['capacity']),
            'joint_primary_lower_bound_model_usd':joint['primary_lower_bound_model_usd'],
            'saving_vs_frozen_lower_bound_model_usd':frozen-joint['worst_cost_model_usd'],
            'saving_vs_frozen_upper_bound_model_usd':frozen-joint['primary_lower_bound_model_usd'],
            'saving_vs_optimized_all_hydro_model_usd':baseline['worst_cost_model_usd']-joint['worst_cost_model_usd']}
    assert result['saving_vs_frozen_lower_bound_model_usd']>0
    assert result['saving_vs_frozen_upper_bound_model_usd']>=result['saving_vs_frozen_lower_bound_model_usd']
    blend=pd.read_csv(ROOT/'results/qualified_blending_20261001_v1/grade_blending_frontier.csv')
    def choice(limit,rule,d):
        return blend[(blend.quality_limit_pct==limit)&(blend.selection_rule==rule)&(blend.relative_mass_interval==d)].iloc[0]
    strong=choice(.65,'phasewise',0.)
    pooled=choice(.6,'pooled',0.)
    robust=choice(.6,'pooled',.1)
    phase=pd.read_csv(ROOT/'results/qualified_product_mfa_20261001_v1/measured_precipitate_phase_metal_masses.csv')
    z=json.loads(pooled.source_phase_fractions)
    source=np.asarray([z[label] for label in phase.phase_label])@phase[[e+'_g' for e in ['Li','Co','Ni','Mn','Al','Fe','Cu']]].to_numpy()
    n=pooled.tm_stoichiometric_CAM_upper_bound_g/MW
    balances=[]
    for e in AW:
        inventory=pooled['qualified_'+e+'_g'];required=n*RATIO[e]*AW[e]
        surplus=inventory-required
        assert surplus>=-1e-8
        balances.append({'element':e,'selected_inventory_g':inventory,'required_for_idealized_NMC622_g':required,'surplus_g':surplus})
    impurity=source[4:].sum()
    retained_source_metals=source.sum()-sum(x['surplus_g'] for x in balances)
    result.update({'source_high_pH_aggregate_TM_potential_g':strong.tm_stoichiometric_CAM_upper_bound_g,
                   'source_high_pH_aggregate_impurity_pct':strong.nominal_blend_impurity_pct,
                   'pooled_nominal_increment_over_source_aggregate_pct':100*(pooled.tm_stoichiometric_CAM_upper_bound_g/strong.tm_stoichiometric_CAM_upper_bound_g-1),
                   'robust_10pct_selected_nominal_potential_g':robust.nominal_tm_CAM_upper_bound_g,
                   'robust_10pct_minimum_potential_g':robust.tm_stoichiometric_CAM_upper_bound_g,
                   'robust_recipe_phase_fractions':json.loads(robust.source_phase_fractions),
                   'if_all_target_surplus_removed_but_all_impurity_retained_source_metal_grade_pct':100*impurity/retained_source_metals,
                   'interpretation':'Grade is pooled-inventory grade before conversion. Surplus disposition and impurity partition are unidentified. Potentials are not synthesized CAM.'})
    pd.DataFrame(balances).to_csv(OUT/'pooled_inventory_stoichiometric_surpluses.csv',index=False)
    (OUT/'strong_comparator_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
