---
title: Git 검증 산출물 관리
type: decision
created: 2026-10-29
tags: [git, verification, artifacts]
related: ["[[2026-10-26 면접 준비용 Omniverse 고도화 구현]]", "[[index]]"]
---

# Git 검증 산출물 관리

## 저장 범위

- 런타임 구현·테스트, 실험 스크립트, Obsidian 문서를 목적별 로컬 커밋으로 분리한다.
- `results/interview/`의 기준 실행·시간 추적 CSV, 환경·검증 JSON, USD 최소 예제와 원본 소스 스냅샷을 저장한다. 실패·중단 결과도 보존하며 정상 결과로 바꾸지 않는다.
- 대량 캡처 이미지·로그·임시 파일과 수명주기 테스트의 일회용 `runs/`는 Git에서 제외한다. 로컬 파일은 삭제하지 않는다. 수명주기 보고서의 시나리오별 결과와 환경 메타데이터는 저장한다.
- `.gitattributes`로 실험 USDA와 수정 전 소스 스냅샷의 줄바꿈 자동 변환을 막아 원본 해시를 보존한다. USD exporter가 작성한 마지막 빈 줄은 그대로 두고 해당 파일의 EOF 빈 줄 경고만 제외한다.
- 내용 불일치의 핵심 이미지 세 장은 `results/interview/evidence/capture_content/`에 원본 바이트 그대로 복사해 저장한다. 같은 폴더 README에서 원래 실행 경로·SHA256·비교 대상을 확인한다.
- 전체 캡처와 무시한 원시 로그는 로컬 실험 결과다. 다른 체크아웃에서 필요하면 [[2026-10-26 면접 준비용 Omniverse 고도화 구현]]의 스크립트로 다시 수집한다. 간헐적 내용 불일치가 같은 seed에서 항상 재현된다고 가정하지 않는다.

## 확인 방법

`git diff --cached --check`로 각 커밋의 변경을 검사하고, `scripts/check_interview_artifacts.ps1`로 문서 링크·구문을 확인한다. 커밋 후 `git status --short`로 작업 트리가 비었는지 확인한다.
