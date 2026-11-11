import tempfile
import base64
import hashlib
from pathlib import Path
import unittest
from unified.engine import store, relative_path, ident
from unified.relations import (references, legal_dependents,
                               index_program_references, two_hop_program_leads)


class RelationsTests(unittest.TestCase):
    def test_unrelated_clause_must_not_be_borrowed(self):
        cites = references("「첫 법」에 따라서 적용한다. 「다른 법」 제2조에 따라 한다")
        self.assertEqual(len(cites), 1)
        self.assertEqual(cites[0]["title"], "다른 법")

    def test_two_hop_is_candidate_not_proven_action(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prior={"source":"law","stable_id":"100","serial":"1",
                   "title":"상위 법","published_at":"2025-01-01"}
            changed={**prior, "serial":"2","published_at":"2026-01-01"}
            rule={"source":"admrul","stable_id":"200","serial":"3",
                  "title":"하위 지침","published_at":"2025-02-01"}
            store(root/relative_path(rule), {"record":rule,
                "official_xml_base64":base64.b64encode(b"<root/>").decode(),
                "body":{"status":"complete",
                  "raw_xml_sha256":hashlib.sha256(b"<root/>").hexdigest(),
                  "clauses":{"제3조":"「상위 법」 제1조에 따른 기준을 적용한다."}}})
            comparison={"changed_record":changed, "prior_record":prior,
              "status":"changed","changes":[{"clause":"제1조",
              "before":"기준 100원","after":"기준 120원"}]}
            graph=legal_dependents(root,[comparison])
            self.assertEqual(len(graph[ident(changed)]),1)
            self.assertEqual(graph[ident(changed)][0]["verification"],
                             "official_reference_verified")
            program={"id":"p","agency":"실제기관","service_name":"공공사업",
                     "basis":{"행정규칙":"「하위 지침」 제3조에 따른 신청"},
                     "criteria":{"선정기준":"100원"},"url":"https://gov.kr"}
            leads=two_hop_program_leads(changed,comparison,graph[ident(changed)],
                                        index_program_references([program]))
            self.assertEqual(len(leads),1)
            self.assertEqual(leads[0]["agency"],"실제기관")
            self.assertEqual(leads[0]["status"],
                             "program_link_candidate_requires_operational_proof")

    def test_title_similarity_not_an_edge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            doc={"source":"law","stable_id":"10","serial":"1","title":"기준법"}
            rule={"source":"admrul","stable_id":"20","serial":"2","title":"관련 고시"}
            store(root/relative_path(rule),{"record":rule,"body":{"status":"complete",
                "clauses":{"제1조":"기준법과 내용이 비슷하다."}}})
            edges=legal_dependents(root,[{"changed_record":doc,
                "changes":[{"clause":"제1조","before":"A","after":"B"}]}])
            self.assertFalse(edges)
