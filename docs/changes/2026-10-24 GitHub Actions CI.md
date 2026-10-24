---
type: change
date: 2026-10-24
tags: [visiontwin, ci, github]
related: ["[[스크립트 목록]]"]
---

# GitHub Actions CI

- `.github/workflows/core-tests.yml`: push, PR, 수동 실행 때마다 `windows-latest` 러너에서 core 테스트를 돌린다.
  - 순서: Python 3.12 → `scripts/requirements-dev.txt` 설치 → **로컬과 같은 `scripts/test_core.ps1`** 실행
  - 테스트 로그는 artifact로 남긴다
- 범위: Kit에 의존하지 않는 `core/` 테스트만 돈다. Kit 앱, 렌더, 실험 run은 RTX GPU와 Kit SDK가 필요해서 CI에서 돌릴 수 없다. 그쪽 근거는 `results/`의 기록이다.
- 테스트에 필요한 데이터는 저장소에 들어 있다: 기계와 로봇의 `kinematics.json`, `reference/teeth_mill.urdf`, `assets/parts/catalog.json`.
- README 맨 위에 배지를 달았다.
