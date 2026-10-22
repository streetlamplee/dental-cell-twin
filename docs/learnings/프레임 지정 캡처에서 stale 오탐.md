---
type: learning
date: 2026-10-22
tags: [visiontwin, capture, bug, day6]
related: ["[[렌더 지연과 프레임 지정 캡처]]", "[[검사 카메라 프레임 캡처 (Gate B)]]"]
---

# 프레임 지정 캡처에서 stale 오탐

## 현상
KFL08 평가 run에서 정상품 #31이 "stale frame (identical to previous capture)"으로 unknown 처리됐고, fail-safe로 배출됐다(분류 39/40). #30과 #31은 **둘 다 frame_offset = 0**, 즉 요청한 프레임을 정확히 캡처했다.

## 원인
고정 dt와 일정한 투입 간격 때문에 연속된 두 제품이 같은 위치에서 찍힌다. 같은 형상의 정상품이고 주변 물체의 상대 위치까지 같으면 **이미지가 바이트 단위로 같을 수 있다.** "직전 캡처와 같음 = 렌더가 멈춤"이라는 가정은 프레임 번호를 검증할 수 없던 Day 3 방식에서만 맞았다.

Day 4 사용자 GUI run에서 나온 stale 1건(#2)도 같은 종류의 오탐이었을 가능성이 크다(추정).

## 해결
- 프레임 번호가 검증된 경우(`frame_offset == 0`)에는 같은 이미지라도 정상으로 판정한다(카운트만 남긴다).
- 프레임 번호를 알 수 없을 때(`frame_offset is None`)만 stale을 unknown으로 처리한다.
- 수정 후 KFL08 평가 run: 40/40.
