---
type: learning
date: 2026-10-21
tags: [visiontwin, kit, api]
related: ["[[2026-10-21 Day1 visiontwin.factory 확장 골격과 팩토리 씬]]"]
---

# Kit 110 업데이트 이벤트 구독 API

## 요약
Kit 110.4.0에서는 매 프레임 콜백을 `carb.eventdispatcher`로 구독한다. 오래된 예제에 나오는 `get_update_event_stream().create_subscription_to_pop()` 대신 이 방식을 쓴다.

## 내용
```python
import carb.eventdispatcher, omni.kit.app

sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
    event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
    on_event=lambda ev: step(float(ev["dt"])),
    observer_name="visiontwin.factory.update",
)
sub.reset()  # 구독 해제
```
- `dt`는 `ev["dt"]`로 받는다. 이 값은 **실제 프레임 간격**이므로 시뮬레이션은 이 dt만큼 진행하고, 선 통과는 구간 판정으로 처리한다. → [[2026-10-21 Day2 컨베이어 시뮬레이션과 제품 상태 머신]]
- `omni.usd.get_context().new_stage_async()`와 `get_stage()`도 110에 있다.

## 근거
- `kit/kernel/py/omni/kit/app/_app.pyi` (`GLOBAL_EVENT_UPDATE = 'update'`)
- `kit/extscore/omni.kit.async_engine/.../async_engine.py`의 `observe_event` 사용 예
- `kit/kernel/py/omni/kit/app/_impl/app_iface.py`의 `ev["dt"]`
- `extscache/omni.usd-1.19.11.../omni/usd/_impl/api.py` (`UsdContext.new_stage_async`)
