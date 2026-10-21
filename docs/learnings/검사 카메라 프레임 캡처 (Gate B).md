---
type: learning
date: 2026-10-21
tags: [visiontwin, kit, capture, gate-b, day3]
related: ["[[렌더 스모크 테스트 (Viewport 자동 캡처)]]", "[[2026-10-21 Day3 비전 검사 파이프라인]]"]
---

# 검사 카메라 프레임 캡처 (Gate B)

## 결론
**Gate B 통과.** Kit 110.4.0에서 검사 카메라의 렌더 RGB를 Python numpy 배열로 실시간으로 받을 수 있다. 다만 **두 번째 Viewport를 만들 때 D3D12에서 간헐적으로 크래시**가 난다(아래 "안정성").

## 동작하는 방법
```python
from omni.kit.viewport.utility import create_viewport_window, capture_viewport_to_buffer, next_viewport_frame_async
win = create_viewport_window("VisionTwin Inspection Camera", width=320, height=280, camera_path=cam)
await next_viewport_frame_async(win.viewport_api, 3)       # 먼저 렌더가 시작되게 둔다
w = win.viewport_widget
w.fill_frame = False; w.expand_viewport = False; w.set_resolution((640, 480))  # 창 크기와 무관한 고정 해상도
capture_viewport_to_buffer(win.viewport_api, cb)            # cb(buffer, size, w, h, fmt), fmt = RGBA8_UNORM
```
- `buffer`는 PyCapsule이다. `ctypes.pythonapi.PyCapsule_GetPointer`로 포인터를 얻은 뒤 `np.frombuffer(...).reshape(h, w, 4)`. **콜백 안에서 `.copy()`** 해야 한다(콜백이 끝나면 버퍼가 무효).
- 구현: `frame_provider.py`의 `InspectionFrameProvider`.

## 시도했지만 안 된 방법
| 방법 | 결과 |
|---|---|
| 메인 Viewport의 `camera_path`를 바꾼 뒤 캡처 | 30프레임 뒤에도 **이전 카메라 화면**이 저장됨 |
| `omni.ui.Window` 안에 `ViewportWidget(camera_path, resolution)` 직접 생성 | **프레임이 한 번도 오지 않음** (`next_viewport_frame_async` 20초 타임아웃) |
| 창 생성 직후 바로 `set_resolution` | 크래시 1회 (이후 첫 프레임 뒤에 고정하도록 변경) |
| `create_viewport_window`만 쓰고 해상도 고정 안 함 | 동작하지만 해상도가 창 크기(312×248 등)를 따라감 |

앱 설정에 `[settings.app.viewport.defaults] fillViewport = true`가 있어서, 고정 해상도를 쓰려면 `fill_frame`과 `expand_viewport`를 직접 꺼야 한다.

## 안정성: 두 번째 Viewport와 D3D12 크래시
- 증상: 두 번째 Viewport가 생기고("Multiple Hydra Engines detected") 몇 초 안에 `carb.graphics-direct3d.plugin.dll` 안에서 access violation이 난다. 직전에 `CreateCommandList failed` 오류가 함께 나오는 경우가 많다.
- 빈도: 대응 전에는 probe/collect 12회 중 7회 크래시.
- 시도한 것과 결과:

| 시도 | 결과 |
|---|---|
| 다른 Kit 인스턴스 종료 (VRAM 공유 가설) | 단독 실행에서도 크래시 → **가설 틀림** |
| 검사 Viewport를 새 stage **전에** 생성 | 3회 중 2회 크래시. 게다가 **메인 Viewport가 씬을 렌더하지 않음**(아래) |
| Vulkan 백엔드 `app.vulkan = true` | 첫 실행에 셰이더 컴파일 약 170초. 이후 같은 계열의 cmdlist 오류 뒤 **멈춤(hang)** → 되돌림 |
| **메인 Viewport가 60프레임을 렌더할 때까지 기다린 뒤** 검사 Viewport 생성 | **probe 7회 연속 + collect 3회 성공** ✅ |

- 결론(추정): `renderer.asyncInit = true`라서 앱 시작 직후나 새 stage 직후에는 RTX가 아직 초기화/업로드 중이다. 그때 두 번째 Hydra 엔진을 만들면 경쟁 상태가 생긴다. 근본 원인은 확인하지 못했고, 대기로 회피한 것이다.
- 자동화 스크립트는 `--/crashreporter/gatherUserStory=0`으로 실행한다. 그래야 크래시가 나도 리포트 창 없이 바로 종료된다(처음에는 창이 떠서 10분간 대기했다).

## 부작용 두 가지 (같은 날 발견, 수정됨)
1. **메인 Viewport가 비어 보임** (사용자가 GUI에서 발견): 카메라와 라이트 아이콘만 보이고 컨베이어가 안 보였다.
   - 원인 A: 검사 Viewport를 새 stage 전에 만들었더니 메인 Viewport가 새 stage의 지오메트리를 그리지 않았다.
   - 원인 B: 검사 창이 생긴 뒤에는 `get_active_viewport()`가 **검사 창**을 돌려줘서, OverviewCamera가 엉뚱한 Viewport에 설정됐다.
   - 수정: 순서를 "새 stage → 씬 → 메인 렌더 대기 → 검사 Viewport 생성"으로 바꿨다. 메인 Viewport는 확장의 `main_viewport` 속성에 처음 한 번 저장해서 쓴다.
2. **stale 프레임**: 1.5초 떨어진 두 제품(#17, #18)이 바이트까지 같은 프레임을 받았다. `rtx.ecoMode`를 꺼도 다시 발생했다(#13).
   - 수정: 요청 이후 새 프레임을 1장 기다린 뒤 캡처한다. 직전 캡처와 MD5가 같으면 3프레임 뒤 다시 캡처하고, 최대 3회까지 시도한다. 그래도 같으면 `unknown`("stale frame")으로 기록한다(잘못된 판정 대신 미판정).
   - 이후 run(seed 1, seed 42)에서는 중복 프레임 0건.
   - **Day 4에서 대체됨:** 근본 원인은 비동기 렌더링으로 인한 이미지 지연이었다. 동기 렌더링과 프레임 지정 캡처로 바꿨다 → [[렌더 지연과 프레임 지정 캡처]]. MD5 stale 감지는 안전장치로 남겼다.

## 진단 도구
`.\scripts\probe_capture.ps1`: 확장의 provider(A)와 새 ViewportWindow(B)로 각각 캡처해서 성공 여부와 PNG를 남긴다.
