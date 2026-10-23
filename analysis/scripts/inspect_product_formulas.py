from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from extract_tudelft_public_ods import NS,cell_value

p=Path(r'D:\MLWork\topic34\manuscript_quality_v2\datasets\work_tudelft_58947_20260930\publication_files\Data for publication\Electrochemical and precipitation data pH 4 (Table 3 and Fig 6).ods')
with zipfile.ZipFile(p) as f:root=ET.fromstring(f.read('content.xml'))
sheet=[s for s in root.findall('.//table:table',NS) if s.get('{'+NS['table']+'}name','').lower().startswith('leaching')][0]
row_number=0
cells={}
for row in sheet.findall('table:table-row',NS):
    repeat=int(row.get('{'+NS['table']+'}number-rows-repeated','1'))
    col=0
    for cell in list(row):
        n=int(cell.get('{'+NS['table']+'}number-columns-repeated','1'))
        val=cell_value(cell);formula=cell.get('{'+NS['table']+'}formula')
        if val or formula:
            for r in range(min(repeat,1000)):
                cells[(row_number+r+1,col+1)]={'value':val,'formula':formula}
        col+=n
    row_number+=repeat
for rr in (95,96,97,159,160,161,257,258,259,293,294):
    print('REFERENCE',rr,{cc:cells[(rr,cc)] for cc in range(1,19) if (rr,cc) in cells})
for (r,c),item in cells.items():
    if item['value']=='Yield Co' or item['value'].startswith('48.294755') or item['value'].startswith('47.924995') or item['value'].startswith('53.978388'):
        print(r,c,item)
        # Report all nearby cells and their formulas.
        for rr in range(max(1,r-1),r+3):
            print(rr,{cc:cells[(rr,cc)] for cc in range(1,8) if (rr,cc) in cells})
