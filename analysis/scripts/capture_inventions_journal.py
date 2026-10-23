"""Small official-page evidence capture; original response bytes immutable."""
from pathlib import Path
import datetime, hashlib, json, urllib.request, urllib.error
ROOT=Path(r'F:\AcademicData\topic34\raw\inventions_journal_20261023_v1')
URLS={
 'scope':'https://www.mdpi.com/journal/inventions/about',
 'indexing':'https://www.mdpi.com/journal/inventions/indexing',
 'instructions':'https://www.mdpi.com/journal/inventions/instructions',
 'imprint':'https://www.mdpi.com/journal/inventions/imprint',
 'sample_multiscale':'https://www.mdpi.com/2411-5134/10/6/111',
 'sample_heat_sink':'https://www.mdpi.com/2411-5134/11/5/109',
 'clarivate_issn':'https://mjl.clarivate.com/search-results?issn=2411-5134'}
def main():
 ROOT.mkdir(parents=True,exist_ok=True); manifest=[]
 for key,url in URLS.items():
  dest=ROOT/(key+'.html')
  if dest.exists(): raise FileExistsError(dest)
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (academic journal information verification)'})
  row={'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'reuse':'Public page evidence for journal verification; no blanket redistribution license inferred.'}
  try:
   with urllib.request.urlopen(req,timeout=20) as resp:
    data=resp.read();row['status']=resp.status
   dest.write_bytes(data);dest.chmod(0o444)
   row.update(file=dest.name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
  except Exception as exc: row.update(status='failed',error=str(exc))
  manifest.append(row)
 out=ROOT/'retrieval_manifest.json';out.write_text(json.dumps(manifest,indent=2),encoding='utf-8');out.chmod(0o444)
 print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
