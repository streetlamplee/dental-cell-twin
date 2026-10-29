---
title: Kit 비동기 작업 수명주기
type: concept
created: 2026-10-26
tags: [visiontwin, kit, lifecycle, asyncio]
related: ["[[시뮬레이션 시각과 캡처 추적]]", "[[면접 준비용 Omniverse 고도화 작업 계획]]", "[[2026-10-26 면접 준비용 Omniverse 고도화 구현]]"]
---

# Kit 비동기 작업 수명주기

1. 각 실행·Stage의 유효 세대를 generation으로 구분한다.
2. Reset·Stage 닫기·Extension 종료 시 세대를 먼저 무효화한다.
3. 소유한 task와 캡처 요청을 추적하고 취소한다. 정상·오류 콜백 모두 세대를 검사한다.
4. 요청은 정상·시간 초과·취소 중 하나로 한 번만 종료한다. Python waiter를 취소한 뒤 native 캡처 콜백이 올 수 있으므로 콜백에도 종료 상태를 검사한다.
5. 이벤트 구독, 로그와 UI·뷰포트 자원을 정리한다. await 가능한 경로에서 task 종료를 확인한다.

동기 `on_shutdown` 안에서 이벤트 루프를 중첩 실행하지 않는다. 즉시 접근을 차단하고 취소를 요청한 다음, 진행 가능한 루프에서 정리가 완료되는지 검증한다. 파일 변경 자동 재시작은 성능·기준 실험에서 끄되, Extension 비활성화/재활성화 자체는 별도 시험한다.

## 자동 실행 중 렌더 진행 조건

설치된 Kit 110.4의 `omni.kit.viewport.window/window.py`는 `/app/renderer/skipWhileMinimized`가 켜진 상태에서 최소화 이벤트를 받으면 `viewport_api.updates_enabled`를 끈다. 같은 확장의 설정에는 `/app/renderer/skipWhileInvisible=true`도 있다. 앱 update가 계속되는 것과 검사 뷰포트가 실제 렌더되는 것은 구분해야 한다.

`scripts/_common.ps1`의 자동 실행 플래그에서는 두 설정을 false로 고정했다. 일반 GUI 실행 설정은 유지한다. `scripts/inspect_kit_window.ps1`은 Kit 주 창의 최소화·가시성을 읽기 전용으로 기록하며 다른 프로그램의 창 제목을 수집하지 않는다. 검사 뷰포트 자체의 매 순간 렌더 진행을 이 스냅샷만으로 보장하지는 않는다.

2026-10-29 추가 native 예약 전환 40회에서는 모든 요청이 native에 예약됐고 전환 직전 native 콜백이 아직 오지 않은 상태였다. 네 전환 후 Python 콜백 전달·소유 task·pending이 모두 0이었다. 이는 Python 소유 자원 정리 검증이며 모든 native GPU 메모리 해제를 측정한 결과로 확대하지 않는다. 상세 근거는 [[2026-10-26 면접 준비용 Omniverse 고도화 구현]]에 연결한다.

최종 native 전환 배치 `results/interview/lifecycle_pending/20261029_213205/report.json`에서는 확장 재활성화 뒤 Start를 두 번 호출하고, 앱 update 20회 동안 simulation time이 `20 × 1/60 = 1/3초` 증가하는지도 10번 확인했다. 구독 중복으로 같은 update에 simulation을 여러 번 진행시키는 동작은 관측되지 않았다. 기록은 각 행의 `subscription_probe`에 있다.
