import unittest
from unified.relations import references, index_program_references
from unified.impact import proof

class GovReferenceTest(unittest.TestCase):
    def test_serialized_basis_and_zero_placeholders(self):
        rows=references('국민기초생활 보장법(제0조의0, 제0항)||국민기초생활 보장법(제8조의0, 제1항)')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['article'],'제8조')
        self.assertEqual(rows[0]['paragraph'],1)
    def test_basis_fields_are_not_concatenated_into_title(self):
        p={'basis':{'법령':'첫째 법(제3조)','행정규칙':'둘째 규칙(제4조)'}}
        idx=index_program_references([p])
        self.assertIn(('첫째법','제3조'),idx)
        self.assertIn(('둘째규칙','제4조'),idx)
    def test_direct_proof_respects_paragraph(self):
        p={'basis':{'법령':'시험법(제3조의0, 제1항)'},'criteria':{'선정기준':'100원'}}
        c={'clause':'제3조','before':'① 100원 ② 200원','after':'① 100원 ② 300원'}
        self.assertIsNone(proof(p,{'title':'시험법'},c))
        c['after']='① 120원 ② 200원'
        self.assertIsNotNone(proof(p,{'title':'시험법'},c))
