# 정책도미노 Unified

**목적:** 상위 정책 제·개정이 실제 공공기관의 어떤 사업·업무·서비스·시스템에서 어떤 기준과 절차를 변경해야 하는지 공식 근거와 함께 제시합니다.

진행 계획·완료 기준: [최종 통합 재구축 계획](docs/FINAL_INTEGRATION_PLAN.md)

## 현재 개발 상태

- 기존 v2·domino·NEXT의 공식 판본 **목록** 감사를 수행했습니다. 고유 버전 46,647건, 완전 추출본 후보 862건, 신규 저장소 이식 846건은 공식 XML·첨부 전수 재검증 완료를 의미하지 않습니다.
- 통합 브랜치에서 역사 색인 1회 이전, 원본 검증 등급, 증분 수집과 비교, 2단계 정책 관계 검증, 사업 영향 후보, AI 설명, 변경 핵심 및 근거 UI를 개발 중입니다.
- 검증되지 않은 기관별 업무 변경을 만들지 않으며, 해당 정책의 법적 기준·사업 근거가 부족하면 분석 대기/검토 후보 상태로 남깁니다.
- **정식 완료/운영 품질 보장 상태가 아닙니다.** 신규 공식 원문 확보 및 기관별 영향 0건 문제, 미수집 고시·별표 등은 실제 재검증이 필요합니다.

## 데이터와 실행

`python -m unittest discover -s tests -v`

`python -m unified.engine --root data --streams 3 --details 18`

`python -m unified.impact --root data`

`python -m unified.publish --root data --output site/data.json`

`python -m unified.acceptance --root data --site site --output site/acceptance.json`

GitHub Actions: `.github/workflows/unified.yml` — 통합 단일 프로덕션 흐름, `.github/workflows/pr-quality.yml` — PR 회귀 검사, `.github/workflows/audit.yml` — 읽기전용 과거 감사.

통합 작업은 별도 브랜치와 **단일 PR**로 진행합니다. 기존 `policy-domino`와 `policy-domino-next` 저장소는 수정하지 않습니다.

수집 공식 ID `LAW_OC`는 Actions에 구성되어 있습니다. 정부24 현재 API 수집에는 `GOV24_SERVICE_KEY`가 필요합니다. 교체 가능한 LLM 연결은 `PD_LLM_API_KEY`/`PD_LLM_MODEL`로 설정하며, 키가 없으면 원천 근거 없는 AI 설명을 생성하지 않습니다.
