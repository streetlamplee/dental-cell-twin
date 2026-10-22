---
type: decision
date: 2026-10-22
tags: [visiontwin, plan, cad, usd-converter]
related: ["[[2026-10-21 Kit 110.4.0 kit_base_editor 기반 앱 구성]]", "[[2026-10-22 Progress]]"]
---

# CAD 자산 파이프라인 추가 (URDF→STP→USD)

## 요약
`reference/teeth_mill.urdf`(5축 치과용 밀링기)를 **STP로 바꾸고, 사용자의 USD converter로 USD를 만들어** 공장 라인의 가공 스테이션으로 넣는다. 계획서에 새 Day 5로 추가하고, 기존 Day 5~7은 Day 6~8로 미뤘다.

## 배경
- 사용자 요청(2026-10-22): reference의 URDF를 STP로 바꾸고 USD converter로 이 프로젝트에 포함.
- Day 1~4가 2026-10-21 하루에 끝나서 달력 종료일(10-28)까지 여유가 있다.

## 입력 조사 (2026-10-22)
| 항목 | 내용 |
|---|---|
| `teeth_mill.urdf` | ROS2 xacro를 펼친 파일. 형상 있는 링크 6개, 비주얼 16개(box/cylinder만, 메시 없음). 움직이는 관절 5개: `x_joint, y_joint, z_joint`(prismatic, m), `b_joint, c_joint`(continuous, rad). m 단위, Z-up. inertial/collision 없음 |
| USD converter | `Documents/01_project/usd_converter/kit-app-template` (GitHub `streetlamplee/USD_converter`), Kit **109.0.3**, 확장 `my_company.stp_pipeline_setup`. `omni.kit.converter.hoops_core`의 `create_converter_task(stp, usd, options)` 사용. 옵션: `bOptimize=true, instancing=true, tessLOD=0, convertMetadata=false, useMaterials=false`. 폴더 감시 서비스 + Nucleus 업로드 |

## 핵심 문제와 결정
1. **STEP에는 관절이 없다.** STEP은 형상(B-rep)만 담는다. → URDF에서 관절 정보를 `kinematics.json`으로 따로 뽑고, 변환된 USD에 코드로 다시 적용한다. 관절의 원본은 언제나 URDF다.
2. **링크 식별:** STEP 부품 이름을 URDF 링크 이름으로 한다. 변환된 USD에서 이 이름으로 링크를 찾는다. 이름이 매칭되지 않으면 실패로 처리하고 추측하지 않는다.
3. **URDF → STP 도구:** CadQuery/OCP(OpenCascade, pip 설치)를 1순위로 한다. 박스/실린더만 있어서 충분하고, 색이 들어간 STEP 어셈블리를 쓸 수 있다. 실패하면 FreeCAD 명령줄을 쓴다.
4. **USD converter 사용 방식(Gate C):** 이 프로젝트는 Kit 110.4이고 converter는 109에서 검증됐다.
   - 1순위: 이 프로젝트에서 `hoops_core`를 직접 사용(변환 로직은 사용자 converter의 옵션을 따른다)
   - 2순위: 기존 `usd_converter` 앱(Kit 109)을 외부 도구로 스크립트에서 호출하고, 결과 USD를 `assets/cad/`에 커밋
   - 둘 다 막히면: URDF → USD 직접 생성으로 씬 통합만 하고, STP 경로는 Known Issue. "USD converter로 변환했다"고 주장하지 않는다.
5. **검증:** 변환 직후 링크 이름, 단위(mm/cm/m), 축, 링크별 바운딩 박스를 URDF와 비교한다(허용 오차 1 mm).
6. **역할 범위:** 밀링기는 **시각 자산**(가공 스테이션)이다. 관절 동작은 시각용 가공 사이클이다. 물리, G-code, 정밀 치수는 제외한다(URDF 치수와 감속비도 임시값). 비전 검사와 분류에는 영향을 주지 않으며, 회귀 run으로 확인한다.

## 영향
- 계획서: 변경 이력, 결과물 7번, 제외 범위, Gate C, 아키텍처(CAD 파이프라인), Day 5 신설, Day 번호 이동, 예시 프롬프트, 폴더 구조, 우선순위 표
- 새 폴더: `reference/`(입력, 커밋), `assets/cad/`(생성물)
- 예정 스크립트(목적별 분리): URDF → STP/kinematics 생성, STP → USD 변환, 변환 검증

## 남은 불확실성
- Kit 110.4 레지스트리에서 `omni.kit.converter.hoops_core`를 받을 수 있는지
- HOOPS 출력의 프림 계층/이름 규칙, 단위(STEP mm → USD cm 가능성), STEP 색 보존 여부
- CadQuery의 Python 3.12 / numpy 2.x 환경 호환성
