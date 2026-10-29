---
title: USD 합성과 변환 계층
type: concept
created: 2026-10-26
tags: [visiontwin, openusd, composition, transform]
related: ["[[USD 인스턴싱과 개별 편집]]", "[[USD 참조와 xformOp 충돌 (부품이 벨트에 묻힘)]]", "[[2026-10-26 면접 준비용 Omniverse 고도화 구현]]"]
---

# USD 합성과 변환 계층

- 참조된 prim의 같은 속성에 더 강한 opinion을 작성하면 기존 변환값이 덮어써질 수 있다. 부모 배치 Xform과 자산 내부 정규화 Xform을 나눠 수치로 비교한다.
- 자산·배치·실행 상태 레이어의 책임을 분리하고, 편집 대상과 sublayer 강도를 명시한다. property stack으로 최종 속성값의 출처를 확인한다.
- 실행 상태 레이어만 제거해 배치를 유지하면서 복원한다. 원본 파일 해시, 저장·재열기 결과도 검증한다.
- `metersPerUnit`·`upAxis` 메타데이터를 바꾸는 것과 좌표값을 실제로 변환하는 것은 구분한다. 작은 meter/mm 및 축 변환 예제로 확인한다.
- 파일 이름의 variant와 USD VariantSet은 다르다. 동일 상태를 두 방식으로 구성해 선택 저장·공유·카탈로그 호환성을 비교한다.

검증 스크립트는 `scripts/verify_usd_composition.ps1`이다. 실험 데이터는 `results/interview/composition/`에 분리해 저장한다.

## 검증한 예제와 적용 방법

`results/interview/composition/20261026_225331/report.json`에서 다음을 확인했다.

| 예제 | 관측 | 프로젝트에 적용할 기준 |
|---|---|---|
| 같은 prim의 translate 덮어쓰기 | 월드 위치 `(10, 0, 0)`에서 자산 보정이 사라짐 | 배치 이동을 자산 내부 보정과 같은 속성에 작성하지 않음 |
| 부모 Xform 아래 참조 | `(9.9, 0, 0.02)`로 원래 보정 유지 | 기존 배치 부모와 자산 계층 분리 유지 |
| 실행 상태 레이어 비우기 | runtime의 `(3, 0, 0)` opinion 제거 후 layout으로 복원 | 임시 실행 상태를 원본 자산에 저장하지 않음 |
| mm 자산 참조 | 단위 메타데이터만으로 크기가 자동 보정되지 않음 | 참조 경계에서 명시적 스케일 적용 |
| Y-up → Z-up | 메타데이터만 바꾸면 좌표 유지, 회전 후 좌표 변환 | 축 메타데이터와 실제 좌표 변환을 함께 확인 |

VariantSet의 선택 저장·재열기와 원본 참조 공유는 별도 예제로 검증했다. 운영 카탈로그는 기존 파생 파일 방식을 유지한다. 현재 카탈로그의 파일별 경로와 호환되며, VariantSet으로 전체 자산을 바꿀 필요가 확인되지 않았기 때문이다. 이 예제를 운영 VariantSet 전환 완료로 설명하지 않는다.
