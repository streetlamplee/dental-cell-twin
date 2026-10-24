---
type: learning
date: 2026-10-23
tags: [visiontwin, cad, usd-converter, hoops]
related: ["[[USD converter (HOOPS) 동작과 출력 구조]]", "[[2026-10-23 STP to USD 변환 강화]]"]
---

# HOOPS 변환 옵션 실측 (LOD, 문자열 인자, 물리량)

`omni.kit.converter.hoops_core` 512.2.1, Kit 110.4. 옵션 문서는 확장 폴더의 `docs/SKILL.md`, `docs/Overview.md`, 기본값 예시는 `docs/converter_config_example.json`에 있다(`%LOCALAPPDATA%/ov/data/exts/v2/omni.kit.converter.hoops_core-512.2.1+110.1.2...`).

## 1. 옵션 값은 문자열이어야 한다
`create_converter_task(src, dst, options)`의 options를 JSON 그대로(`true`, `3`) 넘기면 실패한다.
```
TypeError: parseArgs(): incompatible function arguments ... args: Dict[str, str]
```
→ `convert_step_to_usd.py`에서 bool은 `"true"/"false"`, 숫자는 `str()`로 바꾼다. 설정 파일에는 자연스러운 JSON 타입을 쓴다.

## 2. 반환값
`create_converter_task`는 `(output_url, status)`를 돌려준다. 성공은 `status.error_code == 0`. 이전 스크립트는 파일이 생겼는지만 봤다. 지금은 둘 다 확인한다.

## 3. 테셀레이션 LOD (실측, `results/cad_lod/`)
| 자산 | LOD 0 | LOD 2 | LOD 3 | LOD 4 |
|---|---|---|---|---|
| 크라운 삼각형 / 부피 오차 | 608 / −1.68 % | 8,002 / −0.12 % | 16,774 / −0.05 % | 30,700 / −0.03 % |
| KFL08 삼각형 / 부피 오차 | 8,896 / −1.35 % | 67,208 / −0.005 % | 219,852 / −0.007 % | 283,568 / +0.003 % |
| 밀링기(원본 URDF 형상) | 384 / −0.03 % | 1,024 / −0.002 % | 1,920 / −0.0005 % | 2,688 / −0.0004 % |

- 테셀레이션은 꼭짓점을 실제 곡면 위에 두므로 부피가 항상 조금 작게 나온다(음수 오차). 오차가 곡면의 거친 정도를 보여 준다.
- KFL08은 LOD 2→3에서 삼각형이 3.3배 늘지만 부피 오차는 줄지 않는다. 면적 오차만 0.087 → 0.037 %로 준다.
- 변환 시간은 모두 4초 이하라 차이가 없다. 파일 크기는 삼각형 수에 비례한다.
- 크기(bbox) 차이는 모든 LOD에서 0.000 mm였다. 다만 B-rep bbox는 `BRepBndLib.AddOptimal`로 구해야 한다. `Add`는 느슨해서 0.5~2.2 mm 차이가 나는 것처럼 보였다.

## 4. `convertPhysicsData`는 이 STEP들에 아무것도 쓰지 않았다
- 로그에는 `convertPhysicsData: true`, `physicsAccuracyLevel: 0.99`가 찍힌다.
- 그런데 출력 USD의 어느 spec에도 `omni:hoops:physics:*`가 없었다. CadQuery로 만든 크라운과 FreeCAD 라이브러리의 KFL08 모두 그랬고, `instancing=false`나 `physicsUseGeometryOnRiBRep=true`로 바꿔도 같았다.
- 원인은 확인하지 못했다. 대신 `report_cad_usd.py`가 OpenCascade(`BRepGProp`)로 정확한 부피와 면적을 계산한다.

## 5. `convertMetadata`
STEP 제품 ID와 이름이 프림 속성으로 들어간다: `omni:hoops:metadata:__STEP:ProductID`, `...:ProductName`. 밀링기는 46개, KFL08은 60개다. 이름이 인코딩된 프림(`tn__1_` 등)도 원래 STEP 이름을 찾을 수 있다.

### 보존율 실측 (2026-10-24, `scripts/verify_cad_metadata.ps1`)
STEP 쪽은 OpenCascade XCAF로 제품(형상 정의)과 인스턴스(어셈블리 배치) 이름을 따로 읽고, USD의 `ProductName`과 대조했다.
- **제품 이름 61/61 보존**(자산 6개: 밀링기 23, KFL08 30, 치과 모델 4종 각 2)
- 밀링기의 인스턴스 이름 6개(`4`, `6`, `10`, `14`, `18`, `22`)는 남지 않는다. CadQuery가 링크 배치에 자동으로 붙인 번호다. HOOPS는 인스턴스와 제품을 프림 하나로 합치고, 그 프림에 제품 이름(`base_link` 등)을 단다.
- `legacy` 프로파일(`convertMetadata=false`)로 변환했던 Day 5~6 USD에는 메타데이터 속성이 0개였다(`report_cad_usd`의 metadata 열).
- 한계: 이 STEP들에는 PMI나 사용자 속성이 없어서, 그런 메타데이터의 보존은 확인하지 못했다.
