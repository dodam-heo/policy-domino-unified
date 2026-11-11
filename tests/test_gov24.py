import tempfile
import unittest
from pathlib import Path
from unified.gov24 import Gov24Client, transform, merge_page, collect
from unified.engine import load, hash256


class Gov24Test(unittest.TestCase):
    def test_merge_field_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first={"서비스ID":"A001","서비스명":"실제 공공지원",
                   "소관기관명":"실제공공기관","선정기준":"기준 100원"}
            second={"서비스ID":"A001","법령":"「지원 규정」 제3조",
                    "지원대상":"지원 자격 요건"}
            self.assertEqual(merge_page(root,[first]),1)
            merge_page(root,[second])
            path=root/"programs"/(hash256("A001")[:2]+".json.gz")
            obj=load(path)["records"][0]
            self.assertEqual(obj["agency"],"실제공공기관")
            self.assertIn("제3조",obj["basis"]["법령"])
            self.assertEqual(obj["criteria"]["선정기준"],"기준 100원")

    def test_resume_official_pagination(self):
        seen=[]
        def transport(endpoint,page,size,auth):
            seen.append((endpoint,page))
            return {"totalCount":1,"data":[{
                "서비스ID":"A","서비스명":"공공 지원",
                "소관기관명":"공공기관","법령":"「실제 규정」 제1조",
                "선정기준":"기준"}]}
        with tempfile.TemporaryDirectory() as directory:
            state=collect(Path(directory),Gov24Client("fake",transport),
                          list_pages=1,detail_pages=1)
            self.assertEqual(state["errors"],[])
            self.assertEqual(len(seen),2)


if __name__=="__main__":
    unittest.main()
