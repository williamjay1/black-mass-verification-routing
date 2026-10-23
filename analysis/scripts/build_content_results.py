"""Numerical manuscript exports, exclusively from recorded computations."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/content_revision_20261001_v1'
FIG=ROOT/'figures/content_v13'

def inventory(run):
    return {r:sum(x['capacity_tpy'] for x in run['capacity'] if x['route']==r) for r in ('D','H','P')}

def main():
    OUT.mkdir(parents=True,exist_ok=True);FIG.mkdir(parents=True,exist_ok=True)
    runs=json.loads((ROOT/'results/signal_contingent_20261001_v1/full_all_runs.json').read_text())
    base=runs[0]['worst_cost_model_usd'];rows=[]
    for i,r in enumerate(runs):
        rows.append({'run_id':i,**r['config'],'worst_cost_model_usd':r['worst_cost_model_usd'],
                     'saving_vs_2030_all_hydro_pct':100*(base-r['worst_cost_model_usd'])/base,
                     **{k+'_capacity_tpy':v for k,v in inventory(r).items()},
                     'max_constraint_violation':r['max_constraint_violation'],'primary_mip_gap':r['primary_mip_gap']})
    net=pd.DataFrame(rows);net.to_csv(OUT/'network_results.csv',index=False)
    cap=json.loads((ROOT/'results/signal_capacity_20261001_v4/capacity_all_runs.json').read_text())
    caps=pd.DataFrame([{'policy':r['config']['policy'],'lot_t':r['config']['maximum_independent_lot_t'],
                       'kappa':r['certified_mean_capacity_fraction'],**inventory(r),
                       'total_tpy':sum(inventory(r).values())} for r in cap])
    caps.to_csv(OUT/'certified_capacity_results.csv',index=False)
    blend=pd.read_csv(ROOT/'results/qualified_blending_20261001_v1/grade_blending_frontier.csv')
    chosen=blend[(blend.quality_limit_pct.isin([.5,.6,.65]))&(blend.relative_mass_interval.isin([0.,.1]))].copy()
    chosen.to_csv(OUT/'qualified_product_results.csv',index=False)
    sim=pd.read_csv(ROOT/'results/capacity_verification_20261001_v1/conditional_lot_overflow_checks.csv')
    recovery=json.loads((ROOT/'results/qualified_product_mfa_20261001_v1/audit_manifest.json').read_text())
    inputs=ROOT/'datasets/futuram_network_inputs_20260930_v1'
    flow=[]
    for y in (2025,2030,2035,2040,2050):
        f=pd.read_csv(inputs/f'national_origins_{y}.csv')
        flow.append({'year':y,'cell_waste_tpy':f.bev_lithium_battery_waste_t.sum(),'reference_BM_tpy':f.reference_black_mass_tpy.sum()})
    flows=pd.DataFrame(flow);flows.to_csv(OUT/'annual_reference_flows.csv',index=False)
    def cam(t,rule,d=0):return float(blend[(blend.quality_limit_pct==t)&(blend.selection_rule==rule)&(blend.relative_mass_interval==d)].tm_stoichiometric_CAM_upper_bound_g.iloc[0])
    # Matched-source repetition diagnostic: one-block certified throughput
    # multiplied by the source TM potential, normalized to the nominal0.65%
    # phasewise case. It is not measured CAM or a transferable EU yield.
    ref_cam=cam(.65,'phasewise')
    joint=[]
    for b in (1.,10.,50.):
        kappa=float(caps[(caps.policy=='confirmation')&(caps.lot_t==b)].kappa.iloc[0])
        for t in (.5,.6,.65):
            for rule in ('phasewise','pooled'):
                for delta in (0.,.1):
                    beta=cam(t,rule,delta)/ref_cam
                    joint.append({'maximum_lot_t':b,'kappa':kappa,'quality_limit_pct':t,
                                  'rule':rule,'relative_mass_interval':delta,
                                  'normalized_TM_potential_per_input':beta,
                                  'certified_throughput_TM_potential_index':kappa*beta})
    pd.DataFrame(joint).to_csv(OUT/'joint_capacity_qualification_boundary.csv',index=False)
    summary={'source_grade_audit':recovery,'annual_flow_results':flow,
             'confirmation_saving_pct':net.iloc[2].saving_vs_2030_all_hydro_pct,
             'cascade_saving_pct':net.iloc[3].saving_vs_2030_all_hydro_pct,
             'cascade_extra_saving_per_t_vs_confirmation':(runs[2]['worst_cost_model_usd']-runs[3]['worst_cost_model_usd'])/flow[1]['reference_BM_tpy'],
             'phasewise_0p65_to_0p6_CAM_ratio':cam(.65,'phasewise')/cam(.6,'phasewise'),
             'pooled_gain_vs_phasewise_0p6':cam(.6,'pooled')/cam(.6,'phasewise'),
             'robust_pooled_gain_vs_robust_phasewise_0p6_10pct':cam(.6,'pooled',.1)/cam(.6,'phasewise',.1),
             'joint_boundary_10t_0p6': [x for x in joint if x['maximum_lot_t']==10 and x['quality_limit_pct']==.6],
             'simulation_max_overflow_mean_only':float(sim[sim.design_capacity_lot_t==0].sample_overflow_share.max()),
             'simulation_max_overflow_certified':float(sim[sim.design_capacity_lot_t==10].sample_overflow_share.max()),
             'verification_role':'solver/numerical/conditional probability checks, not empirical calibration'}
    (OUT/'numerical_claims.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axs=plt.subplots(1,2,figsize=(9,3.4))
    for rho in (.05,.1):
        p=np.linspace(.02,.9,400);sp=np.maximum(0,1-rho*p*.95/((1-rho)*(1-p)))
        axs[0].plot(p,sp,label=f'Mismatch guardrail {rho:.0%}')
    axs[0].set(xlabel='Compatible share p (design condition)',ylabel='Minimum specificity',ylim=(.65,1.003));axs[0].legend(frameon=False)
    front=pd.read_csv(ROOT/'results/signal_contingent_20261001_v1/cascade_break_even_frontier.csv')
    for eta in (0.,.5,1.):
        d=front[front.bad_error_dependence==eta]
        axs[1].plot(d.p_compatible_scenario,d.confirmation_fee_break_even_usd_per_t,label=f'Error dependence {eta:g}')
    axs[1].set(xlabel='Compatible share p (design condition)',ylabel='Confirmation fee break-even\n(model USD/t)');axs[1].legend(frameon=False)
    fig.tight_layout();fig.savefig(FIG/'verification_frontiers.pdf');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(9,3.4));labels=['Untested H','Screen','Confirm','Cascade','Perfect']
    axs[0].bar(labels,net.iloc[:5].worst_cost_model_usd/flow[1]['reference_BM_tpy']/1000,color=['.55','#b98350','#507d94','#328a69','#897dae'])
    axs[0].set(ylabel='Worst-profile pathway cost\n(thousand model USD/t)',ylim=(28.8,31.5));axs[0].tick_params(axis='x',rotation=25)
    xx=np.arange(3);w=.25
    for i,pol in enumerate(('none','confirmation','cascade')):
        df=caps[caps.policy==pol].sort_values('lot_t')
        axs[1].bar(xx+(i-1)*w,df.total_tpy/1000,w,label={'none':'Untested H','confirmation':'Confirm','cascade':'Cascade'}[pol])
    axs[1].set(xticks=xx,xticklabels=['1','10','50'],xlabel='Maximum independent lot (t)',ylabel='Reserved input-equivalent capacity\n(thousand t/y)');axs[1].legend(frameon=False)
    fig.tight_layout();fig.savefig(FIG/'policy_capacity.pdf');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(9,3.4))
    for rule,style in [('phasewise','--'),('pooled','-')]:
        for d,color in [(0.,'#507d94'),(.1,'#b98350')]:
            df=blend[(blend.selection_rule==rule)&(blend.relative_mass_interval==d)&(blend.quality_limit_pct<=1)]
            axs[0].plot(df.quality_limit_pct,df.tm_stoichiometric_CAM_upper_bound_g,style,color=color,marker='o',markersize=3,label=f'{rule}, interval {d:.0%}')
    axs[0].set(xlabel='Al+Fe+Cu limit on all-metal basis (%)',ylabel='TM-based NMC622 potential\n(g per source aliquot)');axs[0].legend(frameon=False,fontsize=8)
    for rule,color in [('phasewise','#507d94'),('pooled','#328a69')]:
        df=blend[(blend.selection_rule==rule)&(blend.quality_limit_pct==.6)]
        axs[1].plot(df.relative_mass_interval*100,df.tm_stoichiometric_CAM_upper_bound_g,label=rule,color=color,marker='o')
    axs[1].set(xlabel='Declared relative mass interval (%)',ylabel='Minimum TM-based potential\n(g per source aliquot)');axs[1].legend(frameon=False)
    fig.tight_layout();fig.savefig(FIG/'qualified_recovery_frontier.pdf');plt.close(fig)
    print(json.dumps(summary,indent=2));print(caps.to_string(index=False))

if __name__=='__main__':main()
