---
type: learning
date: 2026-10-23
tags: [visiontwin, robot, urdf, usd, rebot]
related: ["[[고도화 방향 조사]]", "[[Kit 110.4 레지스트리와 Kit 안 ONNX 추론 실측]]", "[[USD converter (HOOPS) 동작과 출력 구조]]"]
---

# Seeed reBot Arm URDF를 USD로 가져오기 (PoC 성공)

## 출처
- 저장소 [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm)
  - 커밋 `6c2bb32b3f7f430c58a37cf93d459d07ee99d736`(2026-10-23)
  - 라이선스 **CERN-OHL-W-2.0**(약한 상호주의 오픈 하드웨어). 재배포할 때는 라이선스와 출처를 함께 둔다.
- `Rebot_Arm_description/`에 B601-DM, B601-RS 두 모델이 있다.
  - 각각 URDF(`DM/urdf/ReBot_Arm_DM.urdf`), MuJoCo MJCF, STL 메시(시각용, 충돌용, 손목 카메라 D405, D435i, Gemini 2, UVC)가 있다.
  - 메시 경로는 URDF 기준 상대 경로(`../meshes/...`)라서 `package://` 문제가 없다.

## 모델 (DM)
- 회전 관절 6개(joint1~6, 한계 있음) + 고정 `end_link` + 직동 그리퍼 2개(finger_left 0~0.05 m, finger_right −0.05~0 m)
- 링크 10개, 시각 메시 34개(21.6 MB, 재질 색 11개). 홈 자세 크기 0.53 × 0.20 × 0.28 m. 리치는 약 750 mm(제조사 표기)

## 파이프라인 (이 프로젝트, Isaac Sim 없이)
```powershell
.\scripts\fetch_robot.ps1 -Name rebot_b601_dm          # 고정 커밋, URDF가 쓰는 메시만, SHA256 기록
.\scripts\urdf_mesh_to_usd.ps1 -Urdf assets\robots\rebot_b601_dm\Rebot_Arm_description\DM\urdf\ReBot_Arm_DM.urdf -Out assets\robots\usd\rebot_b601_dm.usd
.\scripts\render_robot_pose.ps1 -Usd assets\robots\usd\rebot_b601_dm.usd -Pose "joint1=-0.9,joint2=-0.7,joint3=-1.3"
```
- `core/urdf_model.py`가 메시 시각 요소를 읽는다(`Visual.mesh`, scale).
- `urdf_mesh_to_usd.py`
  - STL(바이너리/ASCII)을 `UsdGeom.Mesh`로 바꾼다(삼각형 430,912개).
  - URDF 재질 색을 UsdPreviewSurface로 만든다.
  - 링크를 홈 자세의 형제 Xform으로 둔다(밀링기 CAD 자산과 같은 구조).
  - 관절 정보는 `.kinematics.json`에 남긴다.
- `render_robot_pose.py`: 링크 Xform에 FK 변환을 넣어 자세를 만든다. 홈 자세와 관절을 움직인 자세 모두 링크가 어긋나지 않고 렌더됐다.

## 아직 하지 않은 것
- IK(집기 자세 계산), 그리퍼 파지, 라인 통합(벨트↔플래터 이송)
- 실제 팔과의 연동(Seeed Python SDK, USB-CAN): 하드웨어가 없어서 확인하지 않았다
- 받은 메시와 USD(약 21 MB + α)는 아직 git에 넣지 않았다(`.gitignore`). 스크립트와 `sources.json`(커밋, SHA256)으로 다시 만들 수 있다.
