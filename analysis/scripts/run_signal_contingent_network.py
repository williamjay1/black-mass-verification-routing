"""Non-oracle verification/route design; explicit scenario, not EU forecasting.

All dispatch fractions depend on an observable assay outcome, never on the
latent compatibility state/profile. Scenario probabilities are conditional
operating-characteristic arithmetic; profile probabilities are NOT estimated.
The robust model minimises the largest scenario cost and then, within the
certified cost tolerance, minimises reserved input-equivalent capacity blocks.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import platform
import numpy as np
import pandas as pd
import scipy
from scipy.optimize import milp, Bounds, LinearConstraint,brentq
from scipy.sparse import coo_matrix
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/futuram_network_inputs_20260930_v1"
OUT = ROOT / "results/signal_contingent_20261001_v1"
REGISTRY = ROOT.parent / "datasets/upgrade/route_parameter_registry_2026-09-26.csv"
ROUTES = ("D", "H", "P")

@dataclass(frozen=True)
class Config:
    year: int = 2030
    policy: str = "confirmation"
    p_low: float = .2
    p_high: float = .8
    risk_cap: float = .1
    screen_s: float = .86
    screen_f: float = .15
    confirm_s: float = .95
    confirm_f: float = .02
    screen_fee: float = 150.
    confirm_fee: float = 450.
    bad_error_dependence: float = 0.
    conservative_joint_s: bool = False
    sunk_cost_fraction: float = 1.
    failed_direct_capacity_fraction: float = 1.
    fallback_cost_multiplier: float = 1.
    distance_multiplier: float = 1.
    transport_per_tkm: float = .5
    max_hubs: int = 5
    block_tpy: float = 1000.
    blocks_per_route_site: int = 100
    force_hydro: bool = False
    oracle_dispatch: bool = False
    maximum_independent_lot_t: float = 0.
    network_overflow_budget: float = .1
    incremental_reservation_premium_per_tpy: float = 0.

def certified_capacity_fraction(block:float,lot:float,budget:float,constraints:int):
    """Conservative Bernstein inner approximation, conditional independent lots.

    For load contributions in[0,b], Var(sum)<=b*mean. Requiring the
    one-block Bernstein tail bound <=budget/constraints suffices for any
    integer number of blocks because the exponent grows with block count.
    This certifies stochastic overflow, not direct-product compatibility.
    """
    if lot==0:return 1.
    if lot<=0 or not 0<budget<1:raise ValueError('invalid capacity reliability parameters')
    ell=np.log(constraints/budget)
    def margin(k):
        mu=k*block;t=(1-k)*block
        return t*t-ell*(2*lot*mu+2*lot*t/3)
    if margin(0)<0:return 0.
    return float(brentq(margin,0.,1.))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def signals(p: float, c: Config):
    """Good/bad JOINT masses per input, plus full-feed assay cost."""
    if c.policy == "none":
        return ["untested"], np.array([p]), np.array([1-p]), 0.
    if c.policy in ("screen", "confirmation", "perfect"):
        s, f, fee = {"screen":(c.screen_s,c.screen_f,c.screen_fee),
                     "confirmation":(c.confirm_s,c.confirm_f,c.confirm_fee),
                     "perfect":(1.,0.,c.confirm_fee)}[c.policy]
        return ["positive","negative"], np.array([p*s,p*(1-s)]), np.array([(1-p)*f,(1-p)*(1-f)]),fee
    if c.policy == "cascade":
        # Fréchet admissible positive-error dependence, not two independent
        # copies of a measured detector. Good joint lower bound is optional.
        s_joint = max(0.,c.screen_s+c.confirm_s-1.) if c.conservative_joint_s else c.screen_s*c.confirm_s
        f0 = c.screen_f*c.confirm_f
        f_joint = f0+c.bad_error_dependence*(min(c.screen_f,c.confirm_f)-f0)
        assert max(0.,c.screen_f+c.confirm_f-1.) <= f_joint <= min(c.screen_f,c.confirm_f)+1e-12
        g = p*np.array([s_joint,c.screen_s-s_joint,1-c.screen_s])
        b = (1-p)*np.array([f_joint,c.screen_f-f_joint,1-c.screen_f])
        fee = c.screen_fee+c.confirm_fee*(p*c.screen_s+(1-p)*c.screen_f)
        return ["both_positive","screen_positive_confirm_negative","screen_negative"],g,b,fee
    raise ValueError(c.policy)

class Rows:
    def __init__(self):
        self.i=[]; self.j=[]; self.a=[]; self.lo=[]; self.hi=[]
    def add(self, terms, lo=-np.inf, hi=np.inf):
        r=len(self.lo)
        for j,a in terms:
            if a:
                self.i.append(r);self.j.append(j);self.a.append(float(a))
        self.lo.append(lo);self.hi.append(hi)
    def build(self,n):
        a=coo_matrix((self.a,(self.i,self.j)),shape=(len(self.lo),n)).tocsc()
        return LinearConstraint(a,np.array(self.lo),np.array(self.hi))

def solve(c: Config, limit: float=60.):
    origins=pd.read_csv(DATA/f"national_origins_{c.year}.csv").sort_values("origin_id").reset_index(drop=True)
    hubs=pd.read_csv(DATA/"candidate_hubs.csv").sort_values("hub_id").reset_index(drop=True)
    dist=pd.read_csv(DATA/"national_origin_hub_geodesic_matrix.csv")
    d=dist.pivot(index="origin_id",columns="hub_id",values="distance_km").loc[origins.origin_id,hubs.hub_id].to_numpy()*c.distance_multiplier
    supply=origins.reference_black_mass_tpy.to_numpy()
    n,h=len(origins),len(hubs)
    # An untested all-hydro policy has deterministic route loads conditional
    # on the fixed annual workload; assay-error safety derating is inapplicable.
    capacity_fraction=1. if c.policy=='none' else certified_capacity_fraction(c.block_tpy,c.maximum_independent_lot_t,c.network_overflow_budget,3*h)
    if capacity_fraction<=0:raise ValueError('one-block approximation cannot certify selected lot/risk; change block size or exact model')
    ps=sorted(set([c.p_low,(c.p_low+c.p_high)/2,c.p_high]))
    packs=[signals(p,c) for p in ps]
    labels=packs[0][0];o=len(labels);w=len(ps)
    gs=np.stack([x[1] for x in packs]);bs=np.stack([x[2] for x in packs]);pis=gs+bs
    assert np.allclose(pis.sum(axis=1),1.) and (pis>=-1e-12).all()
    with np.errstate(divide="ignore",invalid="ignore"):
        risks=np.where(pis>0,bs/pis,1.)
    safe=(risks.max(axis=0)<=c.risk_cap+1e-12) & (pis.min(axis=0)>0)
    reg=pd.read_csv(REGISTRY);v=dict(zip(reg.parameter_id,reg.value))
    cost=np.array([v['allen_direct_total_cost'],v['allen_hydro_total_cost'],v['allen_pyro_total_cost']],float)*1000
    # All variables shared across latent profiles unless an explicitly
    # nonimplementable perfect-state dispatch lower bound is requested.
    npol=w if c.oracle_dispatch else 1
    size=npol*o*n*h*3
    x=np.arange(size).reshape(npol,o,n,h,3)
    y=np.arange(size,size+h)
    k=np.arange(size+h,size+h+3*h).reshape(h,3)
    z=size+4*h;nv=z+1
    lb=np.zeros(nv);ub=np.full(nv,np.inf);integrality=np.zeros(nv,int)
    ub[y]=1;integrality[y]=1
    ub[k]=c.blocks_per_route_site;integrality[k]=1
    for a in range(o):
        if c.force_hydro or not safe[a]: ub[x[:,a,:,:,0].ravel()]=0
        if c.force_hydro: ub[x[:,a,:,:,2].ravel()]=0
    rows=Rows()
    for policy in range(npol):
        for a in range(o):
            for r in range(n):rows.add([(int(i),1) for i in x[policy,a,r].ravel()],lo=supply[r],hi=supply[r])
    for j in range(h):
        for route in range(3):rows.add([(int(k[j,route]),1),(int(y[j]),-c.blocks_per_route_site)],hi=0)
    rows.add([(int(j),1) for j in y],hi=c.max_hubs)
    scenario_vectors=[];assay_costs=[]
    for iw,p in enumerate(ps):
        ix=iw if c.oracle_dispatch else 0
        vec=np.zeros(nv)
        for a in range(o):
            pi,g,b=pis[iw,a],gs[iw,a],bs[iw,a]
            coefficients=[g*cost[0]+b*(c.sunk_cost_fraction*cost[0]+c.fallback_cost_multiplier*cost[2]),pi*cost[1],pi*cost[2]]
            for r in range(n):
                for j in range(h):
                    for route in range(3):vec[x[ix,a,r,j,route]]=coefficients[route]+pi*d[r,j]*c.transport_per_tkm
        fee=packs[iw][3]*supply.sum()
        terms=[(int(i),vec[i]/1e6) for i in np.flatnonzero(vec)]
        terms.append((z,-1.));rows.add(terms,hi=-fee/1e6)
        scenario_vectors.append(vec);assay_costs.append(fee)
        for j in range(h):
            for route in range(3):
                terms=[(int(k[j,route]),-c.block_tpy*capacity_fraction)]
                for a in range(o):
                    direct_load=gs[iw,a]+c.failed_direct_capacity_fraction*bs[iw,a]
                    coeff=direct_load if route==0 else pis[iw,a]
                    terms.extend((int(x[ix,a,r,j,route]),coeff) for r in range(n))
                    if route==2:terms.extend((int(x[ix,a,r,j,0]),bs[iw,a]) for r in range(n))
                rows.add(terms,hi=0.)
    objective=np.zeros(nv);objective[z]=1.
    objective[k.ravel()]=c.incremental_reservation_premium_per_tpy*c.block_tpy/1e6
    result=milp(objective,integrality=integrality,bounds=Bounds(lb,ub),constraints=rows.build(nv),options={"time_limit":limit,"mip_rel_gap":1e-7})
    if result.x is None: return {"config":asdict(c),"status":"no_incumbent","solver_status":int(result.status),"message":result.message}
    primary_bound=float(result.mip_dual_bound);primary_gap=float(result.mip_gap);primary_upper=float(result.fun)
    # Cost first; spare block minimisation is a decision-resolution tie break,
    # not an inferred capital cost or profitability estimate.
    tol=1e-5
    rows.add([(int(i),objective[i]) for i in np.flatnonzero(objective)],hi=primary_upper+tol)
    obj2=np.zeros(nv);obj2[k.ravel()]=1.;obj2[y]=.001
    second=milp(obj2,integrality=integrality,bounds=Bounds(lb,ub),constraints=rows.build(nv),options={"time_limit":limit,"mip_rel_gap":1e-6})
    sol=second.x if second.x is not None else result.x
    residual=rows.build(nv).A @ sol
    lo=np.array(rows.lo);hi=np.array(rows.hi)
    max_violation=float(max(0.,np.max(lo-residual),np.max(residual-hi),np.max(lb-sol),np.max(sol-ub)))
    scenarios=[]
    reservation_premium=float(sol[k].sum()*c.block_tpy*c.incremental_reservation_premium_per_tpy)
    for iw,p in enumerate(ps):
        ix=iw if c.oracle_dispatch else 0
        xx=sol[x[ix]]
        admitted=float(sum(pis[iw,a]*xx[a,:,:,0].sum() for a in range(o)))
        good=float(sum(gs[iw,a]*xx[a,:,:,0].sum() for a in range(o)))
        failed=float(sum(bs[iw,a]*xx[a,:,:,0].sum() for a in range(o)))
        hydro=float(sum(pis[iw,a]*xx[a,:,:,1].sum() for a in range(o)))
        pyro=float(sum(pis[iw,a]*xx[a,:,:,2].sum() for a in range(o)))
        transported=float(sum(pis[iw,a]*np.sum(xx[a]*d[:,:,None]) for a in range(o)))
        total=float(scenario_vectors[iw]@sol+assay_costs[iw]+reservation_premium)
        assert abs(good+failed+hydro+pyro-supply.sum())<1e-4
        assert abs(admitted-good-failed)<1e-4
        scenarios.append({"p_compatible":p,"total_cost_model_usd":total,"assay_cost_model_usd":assay_costs[iw],
                          "incremental_reservation_premium_model_usd":reservation_premium,
                          "transport_tkm":transported,"direct_admitted_t":admitted,"direct_compatible_t":good,
                          "false_positive_fallback_t":failed,"hydro_primary_t":hydro,"pyro_primary_t":pyro,
                          "unique_input_t":float(supply.sum()),"total_terminal_input_equivalent_t":good+hydro+pyro+failed,
                          "total_process_input_equivalent_t":good+c.failed_direct_capacity_fraction*failed+hydro+pyro+failed})
    cap=[{"hub_id":hubs.hub_id[j],"city":hubs.city[j],"route":ROUTES[r],"blocks":int(round(sol[k[j,r]])),"capacity_tpy":round(sol[k[j,r]])*c.block_tpy} for j in range(h) for r in range(3) if sol[k[j,r]]>.5]
    policy_flows=[{"profile_index":ip if c.oracle_dispatch else None,"signal":labels[a],"origin_id":origins.origin_id[r],
                   "hub_id":hubs.hub_id[j],"route":ROUTES[route],"nominal_if_all_input_had_signal_t":float(sol[x[ip,a,r,j,route]])}
                  for ip in range(npol) for a in range(o) for r in range(n) for j in range(h) for route in range(3) if sol[x[ip,a,r,j,route]]>1e-7]
    return {"config":asdict(c),"status":"computed","primary_optimal":bool(result.status==0),"primary_solver_status":int(result.status),
            "worst_cost_model_usd":max(s["total_cost_model_usd"] for s in scenarios),"primary_lower_bound_model_usd":primary_bound*1e6,
            "primary_mip_gap":primary_gap,"decision_cost_tolerance_model_usd":tol*1e6,
            "capacity_tie_break_status":int(second.status),"capacity_tie_break_gap":float(second.mip_gap) if second.x is not None else None,
            "max_constraint_violation":max_violation,"signal_labels":labels,"posterior_risk_by_profile":risks.tolist(),
            "direct_eligible_signals":safe.tolist(),"scenarios":scenarios,"capacity":cap,
            "active_hubs":[str(hubs.hub_id[j]) for j in range(h) if sol[y[j]]>.5],"signal_contingent_nominal_policy_flows":policy_flows,
            "certified_mean_capacity_fraction":capacity_fraction,
            "policy_invariance":"one dispatch tensor shared across profiles" if not c.oracle_dispatch else "nonimplementable latent-profile oracle benchmark"}

def frontiers():
    # Designed parameter coverage, not an estimated European prevalence.
    rows=[]
    for p in (.05,.1,.2,.3,.5,.8,.95):
        for rho in (.01,.05,.1,.2):
            for s in (.8,.86,.95,.99):
                specificity=1-rho*p*s/((1-rho)*(1-p))
                rows.append({"p_compatible_scenario":p,"risk_cap":rho,"sensitivity_scenario":s,"minimum_specificity":max(0.,specificity)})
    pd.DataFrame(rows).to_csv(OUT/"reliability_frontier.csv",index=False)
    v=pd.read_csv(REGISTRY);cost=dict(zip(v.parameter_id,v.value))
    cd=float(cost['allen_direct_total_cost'])*1000;ch=float(cost['allen_hydro_total_cost'])*1000;cp=float(cost['allen_pyro_total_cost'])*1000
    rows=[]
    for p in np.linspace(.05,.95,91):
        for eta in (0.,.25,.5,.75,1.):
            s=.86*.95; f=.15*.02+eta*(.02-.15*.02)
            # Confirmation fee threshold where cascade and full confirmation
            # have equal expected routing cost; direct-enabled domains only.
            saving_in_confirm_volume=1-(p*.86+(1-p)*.15)
            delta_process=p*(.95-s)*(ch-cd)+(1-p)*(f-.02)*(cd+cp-ch)
            fee_threshold=(150+delta_process)/saving_in_confirm_volume
            q=(1-p)*f/(p*s+(1-p)*f)
            rows.append({"p_compatible_scenario":p,"bad_error_dependence":eta,"cascade_q":q,"confirmation_fee_break_even_usd_per_t":fee_threshold,
                         "cascade_joint_sensitivity":s,"cascade_joint_false_positive_rate":f})
    pd.DataFrame(rows).to_csv(OUT/"cascade_break_even_frontier.csv",index=False)
    # Transparent exploratory uniform hypercube; no source-estimated prior.
    u=qmc.Sobol(d=7,scramble=True,seed=3401).random_base2(14)
    p=.05+.9*u[:,0];s=.8+.19*u[:,1];f=.002+.198*u[:,2];fee=100+1400*u[:,3]
    alpha=u[:,4];dscale=.7+.6*u[:,5];pscale=.7+.6*u[:,6]
    pi=p*s+(1-p)*f;q=(1-p)*f/pi
    good=p*s;bad=(1-p)*f
    net=good*(ch-cd*dscale)-bad*(alpha*cd*dscale+cp*pscale-ch)-fee
    a=pd.DataFrame({"p":p,"s":s,"f":f,"fee":fee,"alpha":alpha,"direct_cost_scale":dscale,"fallback_cost_scale":pscale,"q":q,
                    "net_value_vs_hydro_usd_per_t":net,"risk_admissible_at_0p1":q<=.1,"cost_beneficial":net>0})
    a.to_csv(OUT/"designed_uncertainty_sobol_16384.csv",index=False)
    return {"designed_sample_count":len(a),"seed":3401,"distribution":"Independent uniform analyst-defined hypercube; not EU empirical probability or confidence interval", "bounds":{"p":[.05,.95],"s":[.8,.99],"f":[.002,.2],"fee":[100,1500],"alpha":[0,1],"direct_cost_scale":[.7,1.3],"fallback_cost_scale":[.7,1.3]},"share_risk_admissible":float((q<=.1).mean()),"share_admissible_and_beneficial":float(((q<=.1)&(net>0)).mean()),"negative_value_given_admissible_share":float((net[q<=.1]<=0).mean())}

def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['smoke','full','frontiers','capacity','premium'],default='smoke');parser.add_argument('--limit',type=float,default=60)
    parser.add_argument('--output-tag',default='signal_contingent_20261001_v1')
    args=parser.parse_args();assert '/' not in args.output_tag and '\\' not in args.output_tag
    OUT=ROOT/'results'/args.output_tag;OUT.mkdir(parents=True,exist_ok=True)
    exploratory=frontiers()
    specs=[Config(policy='none',force_hydro=True),Config(policy='screen'),Config(policy='confirmation'),Config(policy='cascade'),Config(policy='perfect')]
    if args.mode=='capacity':
        specs=[Config(policy=p,maximum_independent_lot_t=b) for b in (1.,10.,50.) for p in ('none','confirmation','cascade')]
    if args.mode=='premium':
        specs=[Config(policy=p,maximum_independent_lot_t=b,incremental_reservation_premium_per_tpy=a)
               for b in (0.,10.) for a in (0.,250.,500.) for p in ('none','confirmation','cascade')]
    if args.mode=='full':
        specs.extend([Config(policy='cascade',bad_error_dependence=e,conservative_joint_s=True) for e in (.5,1.)])
        specs.extend([Config(policy=p,risk_cap=.05) for p in ('confirmation','cascade')])
        specs.extend([Config(policy=p,confirm_fee=1000) for p in ('confirmation','cascade')])
        specs.extend([Config(policy='confirmation',sunk_cost_fraction=a) for a in (0.,.5)])
        specs.extend([Config(policy='confirmation',failed_direct_capacity_fraction=l) for l in (0.,.5)])
        specs.extend([Config(policy='confirmation',distance_multiplier=m) for m in (1.3,1.6)])
        specs.extend([Config(policy='confirmation',year=y) for y in (2025,2035,2040,2050)])
        specs.extend([Config(policy='confirmation',oracle_dispatch=True)])
    results=[]
    if args.mode!='frontiers':
        for i,c in enumerate(specs):
            result=solve(c,args.limit);name=f"run_{i:02d}_{c.year}_{c.policy}.json"
            (OUT/name).write_text(json.dumps(result,indent=2),encoding='utf-8');results.append(result)
            print(json.dumps({"file":name,"status":result['status'],"worst_cost":result.get('worst_cost_model_usd'),"gap":result.get('primary_mip_gap'),"capacity_status":result.get('capacity_tie_break_status')}),flush=True)
        (OUT/f"{args.mode}_all_runs.json").write_text(json.dumps(results,indent=2),encoding='utf-8')
    files=[REGISTRY,DATA/'national_origin_hub_geodesic_matrix.csv',DATA/'candidate_hubs.csv',DATA/'input_manifest.json']
    files.extend(DATA/f"national_origins_{y}.csv" for y in (2025,2030,2035,2040,2050))
    manifest={"generated_utc":datetime.now(timezone.utc).isoformat(),"script_sha256":sha(__file__),"inputs":[{"path":str(p),"sha256":sha(p)} for p in files],
              "python":platform.python_version(),"scipy":scipy.__version__,"run_mode":args.mode,"exploratory_uncertainty":exploratory,
              "source_vs_scenario":"FutuRaM flows are published modeled public data. Costs are source case values. All compatibility fractions, classifier parameters, test fees, block capacities, distance inflation and failure penalties are designed scenarios.",
              "excluded_claims":["validated instrument performance","EU plant prices","empirical compatibility shares","actual capacity investment","ISO comparative LCA","actual qualified CAM output","policy compliance"]}
    (OUT/f"{args.mode}_run_manifest.json").write_text(json.dumps(manifest,indent=2),encoding='utf-8')

if __name__=='__main__':main()
