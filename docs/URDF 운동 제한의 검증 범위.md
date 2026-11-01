---
title: URDF 운동 제한의 검증 범위
type: concept
created: 2026-11-01
tags: [urdf, verification, robotics]
related: ["[[smoothstep 궤적의 속도와 가속도]]", "[[2026-11-01 관절 속도와 가속도 검증]]"]
---

# URDF 운동 제한의 검증 범위

URDF에 선언된 속도와 실제 장비가 허용하는 속도는 별개의 근거다. 이번 검증은 저장된 원본 URDF의 `limit velocity`와 [[smoothstep 궤적의 속도와 가속도]] 계산값을 비교한다. 실제 모터·감속기·컨트롤러의 성능을 검증한 것은 아니다. `effort`는 가속도 제한으로 사용하지 않는다.

로봇 원본 URDF는 `assets/robots/sources.json`에 고정된 SHA256과 비교한다. 현재 궤적에 사용되는 kinematics JSON과 원본의 관절 이름·타입·부모/자식·원점·축·위치 제한도 일치해야 한다. 기존 JSON에는 속도·가속도가 저장되지 않으므로 원본에서 별도로 읽는다.

선언 속도는 로봇 joint1~3이 50 rad/s, joint4~6이 200 rad/s, 그리퍼 각 축이 0.08 m/s다. 기계 X/Y/Z는 0.1 m/s이고 B/C는 속도 제한이 없다. 모든 대상 축에 가속도 제한이 없다. 이런 값은 장비 사양과 독립적으로 확인되지 않았으므로 URDF 기준 비교임을 명시한다.

결과는 제한 이내(`within`), 제한 초과(`exceeded`), 제한 부재(`unverified`)를 구별한다. 전체 제한이 있어야 전체 합격이다. 위치 불연속(`discontinuous`)은 별도 실패로 기록한다. 장치 부하·토크·추종 오차와 힘/동역학은 이번 비교에 포함하지 않는다. 실제 적용 전 제한값의 출처를 보완해야 한다.
