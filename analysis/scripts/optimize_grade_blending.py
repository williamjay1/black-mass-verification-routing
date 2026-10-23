"""Measured-product blending frontier; no battery-grade or scale-up claim.

One-variable-at-a-time quality/mass-error envelopes are declared design
conditions. The source metal recovery denominator is audited separately.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from scipy.optimize import linprog

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/qualified_product_mfa_20261001_v1/measured_precipitate_phase_metal_masses.csv'
AUDIT=ROOT/'results/qualified_product_mfa_20261001_v1/audit_manifest.json'
OUT=ROOT/'results/qualified_blending_20261001_v1'
AW={'Ni':58.6934,'Co':58.933194,'Mn':54.938044}
RATIO={'Ni':.6,'Co':.2,'Mn':.2}
MW=6.94+sum(AW[e]*RATIO[e] for e in AW)+2*15.999

def calc(a,limit,rule,delta=0.):
    elements=['Li','Co','Ni','Mn','Al','Fe','Cu']
    mass=a[[e+'_g' for e in elements]].to_numpy()
    impurities=a[['Al_g','Fe_g','Cu_g']].sum(axis=1).to_numpy()
    clean=mass.sum(axis=1)-impurities
    # Separate relative mass intervals; no assay error distribution is claimed.
    i_hi=(1+delta)*impurities;c_lo=(1-delta)*clean
    q_hi=100*i_hi/(i_hi+c_lo)
    rows=[]
    if rule=='phasewise':
        z=(q_hi<=limit+1e-12).astype(float)
        n=min(float(np.dot(z,a[e+'_g']))*(1-delta)/AW[e]/RATIO[e] for e in AW)
        status='deterministic selection'
    else:
        # z_j<=1 source phase fractions; n is stoichiometric NMC622 mol upper
        # bound after adding external Li/O and before synthesis losses.
        quality=np.r_[(1-limit/100)*i_hi-limit/100*c_lo,0.]
        A=[quality];b=[0.]
        for e in AW:
            A.append(np.r_[-(1-delta)*a[e+'_g'].to_numpy()/AW[e],RATIO[e]])
            b.append(0.)
        res=linprog(np.r_[np.zeros(len(a)),-1.],A_ub=np.asarray(A),b_ub=b,
                    bounds=[(0,1)]*len(a)+[(0,None)],method='highs')
        assert res.success,res.message
        z=res.x[:-1];n=res.x[-1];status=res.message
        assert max(np.asarray(A)@res.x-np.asarray(b))<1e-9
    used=z@mass;den=float(used.sum());impurity=100*sum(used[4:])/den if den>0 else 0.
    nominal_n=min(float(used[elements.index(e)])/AW[e]/RATIO[e] for e in AW)
    assert n<=nominal_n+1e-9
    output={'quality_limit_pct':limit,'selection_rule':rule,'relative_mass_interval':delta,
            'tm_stoichiometric_CAM_upper_bound_g':n*MW,'nominal_tm_CAM_upper_bound_g':nominal_n*MW,
            'selected_precipitate_g':float(z@a.collected_precipitate_g.to_numpy()),
            'nominal_blend_impurity_pct':impurity,
            'worst_interval_blend_impurity_pct':float(100*np.dot(z,i_hi)/(np.dot(z,i_hi+c_lo))) if den>0 else 0.,
            'source_phase_fractions':json.dumps(dict(zip(a.phase_label,z))),
            'qualified_Ni_g':float(used[2]),'qualified_Co_g':float(used[1]),'qualified_Mn_g':float(used[3]),
            'status':status}
    return output

def main():
    OUT.mkdir(parents=True,exist_ok=True);a=pd.read_csv(SOURCE);meta=json.loads(AUDIT.read_text())
    rows=[calc(a,t,r,d) for t in (.1,.2,.3,.4,.5,.6,.64,.65,.7,.8,1.,2.,5.)
          for r in ('phasewise','pooled') for d in (0.,.05,.1,.2)]
    f=pd.DataFrame(rows)
    ref=float(f[(f.quality_limit_pct==.65)&(f.selection_rule=='phasewise')&(f.relative_mass_interval==0)].tm_stoichiometric_CAM_upper_bound_g.iloc[0])
    f['idealized_input_requirement_lower_bound_ratio_to_source_0p65']=np.where(f.tm_stoichiometric_CAM_upper_bound_g>0,ref/f.tm_stoichiometric_CAM_upper_bound_g,np.inf)
    # Yield checks on nominal masses. Recovery denominator includes leaching.
    for e in AW:
        denominator=meta['aliquot_equivalent_original_feed_metals_g'][e]
        f[e+'_original_feed_recovery_pct']=100*f['qualified_'+e+'_g']/denominator
        assert (f[e+'_original_feed_recovery_pct']<=100+1e-8).all()
    f.to_csv(OUT/'grade_blending_frontier.csv',index=False)
    manifest={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'optimization_count':len(rows)//2,'design_count':len(rows),
              'mass_interval_status':'analyst relative intervals, not measured errors or confidence intervals',
              'legacy_column_semantics':{'tm_stoichiometric_CAM_upper_bound_g':'Nominal stoichiometric potential for delta=0; robust minimum stoichiometric potential for delta>0. Not a guaranteed manufactured yield or uniform upper bound over the mass box.', 'qualified_Ni_g':'Nominal Ni in selected grade-admissible inventory, not manufactured qualified NMC622.', 'qualified_Co_g':'Nominal Co in selected inventory.', 'qualified_Mn_g':'Nominal Mn in selected inventory.'},
              'limitation':'Elemental mass blending only. No compatibility/reaction validation, battery performance, synthetic CAM yield, EU product output or environmental credit claimed.',
              'source_phase_count':len(a),'nmc622_molar_mass_g_per_mol':MW}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f[(f.quality_limit_pct.isin([.5,.6,.65]))&(f.relative_mass_interval.isin([0,.1]))].to_string(index=False))

if __name__=='__main__':main()
