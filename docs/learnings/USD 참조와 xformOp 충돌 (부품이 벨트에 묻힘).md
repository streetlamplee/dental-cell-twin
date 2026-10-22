---
type: learning
date: 2026-10-22
tags: [visiontwin, usd, bug, day6]
related: ["[[2026-10-22 Day6 실제 CAD 부품 제품]]"]
---

# USD 참조와 xformOp 충돌 (부품이 벨트에 묻힘)

## 현상
KFL08 변형을 제품으로 올렸더니 검사 프레임에 **0.1 m 원형 보스만** 보이고, 0.2 m 다이아몬드 플랜지가 보이지 않았다. 형상 데이터(위/아래 면적 0.0075 m², 서브셋 없음, 법선 정상)는 문제가 없었다.

## 원인
변형 레이어의 `/Part`는 정규화용 xformOp(translate → rotateXYZ → scale)를 가진다. 제품 프림(`/World/Products/P_xxxx`) **자체에** 이 레이어를 참조하고 `XformCommonAPI.SetTranslate`를 호출하니, 같은 `xformOp:translate`가 **제품 위치로 덮어써졌다.** 바닥을 z=0으로 맞추고 x/y를 가운데로 옮기던 오프셋이 사라져서 부품 바닥이 z=0.783(벨트 윗면 0.8보다 1.7 cm 아래)에 놓였고, 얇은 플랜지가 벨트 속에 묻혔다.

`render_smoke.ps1 -Part kfl08`이 Kit에서 본 제품 bbox와 xformOp 목록을 출력하게 해서 찾았다.

## 해결
제품 프림은 위치용 Xform으로만 두고, 변형 참조는 **자식 프림** `P_xxxx/Part`에 건다. 두 변환 스택이 분리된다.

## 일반 규칙
자체 xformOp를 가진 에셋을 참조할 때는, 참조한 프림에 직접 변환을 쓰지 말고 감싸는 부모 Xform을 둔다.
