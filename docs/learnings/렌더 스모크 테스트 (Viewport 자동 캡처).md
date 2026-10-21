---
type: learning
date: 2026-10-21
tags: [visiontwin, kit, capture, gate-b]
related: ["[[Viewport에 씬이 안 보이던 문제 (단위와 카메라)]]", "[[스크립트 목록]]"]
---

# 렌더 스모크 테스트 (Viewport 자동 캡처)

## 요약
GUI 앱을 `--exec scripts/render_smoke.py`로 실행하면 사람 없이도 다음을 자동으로 한다: 씬 생성 → 컨베이어 실행 → Viewport를 PNG로 저장 → 종료. Agent가 렌더 결과를 직접 이미지로 확인할 수 있다.

## 사용한 API (Kit 110.4.0, omni.kit.viewport.utility 2.1.2)
```python
from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file, next_viewport_frame_async
vp = get_active_viewport()
await next_viewport_frame_async(vp, 30)
cap = capture_viewport_to_file(vp, "out.png")
result = await cap.wait_for_result(completion_frames=60)  # ['LdrColor'] on success
```
- 같은 모듈에 `capture_viewport_to_buffer(vp, on_capture_fn)`도 있다. 파일 없이 메모리로 받는 방식이며, Day 3 실시간 검사(Gate B)의 후보다.
- 확장은 `visiontwin.factory.extension.get_instance()`로 접근하고, `build_scene_async / start / stop / reset` 공개 메서드를 쓴다.
- 설정값은 `--/visiontwin/smoke/out=...`처럼 명령줄 carb 설정으로 넘긴다.

## 확인된 한계 (Day 3 과제)
- `viewport.camera_path`를 InspectionCamera로 바꾼 뒤 30프레임 기다렸다 캡처해도 **이전 카메라 화면이 저장됐다.** 카메라 전환이 렌더에 반영되기까지 더 기다려야 하거나, 검사 카메라용 render product를 따로 만들어야 할 수 있다. 미확인.
- RTX 첫 로딩 시간과 관계없이 결과가 같았다(240프레임과 1500프레임 비교).

## 실행
`.\scripts\render_smoke.ps1 [-Frames 240]` → `results/smoke/render_smoke_<ts>.png`(+ `_inspection.png`)
