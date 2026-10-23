---
type: learning
date: 2026-10-23
tags: [visiontwin, kit, python, scripts]
related: ["[[스크립트 목록]]"]
---

# exec 스크립트의 함수 안 `import omni.x`가 Kit을 멈추게 함

## 증상
`--exec` 스크립트가 시작하자마자 죽었다. Kit은 종료되지 않고 계속 떠 있었고, 스크립트는 10분 제한 시간까지 끝나지 않았다. 2026-10-23에 두 번 겪었다(`probe_onnx_in_kit.py`, `render_robot_pose.py`).
```
UnboundLocalError: cannot access local variable 'omni' where it is not associated with a value
    app = omni.kit.app.get_app()
```

## 원인
`async def _main()` 안 어딘가에 `import omni.kit.pipapi`(또는 `import omni.kit.actions.core`)가 있으면, Python은 `omni`를 **함수 전체의 지역 변수**로 본다. 그래서 그 import보다 앞에 있는 `omni.kit.app.get_app()`에서 `UnboundLocalError`가 난다. 이 줄이 `try/finally` 밖에 있으니 `app.post_quit()`도 불리지 않고, Kit은 그대로 남는다.

## 규칙
- exec 스크립트의 `omni.*` import는 **모듈 맨 위**에 둔다. 확장 모듈(`extension.py`)의 함수 안 import도 같은 문제가 있으니, 패키지 이름(`omni`)을 함수 안에서 다시 바인딩하지 않는다.
- `app = omni.kit.app.get_app()` 다음의 모든 코드는 `try/finally: app.post_quit(code)` 안에 둔다.
- 멈췄을 때: 백그라운드 작업을 멈추고 `kit.exe`를 종료한다(`Get-Process kit | Stop-Process`).
