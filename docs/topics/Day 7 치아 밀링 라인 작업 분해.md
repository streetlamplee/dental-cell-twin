---
type: topic
date: 2026-10-22
tags: [visiontwin, plan, line, dental, day7]
related: ["[[2026-10-22 치아 밀링 가공 라인으로 확장]]"]
---

# Day 7 치아 밀링 라인 작업 분해

| # | 단계 | 산출물 | 확인 |
|---|---|---|---|
| 7.1 | 치과 부품 모델(CadQuery): 블랭크, 크라운, 미완성 크라운 → STEP | `scripts/make_dental_parts.*`, `assets/parts/raw/dental_*.step` | inspect_step |
| 7.2 | STEP → USD(USD converter) + 변형 생성기 일반화(변형별 원본, raw/final 단계) | `assets/parts/usd/crown_*` | 렌더 |
| 7.3 | 코어: `PROCESSING` 상태, 공정 스테이션(로딩, 사이클, 대기, 축적, 출구 막힘) | `core/conveyor.py`, `core/product_tracker.py` | pytest |
| 7.4 | 카탈로그: 공정(스테이션, 사이클), 카메라, 투입 간격, raw/final 변형 | `assets/parts/catalog.json`, `core/product_catalog.py` | pytest |
| 7.5 | 씬: 부품별 검사 카메라, 제품 Raw/Final 자식, 행렬 배치, 밀링기 work 숨김, 플래터 월드 변환 | `scene_manager.py`, `mill_station.py` | 렌더 |
| 7.6 | 확장: 스테이션 이벤트, 로딩/가공/언로딩 애니메이션, 형상 전환, 밀링 사이클 동기화, 라인 지표 | `extension.py` | GUI/렌더 |
| 7.7 | 검사기: 배경 차분 분할, a*b* 셰이드, 외곽선 비교 + 테스트 | `core/vision_inspector.py` | pytest |
| 7.8 | 보정(외곽선 기준 포함) → 평가 run, box/KFL08 회귀 | config, run 폴더 | 실측 |
