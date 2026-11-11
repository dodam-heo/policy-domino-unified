import io
import unittest
import zipfile
from unified.annex_clauses import recover

def hwpx(prose,amount='100'):
    xml='<s xmlns:h="urn:h"><h:p><h:t>'+prose+'</h:t><h:tbl><h:tr><h:tc><h:p><h:t>금액</h:t></h:p></h:tc><h:tc><h:p><h:t>'+amount+'</h:t></h:p></h:tc></h:tr></h:tbl><h:t>이 기준을 적용한다.</h:t></h:p></s>'
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z: z.writestr('Contents/section0.xml',xml)
    return buf.getvalue()

class RecoveryTests(unittest.TestCase):
    def test_matching_article_recovers_image_table(self):
        text='제2조(소득) 다음 표에 따른다. <img id="3"></img> 이 기준을 적용한다.'
        out=recover({'제2조':text},['제2조'],hwpx('제2조(소득) 다음 표에 따른다.'))
        self.assertIn('금액 | 100',out['제2조'])
    def test_same_article_with_different_prose_is_not_evidence(self):
        text='제2조(소득) 다음 표에 따른다. <img id="3"></img> 이 기준을 적용한다.'
        self.assertEqual(recover({'제2조':text},['제2조'],hwpx('제2조(소득) 다른 기준이다.')), {})
    def test_missing_second_image_is_not_complete(self):
        text='제2조(소득) 다음 표에 따른다. <img id="3"></img><img id="4"></img> 이 기준을 적용한다.'
        self.assertEqual(recover({'제2조':text},['제2조'],hwpx('제2조(소득) 다음 표에 따른다.')), {})
