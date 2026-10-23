"""Delivery audit: source/output alignment, extraction and all-page renders."""
from pathlib import Path
import json,re,hashlib
import numpy as np
import pandas as pd
import fitz
from scipy.optimize import brentq
from PIL import Image,ImageOps,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa/inventions_delivery_20261023_v1'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'main_inventions_v14.tex').read_text(encoding='utf-8')
    stats=json.loads((ROOT/'results/content_revision_20261001_v1/numerical_claims.json').read_text())
    primary=json.loads((ROOT/'results/signal_contingent_20261001_v1/full_all_runs.json').read_text())
    premium=json.loads((ROOT/'results/signal_reservation_premium_20261001_v1/premium_all_runs.json').read_text())
    strong=json.loads((ROOT/'results/strong_comparators_20261001_v1/strong_comparator_audit.json').read_text())
    table=pd.read_csv(ROOT/'results/content_revision_20261001_v1/network_results.csv')
    cap=pd.read_csv(ROOT/'results/content_revision_20261001_v1/certified_capacity_results.csv')
    trace=[]
    def chk(label,value,printed,locator):
        expected=f'{value:.{len(printed.split(".")[1]) if "." in printed else 0}f}'
        assert expected==printed,(label,value,printed,expected)
        assert printed in source,(label,'absent in source')
        trace.append({'claim':label,'value':float(value),'printed':printed,'source':locator,'pass':True})
    chk('confirmation saving percent',stats['confirmation_saving_pct'],'2.56','numerical_claims.json')
    chk('cascade saving percent',stats['cascade_saving_pct'],'3.54','numerical_claims.json')
    chk('pooled-to-phasewise ratio',stats['pooled_gain_vs_phasewise_0p6'],'9.025','grade_blending_frontier.csv')
    chk('robust matched ratio',stats['robust_pooled_gain_vs_robust_phasewise_0p6_10pct'],'8.330','grade_blending_frontier.csv')
    chk('phase threshold ratio',stats['phasewise_0p65_to_0p6_CAM_ratio'],'8.929','product_grade_recovery_frontier.csv')
    for i,printed in enumerate(['310.889','312.393','302.937','299.896','297.693']):
        chk(f'primary policy{i}million cost',primary[i]['worst_cost_model_usd']/1e6,printed,f'full_all_runs.json[{i}]')
    chk('capacity premium cascade incumbent',premium[17]['worst_cost_model_usd']/1e6,'312.195','premium_all_runs.json[17]')
    chk('premium case MIP gap',premium[17]['primary_mip_gap'],'0.001903','premium_all_runs.json[17]')
    chk('cost contrast modelUSD/t',stats['cascade_extra_saving_per_t_vs_confirmation'],'303.234','numerical_claims.json')
    chk('frozen-design certified saving million',strong['saving_vs_frozen_lower_bound_model_usd']/1e6,'3.202','strong_comparator_audit.json')
    chk('frozen-design saving upper bound million',strong['saving_vs_frozen_upper_bound_model_usd']/1e6,'3.796','strong_comparator_audit.json')
    chk('frozen design cost million',strong['frozen_zero_premium_policy_plus_premium_model_usd']/1e6,'315.396','strong_comparator_audit.json')
    chk('joint objective lower bound million',strong['joint_primary_lower_bound_model_usd']/1e6,'311.601','strong_comparator_audit.json')
    chk('pool increment versus source aggregate percent',strong['pooled_nominal_increment_over_source_aggregate_pct'],'1.072','strong_comparator_audit.json')
    chk('robust recipe nominal potential',strong['robust_10pct_selected_nominal_potential_g'],'2.630335','strong_comparator_audit.json')
    assert '\\label{eq:joint}' not in source
    campaign=ROOT/'results/inventions_campaign_stress_20261023_v2'
    bounds=pd.read_csv(campaign/'certified_handling_limits.csv')
    for policy,b,h,printed in [('confirmation',10,0,'30.978'),('cascade',10,0,'27.303'),('confirmation',50,0,'157.772'),('cascade',50,0,'156.243'),('cascade',10,500,'10.000')]:
        row=bounds.query('policy == @policy and design_lot_t == @b and reservation_premium == @h').iloc[0]
        chk(f'{policy} campaign limit b{b} h{h}',row.maximum_certified_campaign_mass_t,printed,'certified_handling_limits.csv')
    replay=pd.read_csv(campaign/'fixed_policy_campaign_replay.csv')
    assert len(replay)==280 and replay.repetitions.eq(4096).all()
    assert replay[['policy','design_lot_t','reservation_premium','p','campaign_mass_t']].duplicated().sum()==0
    assert replay.repetitions.sum()==1146880
    assert np.allclose(replay.overflow_share,replay.overflow_count/replay.repetitions)
    for policy,printed in [('confirmation','1177'),('cascade','1539')]:
        v=replay.query('policy == @policy and reservation_premium == 500 and campaign_mass_t == 1000').overflow_count.max()
        chk(f'{policy} max 1000t stress count',v,printed,'fixed_policy_campaign_replay.csv')
    for policy,s,f,printed_gate,printed_value in [('confirmation',.95,.02,'0.15929','0.11122'),('cascade',.817,.003,'0.03199','0.04286')]:
        p_gate=.9*f/(.1*s+.9*f)
        fee=(lambda p:450.) if policy=='confirmation' else (lambda p:150+450*(p*.86+(1-p)*.15))
        def net(p):return p*s*(30840-22010)-(1-p)*f*(22010+36000-30840)-fee(p)
        p_value=brentq(net,0.,1.)
        chk(policy+' admission p',p_gate,printed_gate,'independent analytical posterior inversion')
        chk(policy+' economic p',p_value,printed_value,'independent net-benefit root')
    frozen=next(r for r in premium if r['config']['policy']=='cascade' and r['config']['maximum_independent_lot_t']==10 and r['config']['incremental_reservation_premium_per_tpy']==0)
    redesigned=next(r for r in premium if r['config']['policy']=='cascade' and r['config']['maximum_independent_lot_t']==10 and r['config']['incremental_reservation_premium_per_tpy']==500)
    for a,b in zip(frozen['scenarios'],redesigned['scenarios']):
        for key in ('direct_admitted_t','direct_compatible_t','false_positive_fallback_t','hydro_primary_t','pyro_primary_t'):
            assert np.isclose(a[key],b[key],atol=1e-5)
    worst_frozen=max(frozen['scenarios'],key=lambda r:r['total_cost_model_usd'])
    worst_redesigned=max(redesigned['scenarios'],key=lambda r:r['total_cost_model_usd'])
    assert worst_frozen['p_compatible']==worst_redesigned['p_compatible']==.2
    delta_transport=(worst_redesigned['transport_tkm']-worst_frozen['transport_tkm'])*.5
    chk('additional transport million',delta_transport/1e6,'0.298289','premium exported policy transport')
    reservation_saving=(sum(r['capacity_tpy'] for r in frozen['capacity'])-sum(r['capacity_tpy'] for r in redesigned['capacity']))*500
    chk('reservation premium saving million',reservation_saving/1e6,'3.500000','premium exported capacity')
    assert np.isclose(reservation_saving-delta_transport,strong['saving_vs_frozen_lower_bound_model_usd'],atol=1e-3)
    engineering=ROOT/'results/inventions_engineering_baselines_20261023_v1'
    heuristic=pd.read_csv(engineering/'centralized_heuristic_comparison.csv')
    for policy,cost,gap in [('cascade','312.302','0.0342'),('confirmation','316.297','0.2605')]:
        r=heuristic.query('policy == @policy').iloc[0]
        chk(policy+' centralized cost million',r.worst_endpoint_cost_model_usd/1e6,cost,'centralized_heuristic_comparison.csv')
        chk(policy+' centralized gap percent',r.heuristic_gap_to_MILP_incumbent_pct,gap,'centralized_heuristic_comparison.csv')
        assert r.families_evaluated==85561 and r.max_one_block_constraint_violation_t<1e-6
    reblock=pd.read_csv(engineering/'fixed_routing_capacity_reblocking.csv')
    assert len(reblock)==128
    for source_id,caps,cost in [('premium:11',[21750,24500,29000,38000],'314.396'),('premium:17',[19000,20000,22000,26000],'311.195')]:
        q=reblock.query('source_id == @source_id').sort_values('new_block_tpy')
        assert q.feasible_under_block_count_limit.all()
        assert np.allclose(q.new_total_capacity_tpy,caps)
        chk(source_id+' total-capacity certified cost million',q.query('new_block_tpy == 1000').iloc[0].new_worst_cost_h500_model_usd/1e6,cost,'fixed_routing_capacity_reblocking.csv')
    greedy=pd.read_csv(engineering/'product_greedy_52_conditions.csv')
    assert len(greedy)==52 and greedy.match_within_1e_minus7_g.sum()==51
    r=greedy.query('quality_limit_pct == .2 and relative_mass_interval == .2').iloc[0]
    chk('greedy exceptional LP potential',r.LP_minimum_potential_g,'0.281266','product_greedy_52_conditions.csv')
    chk('greedy exceptional simple potential',r.greedy_minimum_potential_g,'0.271097','product_greedy_52_conditions.csv')
    chk('greedy exceptional LP increment percent',r.LP_improvement_over_greedy_pct,'3.75','product_greedy_52_conditions.csv')
    boundary=pd.read_csv(engineering/'source_aggregate_delta_boundaries.csv').query('quality_limit_pct == .6').iloc[0]
    chk('source aggregate delta boundary percent',boundary.largest_admissible_relative_mass_interval*100,'9.1717','source_aggregate_delta_boundaries.csv')
    aggregate=pd.read_csv(engineering/'source_aggregate_52_conditions.csv').query('quality_limit_pct == .6 and relative_mass_interval == .1').iloc[0]
    chk('source aggregate worst impurity percent',aggregate.worst_inventory_impurity_pct,'0.610054','source_aggregate_52_conditions.csv')
    removal=pd.read_csv(engineering/'post_stoichiometry_impurity_removal_requirements.csv').query('recipe == "LP_selected_inventory" and quality_limit_pct == .6 and relative_mass_interval == 0').iloc[0]
    chk('post-surplus retained source-metal impurity percent',removal.post_surplus_removal_impurity_pct,'0.658323','post_stoichiometry_impurity_removal_requirements.csv')
    chk('required impurity removal percent',removal.minimum_impurity_removal_fraction*100,'8.9','post_stoichiometry_impurity_removal_requirements.csv')
    assert max(x['max_constraint_violation'] for x in primary)<7e-11
    assert all(x['primary_optimal'] for x in primary)
    # Manuscript citations must all have actual bibliography entries.
    keys=set(re.findall(r'\\bibitem\{([^}]+)\}',source));uses=set()
    for block in re.findall(r'\\cite\{([^}]+)\}',source):uses.update(block.split(','))
    assert not (uses-keys),uses-keys
    abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',source,re.S).group(1)
    maintext=source.split('\\section{Introduction}',1)[1].split('\\section*{Data and code availability}',1)[0]
    def words(s):
        s=re.sub(r'\\begin\{(?:equation|align|tabular|tabularx)\}.*?\\end\{(?:equation|align|tabular|tabularx)\}',' ',s,flags=re.S)
        s=re.sub(r'\\(?:cite|url|label|ref|includegraphics)(?:\[[^]]*\])?\{[^}]*\}',' ',s)
        s=re.sub(r'\\[a-zA-Z]+',' ',s)
        return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b",s))
    details={'numerical_claim_count':len(trace),'all_numerical_checks_pass':True,
             'abstract_word_count_approximate':words(abstract),'maintext_word_count_approximate':words(maintext),
             'main_figures':source.count('\\begin{figure}'),'main_tables':source.count('\\begin{table}'),
             'bibliography_items':len(keys),'pdf_checks':[]}
    assert words(abstract)<=200,words(abstract)
    assert not re.search(r'Target journal[^\n]*Waste Management|Inventions[^\n]*SCIE',source)
    pd.DataFrame(trace).to_csv(OUT/'numeric_claim_trace.csv',index=False)
    for name in ('main_inventions_v14','supplement_inventions_v14'):
        pdf=ROOT/'output/pdf'/f'{name}.pdf'
        assert pdf.stat().st_mtime >= (ROOT/f'{name}.tex').stat().st_mtime, 'PDF is stale relative to its source'
        doc=fitz.open(pdf);texts=[];pageimages=[];outside=[]
        log=(pdf.with_suffix('.log')).read_text(encoding='utf-8',errors='replace')
        assert 'undefined references' not in log.lower(),name
        assert 'undefined on input line' not in log.lower(),name
        for i,page in enumerate(doc):
            text=page.get_text();texts.append(text)
            assert '\ufffd' not in text and '[?]' not in text,(name,i)
            for b in page.get_text('blocks'):
                if b[6]==0 and (b[0]<15 or b[2]>page.rect.width-15 or b[1]<15 or b[3]>page.rect.height-12):
                    outside.append({'page':i+1,'bbox':b[:4],'text':b[4][:100]})
            pix=page.get_pixmap(matrix=fitz.Matrix(1.15,1.15),alpha=False)
            image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
            imgpath=OUT/f'{name}_page_{i+1:02d}.png';image.save(imgpath);pageimages.append(image)
        (OUT/f'{name}_extracted.txt').write_text('\n\n'.join(texts),encoding='utf-8')
        if name=='main_inventions_v14':
            extracted='\n'.join(texts)
            for row in trace:assert row['printed'] in extracted,(row['claim'],'absent from compiled PDF')
        for start in range(0,len(pageimages),4):
            group=pageimages[start:start+4];w,h=group[0].size
            canvas=Image.new('RGB',(2*w+30,2*h+60),'#dddddd');draw=ImageDraw.Draw(canvas)
            for j,im in enumerate(group):
                x=(j%2)*(w+10)+10;y=(j//2)*(h+20)+20
                canvas.paste(im,(x,y));draw.text((x,y-14),f'{name}: page{start+j+1}',fill='black')
            canvas.save(OUT/f'{name}_contact_{start//4+1:02d}.png')
        details['pdf_checks'].append({'name':name,'pages':len(doc),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                     'extraction_ok':True,'page_boundary_flags':outside,
                                     'font_count':len({x[3] for page in doc for x in page.get_fonts()})})
        doc.close()
    (OUT/'audit_summary.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
    print(json.dumps(details,indent=2))

if __name__=='__main__':main()
