---
type: topic
date: 2026-10-22
tags: [visiontwin, plan, cad, day5, day6]
related: ["[[2026-10-22 CAD 자산 파이프라인 추가 (URDF→STP→USD)]]", "[[2026-10-22 실제 CAD 부품을 제품으로 사용]]", "[[2026-10-22 Progress]]"]
---

# Day 5-6 작업 분해

계획서의 Day 5(밀링기 URDF→STP→USD)와 Day 6(실제 CAD 부품 제품)을 실행 순서로 나눈 것이다. 각 단계의 결과는 체크하고 해당 노트를 링크한다.

## Day 5 — CAD 자산 파이프라인

| # | 단계 | 산출물 | 확인 방법 |
|---|---|---|---|
| 5.1 | **Gate C:** Kit 110.4에서 `omni.kit.converter.hoops_core`를 받아 STP 1개 변환 | `scripts/probe_cad_converter.*`, 결과 노트 | USD 생성, 프림 계층/단위 출력 |
| 5.2 | CAD용 Python 환경(CadQuery/OCP), 시스템 Python을 오염시키지 않도록 별도 venv | `scripts/setup_cad_env.ps1`, `.venv-cad/`(git 제외) | `import cadquery` |
| 5.3 | URDF 파서(순수 Python) + 테스트 | `core/urdf_model.py`, `tests/test_urdf_model.py` | 링크 6, 비주얼 16, 관절 5, 홈 자세 변환 |
| 5.4 | URDF → STP(링크별 부품, 이름 = 링크, 색) + kinematics.json | `scripts/urdf_to_step.*`, `assets/cad/teeth_mill.stp/.kinematics.json` | 재실행 시 같은 결과 |
| 5.5 | STP → USD (USD converter 옵션 그대로) | `scripts/convert_step_to_usd.*`, `assets/cad/teeth_mill.usd` | 변환 성공 |
| 5.6 | 변환 검증: 링크 이름 매칭, 단위/축, 링크별 bbox vs URDF (±1 mm) | `scripts/verify_cad_usd.*` | 16/16 비주얼, 6/6 링크 |
| 5.7 | MillStation: 씬 배치 + kinematics.json으로 관절 피벗 + 가공 사이클 동작(시각용) | `mill_station.py`, scene 연동 | 렌더 스모크, GUI |
| 5.8 | 회귀: 검사/분류 결과 불변 (seed 42) | run 폴더 | `compare_runs` 동일 |

## Day 6 — 실제 CAD 부품 제품

| # | 단계 | 산출물 | 확인 방법 |
|---|---|---|---|
| 6.1 | **Gate D:** 재배포 가능한 부품 STP 후보 조사 | 후보표 노트 | 라이선스/크기/위에서 본 특징 |
| 6.2 | 다운로드 + SHA256 + 라이선스 기록 | `assets/parts/sources.json`, `LICENSES.md`, `scripts/fetch_parts.*` | 해시 일치 |
| 6.3 | STP → USD (5.5 스크립트 재사용) + 정규화 레이어 | `assets/parts/usd/`, `scripts/normalize_part.*` | 단위/원점/크기 |
| 6.4 | 변형: good / color / missing | `scripts/make_part_variants.*` | 렌더로 구분 확인 |
| 6.5 | ProductCatalog + ConveyorConfig(부품, 결함 비율) | `core` + scene 연동 | 단위 테스트, 렌더 |
| 6.6 | 형상 검사(면적비, matchShapes, 구멍 수) + 테스트 | `vision_inspector.py` 확장 | 합성 이미지 테스트 |
| 6.7 | 보정(seed 1) + 평가(seed 42), 결함 종류별 지표 | run 폴더, 노트 | 실측 그대로 기록 |
