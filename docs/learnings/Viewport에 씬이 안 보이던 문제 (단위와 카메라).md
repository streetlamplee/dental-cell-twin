---
type: learning
date: 2026-10-21
tags: [visiontwin, kit, viewport, units]
related: ["[[2026-10-21 Day1 visiontwin.factory 확장 골격과 팩토리 씬]]", "[[렌더 스모크 테스트 (Viewport 자동 캡처)]]"]
---

# Viewport에 씬이 안 보이던 문제 (단위와 카메라)

## 현상
GUI에서 Build Scene → Start를 누르면 카운터는 정상으로 올라갔다(`spawned=30 exited=30`). 하지만 Viewport에는 라이트와 카메라 아이콘만 보이고 컨베이어와 상자는 보이지 않았다.

![[image2.png]]

Console 경고:
```
[omni.metrics.assembler.ui] Stage units changed to 'm'. Object positions and sizes are NOT auto-converted.
```

## 원인
1. 새 stage는 Kit 기본값인 **cm 단위**로 만들어지고, 기본 카메라와 라이트도 cm 기준으로 배치된다(라이트 Z=305 등).
2. Build Scene이 그 뒤에 `metersPerUnit=1.0`, Z-up으로 바꾸면서 기본 카메라가 수백 m 밖에 있는 셈이 됐다. 그래서 6m 컨베이어가 점처럼 보였다.
3. `frame_viewport_prims`로 다시 맞추려 했지만, 렌더 결과는 밝은 회색 화면뿐이었다. 정확한 원인은 **미확정**이다(Dome/Distant 라이트를 포함한 프레이밍 문제로 추정).

## 해결
- 앱 설정(`visiontwin.app.kit`)에서 새 stage를 **처음부터 Z-up, m 단위**로 만든다.
  ```toml
  [settings.persistent.app]
  stage.upAxis = "Z"
  [settings.persistent.simulation]
  defaultMetersPerUnit = 1.0
  ```
  근거: `omni.kit.stage_template.core`의 `stage_core.py`가 `/persistent/app/stage/upAxis`를 읽는다. 환경설정 페이지는 `/persistent/simulation/defaultMetersPerUnit`를 쓴다.
- 자동 프레이밍 대신 고정 카메라 `/World/Factory/OverviewCamera`(eye=(-2,-6.5,3.5), target=(0.3,0,0.8))를 만들고, `viewport.camera_path`를 그 카메라로 지정한다. 실행할 때마다 같은 구도가 나와서 시연 영상에도 유리하다.
- 조명을 Kit 기본 리그 수준으로 낮췄다: Distant 3000→1000, Dome 300→500.

## 검증
`.\scripts\render_smoke.ps1` 결과. 컨베이어, 검사선, 배출선, bin, 정상품(파랑)과 불량품(빨강)이 모두 보인다.

![[day1_render_smoke.png]]

## 남은 점
- 바닥이 약간 과노출이다. Day 3에서 검사 카메라용 조명을 다시 맞춘다.
- 사용자 PC의 `user.config.json`에 이미 다른 persistent 값이 저장돼 있으면 `.kit` 기본값보다 그 값이 우선한다. 이상하면 Edit → Preferences → Stage에서 Up Axis와 단위를 확인한다.
