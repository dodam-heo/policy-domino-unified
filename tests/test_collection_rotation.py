import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unified.engine import run, store, load, ident

class RotationTest(unittest.TestCase):
    def test_partial_original_does_not_starve_other_versions(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = [dict(source='admrul', stable_id=str(i), serial=str(i),
                         title='2027년 시험 기준', published_at='2026-10-01',
                         effective_date='2027-01-01') for i in range(1, 5)]
            store(root/'indexes'/'admrul'/'seed.json.gz', {'records': rows})
            class API:
                def __init__(self): self.seen=[]
                def search(self,*a,**kw):
                    return [],dict(reported=0,collected=0,pages=1,complete=True)
                def detail(self,rec):
                    self.seen.append(ident(rec))
                    return '<AdmRulService><조문내용>제1조 &lt;img id="1"&gt;</조문내용></AdmRulService>'.encode()
                def predecessor(self,rec): return None,False
            api=API()
            for _ in range(4):
                run(root,api,limit_streams=1,detail_budget=1,today=dt.date(2026,11,11))
            self.assertEqual(len(set(api.seen)),4)
            state=load(root/'collection-state.json')
            self.assertTrue(all(n==1 for n in state['attempts'].values()))
            self.assertEqual(len(state['last_detail_attempt']),4)
