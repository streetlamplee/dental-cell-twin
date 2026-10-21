---
type: learning
date: 2026-10-21
tags: [visiontwin, build, windows]
related: ["[[스크립트 목록]]"]
---

# cmd PATH 빈 항목 문제

## 현상
Agent(Claude Code) 셸에서 `repo.bat`을 실행하면 다음 오류가 난다.
```
'powershell' is not recognized as an internal or external command
```
`cmd /c where powershell`조차 실패한다.

## 원인
이 실행 환경에서 `cmd.exe`에 넘어가는 `PATH`가 `;`(빈 항목)으로 시작한다. 이 상태에서는 cmd가 PATH 검색에 실패한다. `set PATH=%PATH:~1%`로 맨 앞 `;`를 지우면 정상 동작하는 것을 확인했다.

## 적용
`scripts/_common.ps1`이 시작할 때 PATH의 빈 항목을 모두 제거한다. 모든 스크립트가 이 파일을 dot-source 하므로 따로 신경 쓸 필요가 없다. 일반 사용자 터미널에는 영향이 없다(빈 항목을 지우기만 함).

## 관련
- [[kit-app-template 비대화형 생성 (replay)]]
