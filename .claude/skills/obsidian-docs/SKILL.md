---
name: obsidian-docs
description: 이 프로젝트에서 코드를 수정했거나, 기획/계획을 변경했거나, 새롭게 알게 된 사실(API 동작, 버그 원인, 환경 이슈, 실험 결과 등)이 생겼을 때 반드시 사용. docs/ 폴더에 Obsidian 형식의 주제별 md 노트로 기록한다.
---

# Obsidian Docs (문서화 규칙)

코드 수정, 기획 변경, 새로 알게 된 점은 **모두** `docs/`에 Obsidian 노트로 남긴다.

## 핵심 원칙: 노트 하나 = 주제 하나

- 노트 하나에는 **주제를 하나만** 담는다. 여러 주제가 섞이면 나누고 `[[링크]]`로 연결한다.
- 같은 주제의 노트가 이미 있으면 **새로 만들지 말고 그 노트를 업데이트한다.** 먼저 `docs/`를 검색한다.
- 날짜별 작업 일지는 `progress`로 남기되, 실제 내용은 주제 노트에 쓰고 일지에서는 링크만 건다.

## 폴더와 노트 종류

| 폴더 | 종류(`type`) | 언제 쓰나 |
|---|---|---|
| `docs/changes/` | `change` | 코드 수정(무엇을, 왜, 영향 범위, 검증 방법) |
| `docs/decisions/` | `decision` | 기획·계획·설계 변경(배경, 선택지, 결정, 이유) |
| `docs/learnings/` | `learning` | 새로 알게 된 것(Kit API 동작, 버그 원인, 환경 이슈, 실험 결과) |
| `docs/topics/` | `topic` | 오래 유지할 설명 문서(아키텍처, 모듈 설명, 실행 방법) |
| `docs/progress/` | `progress` | 날짜별 Done / Blocked / Next / Evidence 일지 |
| `docs/` 루트 | `index` | `00_Index.md` (전체 목차, MOC) |

## 파일 이름

- 사람이 읽을 수 있는 제목을 그대로 쓴다. Obsidian은 파일 이름으로 링크하므로 **프로젝트 전체에서 이름이 겹치지 않아야 한다.**
- `changes`, `decisions`, `progress`는 앞에 날짜를 붙인다: `2026-10-22 ProductTracker 상태 머신 도입.md`
- `learnings`, `topics`는 날짜 없이 주제로: `Kit 109 Viewport 프레임 캡처.md`
- 파일 이름에 `/ \ : * ? " < > | # ^ [ ]`는 쓰지 않는다.

## 노트 형식

```markdown
---
type: change | decision | learning | topic | progress
date: YYYY-MM-DD
tags: [visiontwin, 관련-모듈]
related: ["[[다른 노트]]"]
---

# 제목

## 요약
한두 문장.

## 내용
(change: 변경 내용 / 이유 / 영향 파일 / 검증 방법)
(decision: 배경 / 선택지 / 결정 / 이유 / 영향)
(learning: 현상 / 원인 / 근거(로그, 문서 링크) / 적용 방법)

## 관련
- [[관련 노트]]
```

- 다른 노트는 `[[노트 이름]]`, 특정 섹션은 `[[노트 이름#섹션]]`으로 링크한다.
- 코드 파일은 상대 경로 마크다운 링크로 쓴다: `[product_tracker.py](../../exts/...)`.
- 증거(로그 일부, 스크린샷 `![[파일.png]]`, 테스트 결과)를 붙인다. 추측은 추측이라고 표시한다.
- 태그는 소문자-kebab-case: `#kit`, `#vision`, `#tracker`, `#build`, `#experiment`.

## 마무리

- 새 노트를 만들면 `docs/00_Index.md`의 맞는 섹션에 `[[링크]]`를 추가한다.
- 작업이 끝날 때 오늘 날짜의 `progress` 노트에 그 작업을 링크한다.
