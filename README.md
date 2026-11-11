# Policy Domino Unified — 감사·통합 엔진 작업 저장소

**실제 목표:** 상위 정책의 제·개정이 공공기관의 어떤 사업·업무·서비스·시스템 기준을 어떻게 변경하는지, 공식 원문과 검증 가능한 연결 근거로 설명합니다.

## 실행 순서
1. `audit`: 과거 v2 백업, 현재 v4, NEXT 공식 문서 원장 전수 대조. 기존 두 저장소는 읽기만 하며 수정하지 않습니다.
2. `ingest`: 3개 자료 원천(law/admrul/ordin)과 현행·연혁의 **독립 수집**. 날짜 범위/종류별 완결성 기록 및 실패 구간 재시도.
3. `compare`: 동일 공식 문서의 연속 판본 또는 연도별 후속 고시를 **원문·별표·첨부 기준**으로 비교. 확인하지 않은 수치는 바뀌었다고 쓰지 않습니다.
4. `impact`: 실제 공공기관·공공서비스 문서와 변경된 조문·기준의 연결을 증명한 뒤 기관별 업무·사업 후속조치를 작성. 문서명 유사성만으로 연결 금지.

## 감사 데이터 기준 (고정 참조)
- `dodam-heo/policy-domino@backup-before-20261109-impact-restore:data/v2_state.json`
- `dodam-heo/policy-domino@main:data/v4_state.json` (실행 시 SHA 기록)
- `dodam-heo/policy-domino-next@main:data/state.json` (실행 시 SHA 기록)

`Audit legacy sources` Actions는 위 공개 저장소를 **별도 디렉터리에 checkout**하여 읽기만 합니다. 저장소 내에 230MB+ 원천 JSON을 복제하지 않습니다. 결과는 Actions artifact로 제공되며 누락·충돌·재사용 가능 자료를 별도 집계합니다. 원문이 불완전하면 완전하다고 판정하지 않습니다.

### 주의
- 감사에서 버전 사이에 없는 기록은 **상대적 누락**입니다. 공식 전체 목록에 없는 것으로 단정하지 않습니다.
- 2027년 기준 중위소득·주거급여·교육급여 고시는 필수 회귀 확인 예시이며, 다른 모든 행정규칙 종류에도 동일한 파이프라인을 적용합니다.
- 공공기관의 실제 반영 완료 여부는 판정하지 않습니다.
- 제출 저장소로 옮기기 전 성능·커버리지·근거 검증을 완료합니다.


## Independently runnable collection engine

`python -m unified.engine --root data --streams 4 --details 24`

Requires the official law API `LAW_OC` identifier (`dori` is configured in Actions). The collection engine does **not** read the previous repositories. It scans the 15 legal/rule kind/current/history streams in rotating batches, retains a complete/incomplete coverage ledger, writes gzip files per official document version and compares verified prior versions. It also detects annual successor announcements without merging different legal IDs. Incomplete annex files produce partial/unverified status rather than invented amounts.

Output structure: `data/documents/<source>/<hashed-stable-id>/<hashed-version>.json.gz`, `data/comparisons/<version-hash>.json.gz`, and small `data/collection-state.json`. A later GitHub Actions run only stages changed per-version files. The first audit is independent of this new collection process.
