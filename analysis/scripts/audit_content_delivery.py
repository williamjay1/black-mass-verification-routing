"""Delivery audit: source/output alignment, extraction and all-page renders."""
from pathlib import Path
import json,re,hashlib
import numpy as np
import pandas as pd
import fitz
from PIL import Image,ImageOps,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa/content_delivery_20261001_v1'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'main_content_v13.tex').read_text(encoding='utf-8')
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
    for item,printed in zip(stats['joint_boundary_10t_0p6'],['0.07683','0.06915','0.69337','0.57598']):
        chk('joint qualification-capacity index',item['certified_throughput_TM_potential_index'],printed,'joint_capacity_qualification_boundary.csv')
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
    pd.DataFrame(trace).to_csv(OUT/'numeric_claim_trace.csv',index=False)
    for name in ('main_content_v13','supplement_content_v13'):
        pdf=ROOT/'output/pdf'/f'{name}.pdf'
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
