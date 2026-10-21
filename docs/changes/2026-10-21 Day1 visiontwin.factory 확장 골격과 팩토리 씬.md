---
type: change
date: 2026-10-21
tags: [visiontwin, kit, scene, ui, day1]
related: ["[[2026-10-21 Kit 110.4.0 kit_base_editor 기반 앱 구성]]", "[[Kit 110 업데이트 이벤트 구독 API]]"]
---

# Day1 visiontwin.factory 확장 골격과 팩토리 씬

## 요약
템플릿으로 만든 확장의 예제 카운터 UI를 VisionTwin 패널로 바꾸고, 버튼으로 팩토리 씬을 만들도록 했다.

## 변경 내용
| 파일 | 내용 |
|---|---|
| `source/apps/visiontwin.app.kit` | 의존성에 `"visiontwin.factory" = {}` 추가 |
| `.../config/extension.toml` | 설명/카테고리 변경, `omni.usd` 의존성 추가 |
| `.../factory/extension.py` | 패널 콜백, 업데이트 구독, 시뮬레이션과 USD 동기화 |
| `.../factory/dashboard.py` | omni.ui 패널: Build Scene / Start / Stop / Reset, 속도, 상태, 카운터, 마지막 이벤트 |
| `.../factory/scene_manager.py` | USD 씬 생성(바닥, 컨베이어, 다리, 검사선, 배출선, 배출 bin, 검사 카메라, 조명), 제품 프림 생성/이동/제거 |
| `.../factory/core/layout.py` | 배치 상수(미터, Z-up) |
| `.../tests/test_factory.py` | 템플릿 hello world 테스트를 대체 |

## 씬 규칙
- **Build Scene**을 누르면 새 stage를 만들고 **Z-up, metersPerUnit=1.0**으로 설정한다. 모든 좌표는 미터 단위다.
- 컨베이어는 +X 방향으로 흐른다. 검사선은 x=-0.5, 배출선은 x=1.5, 끝은 x=3.0이다.
- 검사 카메라(`/World/Factory/InspectionCamera`)는 검사선 바로 위 1.2m에서 아래를 내려다본다.
- 색상은 `displayColor`로만 칠한다. 머티리얼은 아직 쓰지 않는다.

## 후속 수정 (같은 날)
GUI에서 씬이 보이지 않는 문제가 있었다 → [[Viewport에 씬이 안 보이던 문제 (단위와 카메라)]]
- 앱 설정에 Z-up, m 단위 기본값 추가 (`visiontwin.app.kit`)
- `OverviewCamera`를 추가하고, Build Scene 후 Viewport가 그 카메라로 보도록 함
- 조명 세기 하향 (Distant 1000, Dome 500)
- 확장에 자동화용 공개 API 추가: `get_instance()`, `build_scene_async / start / stop / reset`
- 의존성 `omni.kit.viewport.utility` 추가

## 검증
- `.\scripts\test_ext.ps1` → 3 tests OK (2026-10-21, 헤드리스)
  - Build Scene 후 Belt, Camera, InspectionZone, RejectZone 프림이 존재함
  - Start 후 제품 프림이 생성됨, Stop 후 30프레임 동안 변화 없음, Reset 후 제품 0개
- `.\scripts\render_smoke.ps1` → 컨베이어와 제품이 렌더됨 (`docs/screenshots/day1_render_smoke.png`)
- **남은 확인:** 사용자가 GUI에서 직접 Build Scene → Start를 눌러 보는 것(Day 1 종료 게이트)

## 관련
- [[2026-10-21 Day2 컨베이어 시뮬레이션과 제품 상태 머신]]
