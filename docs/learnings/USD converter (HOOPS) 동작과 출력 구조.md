---
type: learning
date: 2026-10-22
tags: [visiontwin, cad, usd-converter, gate-c]
related: ["[[2026-10-22 Day5 CAD 자산 파이프라인]]", "[[2026-10-22 CAD 자산 파이프라인 추가 (URDF→STP→USD)]]"]
---

# USD converter (HOOPS) 동작과 출력 구조

## Gate C 결과: 통과
- 이 프로젝트의 Kit **110.4**에서 `omni.kit.converter.hoops_core-512.2.1`이 레지스트리에서 받아지고 바로 동작한다. 함께 받아지는 것: `omni.kit.converter.common-511.1.1`, `omni.scene.optimizer.core-110.3.1`, `omni.usdex.libs-3.0.0`.
- 사용자 `usd_converter`(Kit 109)와 같은 API를 쓴다.
  ```python
  mgr.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True)
  from omni.kit.converter.hoops_core import get_instance
  await get_instance().create_converter_task(stp, usd, options)
  ```
- 앱 `.kit`에 의존성을 넣지 않고 변환 스크립트에서만 켠다(앱 시작이 무거워지지 않게).
- 진단: `scripts/probe_cad_converter.ps1`, 실제 변환: `scripts/convert_step_to_usd.ps1`

## 출력 구조 (teeth_mill.stp 기준)
```
/teeth_mill                      (defaultPrim, Xform)
  /Looks/Color_<RRGGBB>          (STEP 색마다 Material 1개, inputs:diffuseColor)
  /teeth_mill                    (STEP 루트 어셈블리)
    /<link>                      (Xform, 홈 자세 위치)
      /<part>                    (Xform, instance)
        /Mesh                    (Material 바인딩은 여기, primvars:displayColor도 있음)
```
- **단위: mm** (`metersPerUnit = 0.001`), **Z-up**. m 단위 씬에 참조할 때 배율 0.001을 직접 준다.
- **이름:** STEP 제품 이름이 그대로 프림 이름이 된다. 식별자로 쓸 수 없는 이름은 인코딩된다(예: `1` → `tn__1_`). URDF 링크/비주얼 이름은 이미 유효한 식별자라 그대로 유지됐다.
- **색:** `useMaterials=true`이면 STEP 색이 Material로 보존된다(16/16 확인). 사용자 converter의 기본값은 `false`였다.
- 변환기가 옵션 dict에 `sceneOpGenerateUVs: true`를 스스로 추가한다.
- 부품은 instance로 만들어진다(`instancing=true`). 그래서 검증할 때 `Usd.TraverseInstanceProxies()`로 들어가야 Mesh와 바인딩이 보인다.

## STEP 생성 쪽에서 알게 된 점 (CadQuery 2.8.0)
- `Assembly.export()`는 `.stp` 확장자를 인식하지 못한다 → `exportType="STEP"`을 명시한다.
- 같은 입력으로 다시 만들면 형상과 색은 같지만, **색 스타일 엔티티(STYLED_ITEM)의 순서가 달라서** 파일이 바이트 단위로 같지는 않다. 검증은 바이트 비교가 아니라 `verify_cad_usd.ps1`(형상, 위치, 색)로 한다.
- CadQuery import 때 `cannot open font ... mstmc.ttf` 경고가 나지만 무해하다(스크립트에서 걸러 낸다).
