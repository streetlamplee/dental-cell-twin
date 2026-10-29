---
title: 2026-10-26 면접 준비용 Omniverse 고도화 구현
type: request
created: 2026-10-26
tags: [visiontwin, omniverse, interview, verification]
related: ["[[면접 준비용 Omniverse 고도화 작업 계획]]", "[[시뮬레이션 시각과 캡처 추적]]", "[[Kit 비동기 작업 수명주기]]", "[[USD 합성과 변환 계층]]", "[[USD 인스턴싱과 개별 편집]]"]
---

# 2026-10-26 면접 준비용 Omniverse 고도화 구현

## 상태

**2026-10-29 계획한 구현·실험·회귀 검증 완료.** `results/interview/verification.json`의 `passed: true`를 확인했다. 전체 core 107개·Kit 내부 5개 테스트, 통제된 box/crown 네 실행, native 전환·LOD·trace 비활성 호환성을 검증했다. 첫 재개 배치의 실패와 native 캡처 내용 불일치의 미해결 원인은 보존한다. 이 완료는 정의한 검증 범위에 해당하며 운영 전체의 이미지 내용 정합을 보장한다는 뜻은 아니다. 기존 제출 포트폴리오 이후의 작업이다.

## 실행 진입점

- 기준·회귀: `scripts/run_interview_baseline.ps1`.
- 수정 전 소스 보존: `scripts/snapshot_interview_source.ps1`.
- 시간 비교: `scripts/run_interview_timing.ps1`.
- 이미지 내용: `scripts/probe_frame_content.ps1`.
- 수명주기: `scripts/verify_kit_lifecycle.ps1`.
- USD 합성: `scripts/verify_usd_composition.ps1`.
- 인스턴싱 CPU/편집: `scripts/benchmark_usd_instancing.ps1`.
- 인스턴싱 Kit 렌더: `scripts/benchmark_interview_render.ps1`.
- 결과 집계: `scripts/summarize_interview_results.ps1`.
- 실제 native pending 전환 검증: `scripts/verify_pending_lifecycle.ps1`.
- LOD 렌더 비교: `scripts/benchmark_interview_lod.ps1`.
- 결과 최종 감사: `scripts/verify_interview_results.ps1`.
- 미완료 검증 재개: `scripts/resume_interview_measurements.ps1`.
- 저장 이미지 중복 감사: `scripts/diagnose_capture_duplicates.ps1`.
- trace 비활성 호환성: `scripts/verify_trace_disabled.ps1`.
- Kit 주 창 상태 진단: `scripts/inspect_kit_window.ps1`.

## 2026-10-29 재개 중 발견한 회귀 실패

`results/interview/baseline/after_20261029_210305/`에서 box 첫 실행은 30/30, 두 번째는 29/30이었다. 두 번째 실행의 정상 제품 21번을 결함으로 배출했다. 기대 라벨과 동일한 판정이 나올 때까지 반복한 결과로 대체하지 않는다.

- 요청/반환 SWH는 모두 2517로 일치했다. 직전 제품 20번의 요청/반환 SWH는 2427이다.
- 두 제품의 RGB digest는 `874e0092d4a6eed84c5a004f228c8d1d`로 같았고 저장 PNG도 바이트까지 일치했다.
- 20번 이미지에는 주황색 제품이 있으며, 21번의 정상 기준 이미지에는 파란색 제품이 있다. 검사기는 받은 주황색 이미지를 실제로 결함 판정했다.
- 따라서 프레임 번호 일치만으로 이미지 내용과 제품 상태의 대응을 보장하지 못한 사례다. native 렌더러·readback·예약 경로 중 정확한 원인은 확인하지 못했다. 현재 런타임 변경이 원인이라고 단정하지 않는다.
- 증거: `results/interview/capture_duplicate_audit.json`, 해당 두 run의 `trace.csv`, `inspections.csv`, `frames/P_0020.png`, `frames/P_0021.png`.
- `diagnose_capture_duplicates`는 저장 결과의 오프라인 감사다. 기대 라벨은 분석에만 사용하며 실행 중 검사기의 입력·판정에 넣지 않는다. 동일 제품이 주기적으로 지나가면 이미지가 같을 수 있으므로 모든 중복을 오류로 분류하지 않는다.

검증 실행기는 독립 항목을 끝까지 수집하고 단계별 실패를 `results/interview/resume_status.json`에 보존하도록 수정했다. 기준 실행은 `-BatchDirectory`로 성공 종료한 개별 실행을 재사용하되, 설정·소스 해시가 일치할 때만 허용한다. 제품 결과 차이는 숨기지 않고 box 비교 실패 후 crown을 계속 수집한다. 전후 비교도 네 쌍 전체를 기록한 뒤 실패한다.

## 2026-10-26 기준과 초기 검증

- 변경 전 순수 Python 테스트: 99 passed. 런타임 1차 통합 후 전체 106 passed.
- 확장 종료 후 속성이 비워진 객체를 사용하는 회귀 사례를 추가한 관련 테스트: 9 passed.
- box/crown 각 30개 기준 실행 두 번: 제품 판정·분류 30/30, 결정론적 결과 동일. 기준 결과는 `results/interview/baseline/before_20261026_224621/`에 보존했다.
- USD 합성 최소 예제: 변환 충돌·부모 분리, 레이어 복원, VariantSet, 단위/축 처리, 원본 해시 불변 검증 통과. Kit에서의 추가 렌더 검증은 별도 기록한다.

## 실험 중 확인한 실행 환경 이슈

- 첫 기준 실행 중 소스 파일 추가로 Kit가 확장을 자동 재시작해 실행이 중단됐다. 이후 자동 실험에 `/app/extensions/fsWatcherEnabled=false`를 적용했다.
- 외부 실행기에서 프로세스 종료 코드가 null로 수집되는 문제는 실행 직후 프로세스 handle을 보유하도록 수정했다. 수정 후 box 기준 실행의 exit code 0을 확인했다.
- 위 중단 실행은 정상 기준 결과에 포함하지 않는다.

## 수명주기 재현과 수정

- 수정 전 Extension·frame provider 원문과 SHA256은 `results/interview/source_before/20261026_225638/`에 보존했다.
- 해당 원문을 Kit의 별도 모듈로 로드하고 캡처 API 경계에서 오류 콜백을 보류한 뒤 Reset 후 전달했다. 새 실행의 제품 ID 1이 unknown으로 바뀌는 현상이 10/10회 재현됐다. 실제 GPU 지연을 기다린 우연적 재현과 구분한 결정론적 콜백 주입 실험이다.
- generation을 먼저 무효화하고 정상·오류 콜백을 모두 검사하도록 변경했다. 캡처 요청은 소유 task·한 번의 종료·native 콜백 차단 상태로 관리한다.
- Kit에서 Extension 비활성화 후 이전 IExt 객체의 `_sim` 속성 접근이 실패하는 사례도 관측했다. 폐기 결과를 기록하는 경로가 닫힌 확장 객체를 읽지 않도록 요청 당시 시각을 보존하고 닫힌 trace에는 쓰지 않도록 수정했다.
- 수정 후 Reset·Build Scene·외부 Stage 변경·확장 토글·실제 pending 캡처 취소를 각각 10회, 총 50회 검증했다. 구세대 콜백 적용 0건이며 pending 요청·소유 task 정리 확인이 통과했다. 결과는 `results/interview/lifecycle/after_20261026_230958/report.json`이다.

## 프레임 내용 진단

- 진단 전용 Stage에 12개 발광 마커를 두고, transform으로 update 번호의 비트를 표시했다. 검사기·학습 모델에는 진단 이미지를 전달하지 않는다.
- 검정/흰색 기준을 먼저 캡처해 비트별 대비를 검증한 뒤, 요청 SWH 번호·반환 SWH 번호·이미지 디코딩 번호를 비교했다.
- 30개 샘플에서 내용 불일치·디코딩 불가·캡처 오류 모두 0건이었다. 결과는 `results/interview/frame_content/20261026_231452/report.json`이다. 이 진단 결과가 기존 모든 stale 사례의 원인을 해명한 것은 아니다.
- 첫 진단 시 보조 뷰포트 초기화 중 D3D native 충돌이 발생했다. 메인 뷰포트의 실제 프레임을 기다린 뒤 생성하도록 바꾼 재실행은 통과했다. 앱 update 대기만으로 renderer 준비를 보장한다고 가정하지 않는다.

## 인스턴싱 CPU 측정

- 실제 crown 자산을 10/50/100개 배치하고 세 구성별 새 프로세스에서 3회씩, 총 27개 USD open·RSS 샘플을 확보했다.
- instance proxy 직접 편집 거부와 한 개만 인스턴싱 해제한 후 재질 바인딩·다른 인스턴스 유지 동작을 확인했다.
- 초기 결과에서 로딩 시간의 일관된 개선은 확인되지 않았다. Kit 렌더 측정을 마친 뒤 적용 범위를 판단한다. OS 파일 캐시를 초기화한 측정으로 표현하지 않는다.

## 시간·부하 비교

- `results/interview/timing/20261026_231543/`에서 같은 seed의 box 6개를 조건별 3회 실행했다. 7개 조건, 총 21회다.
- 고정 스텝/실제 경과시간 × 가벼운/무거운 메인 뷰포트의 네 정상 조건과 0.5초 전달 지연 조건을 비교했다. 실제 경과시간 모드에서도 이번 표본의 판정·분류 오류나 지연 판정은 관측되지 않았다.
- 실제 시간 제한과 업데이트 예산 초과 조건은 각각 매 실행 6건의 타임아웃과 6건의 fail-safe 배출을 기록했다. 정상 정확도 비교 표본과 구분한다.
- 캡처 서비스 지연에는 기본 `wait_for_result()`의 완료 후 2 update 대기가 포함된다. GPU 단독 처리시간으로 표현하지 않는다.
- 조건별 수치와 원시 추적은 `results/interview/report.md`, `report.json`, 각 run의 `trace.csv`에서 확인한다. 같은 제품을 반복한 것이므로 독립된 결함 표본 수가 늘었다고 해석하지 않는다.

## 결과와 남은 일

### 완료 결과

| 항목 | 실제 완료한 내용 |
|---|---|
| 변경 전 기준 | box/crown 각 30개 × 2회. 모두 30/30, 반복 결과 동일 |
| 런타임 구현 | generation 무효화, task 소유·취소, 닫힌 확장 객체 접근 방지, 시간/업데이트 타임아웃 구분, trace·RTF 기록 |
| 수명주기 | 수정 전 오류 콜백 오적용 10/10 재현. 수정 후 구세대 콜백 40건 차단 + 실제 pending Reset 10건, 총 50건 통과 |
| 추가 native 수명주기 | 2026-10-29 Reset·Build·외부 Stage·확장 토글 각 10회, 총 40회 통과. 전환 전 native 콜백 대기 40/40, 전환 후 전달·pending·task 0. 최종 배치에서 중복 업데이트 10회 추가 확인 |
| 프레임 내용 | 진단용 30장 모두 요청 상태와 일치. 오류·디코딩 불가 0 |
| 시간·부하 | 7조건 × 3회 = 21회. 네 정상 조건과 전달 지연 조건 모두 6/6. 두 타임아웃 조건은 매회 6건 fail-safe |
| USD 합성 | 최소 예제의 5개 검증 통과 및 Kit 열기·렌더 확인 |
| 인스턴싱 | CPU 27개 샘플, 고정 960×640 Kit 렌더 27회, 개별 편집 제약 확인 |
| LOD | LOD 0/3/4의 50개 인스턴스 렌더 각 3회, 총 9회 완료. 품질 표는 기존 CAD 리포트 재사용 |
| 수정 후 기준 | 통제된 새 배치의 box/crown 각 30개 × 2회 모두 30/30. 반복 비교 및 변경 전후 네 쌍의 제품별 결과 동일. 첫 재개 배치의 실패는 별도 보존 |
| 코드 검사 | 2026-10-29 전체 core 107 passed, Kit 내부 5 tests OK, 시작 검사 포함 2개 Extension 테스트 프로세스 exit 0 |
| 진단 비활성 호환성 | trace=false 비전 검사 6/6, 기존 check_run 통과, trace.csv 미생성·timing summary 유지 |
| 최종 결과 감사 | `scripts/verify_interview_results.ps1` 통과, `results/interview/verification.json`의 passed=true |

고정 스텝 RTF 중앙값은 가벼운 뷰포트 약 1.013, 무거운 뷰포트 약 0.613이었다. 캡처 p95 중앙값은 각각 약 128 ms, 212 ms다. 실제 경과시간 모드의 RTF 약 1은 시계 정의의 영향도 있으며 실기 연동 성능 보장의 근거가 아니다.

인스턴싱 100개 구성에서 CPU USD RSS 중앙값은 일반 참조 약 67.4 MiB, 인스턴스 약 65.6 MiB였다. Kit update p50은 두 구성 모두 약 10.2 ms로, 이번 범위의 뚜렷한 프레임 개선은 관측되지 않았다. GPU 단독 시간·프로세스 전용 VRAM·콜드 캐시 결과로 표현하지 않는다. 운영 재질 편집 흐름은 유지하고 인스턴싱 비교는 독립 실험 Stage에서 관리한다.

### 중단 이력과 최종 증거

- 진행하던 배치: `results/interview/baseline/after_20261026_233733/crown_1/`. 자동 실행기를 먼저 중단하고 Kit 종료를 요청했다. 이 crown 실행을 정상 완료 회귀로 집계하지 않는다.
- 중단 기록: `results/interview/interrupted.json`.
- 2026-10-29 첫 재개 배치 `after_20261029_210305`는 box 29/30 사례와 crown 125건의 capture update-budget 초과를 보존한다. crown은 제품 6번부터 캡처가 완료되지 않았고 25개 제품을 fail-safe 배출했다. 원인 관측 없이 정상 실행으로 대체하지 않는다.
- 설치된 Kit의 최소화·비가시 상태 렌더 중지 설정을 자동 실행에서 false로 고정했다. 프로세스 메타데이터에 `automation_args`를 저장한다. 일반 GUI 설정은 유지하며, 첫 실패의 직접 원인이라고 확정하지 않는다.
- 통제된 새 배치는 `results/interview/baseline/after_20261029_211839/`다. 전체 네 번과 전후 네 쌍 비교가 통과했다. 비교 결과는 `results/interview/baseline/comparison.json`이다. crown은 각각 151/152장 캡처·기존 재촬영 1/2회·타임아웃 0건이었다. 제품별 최종 판정·경로·시뮬레이션 결과의 일치와 캡처 재시도 횟수의 일치를 구분한다.
- native 전환 1차 결과: `results/interview/lifecycle_pending/20261029_211207/report.json`. 중복 업데이트 검사까지 추가한 최종 결과는 `results/interview/lifecycle_pending/20261029_213205/report.json`이다. 확장 재활성화 후 Start를 두 번 호출하고 update 20회당 simulation 20 step을 10번 검증했다. 각 simulation 시간 증분은 1/3초였다.
- LOD 결과: `results/interview/lod/20261029_211444/manifest.json`, 각 `render.json`, `quality_reference.md`.
- trace 비활성 호환성 결과: `results/interview/compatibility/20261029_213459/report.json`.
- 전체 core 로그: `logs/test_core_20261029_211744.log`. Kit 테스트 로그: `logs/test_ext_20261029_211827.log` 및 `_testoutput/`.
- 최종 감사: `results/interview/verification.json`. 측정 범위, 선택한 원시 결과, 코드 테스트 증거, 과거 내용 불일치 1건과 한계를 함께 기록한다.
- `results/interview/resume_status.json`은 첫 재개 시도의 실패 기록이다. 새 기준 재검증과 추가 검사를 마친 뒤의 최종 통과 여부는 `verification.json`을 따른다. 실패 이력을 삭제하거나 성공으로 바꾸지 않았다.
- 계획한 미실행 검증은 남아 있지 않다. native 이미지 내용 불일치 원인 조사는 아래의 후속 과제로 남긴다.

### 전체 검증 재실행 명령

```powershell
.\scripts\resume_interview_measurements.ps1
```

이 명령은 새 after 기준 → 변경 전후 비교 → 이미지 중복 감사 → native pending 40회 → LOD 렌더 9회 → core/Extension 테스트 → trace 비활성 호환성 → 문서·구문 검사 → 집계·최종 감사 순서다. 완료한 시간 21회·인스턴싱 27회는 재사용한다. 이미 측정한 항목만 확인할 때는 각 검증·집계 스크립트를 사용한다.

결과 진입점은 `results/interview/report.md`와 `report.json`이다. 미실행·중단 항목은 통과로 표시하지 않는다.

## 코드·재현·증거 찾기

| 주제 | 확인할 구현 | 재현 명령 | 확보한 원시 결과 |
|---|---|---|---|
| 시간·요청 추적 | `core/runtime.py`, `extension.py` | `scripts/run_interview_timing.ps1` | `results/interview/timing/20261026_231543/`의 trace·summary·timing |
| 수명주기 | `runtime_session.py`, `capture_runtime.py` | `scripts/verify_kit_lifecycle.ps1`, `scripts/verify_pending_lifecycle.ps1` | `lifecycle/after_20261026_230958/`, `lifecycle_pending/20261029_213205/` |
| USD 합성 | `scripts/verify_usd_composition.py` | `scripts/verify_usd_composition.ps1` | `composition/20261026_225331/`의 USDA·property stack·보고서 |
| 인스턴싱 | `scripts/benchmark_usd_instancing.py` | `scripts/benchmark_usd_instancing.ps1`, `scripts/benchmark_interview_render.ps1` | `instancing/20261026_230542/`의 CPU 27개·Kit 27회 |
| LOD | `scripts/prepare_interview_lod.py` | `scripts/benchmark_interview_lod.ps1` | `lod/20261029_211444/`의 Kit 9회·기존 품질 참조표 |
| 내용 불일치 | `scripts/diagnose_capture_duplicates.py` | `scripts/diagnose_capture_duplicates.ps1` | `capture_duplicate_audit.json`과 box 실패 이미지·trace |

표의 런타임 파일 위치는 `source/extensions/visiontwin.factory/visiontwin/factory/` 기준이며, 원시 결과 축약 경로는 `results/interview/` 기준이다. 시간 측정은 [[시뮬레이션 시각과 캡처 추적]], 수명주기는 [[Kit 비동기 작업 수명주기]], 합성과 인스턴싱 판단은 [[USD 합성과 변환 계층]]·[[USD 인스턴싱과 개별 편집]]에서 이어 읽는다.

## 내용 정합에서 남은 조사 절차

공유할 핵심 실패·대조 이미지는 `results/interview/evidence/capture_content/`에 저장했다. 전체 캡처·수명주기 테스트의 일회용 실행 폴더와 버전 관리 범위는 [[Git 검증 산출물 관리]]를 따른다. 원래 로컬 실험 파일은 유지한다.

1. 저장된 실패 제품 20/21의 요청·수신·판정과 이미지를 출발점으로 삼는다. seed를 고정해도 이 문제가 매번 재현된다고 가정하지 않는다.
2. 최소화·비가시 렌더 중지 정책을 고정하고 실제 검사 뷰포트의 `updates_enabled`·진행 프레임과 native 콜백 수신 여부를 함께 계측한다. 주 창 상태 스냅샷만으로 보조 뷰포트의 진행을 대신 판단하지 않는다.
3. 현재 30장 진단보다 긴 실행과 실제 CAD·카메라 이동 부하를 가진 별도 진단 Stage에서 프레임 패턴을 검사한다. 패턴을 운영 검사 ROI나 학습 입력에 넣지 않는다.
4. 정상적인 동일 이미지가 나오는 반복 배치를 대조군으로 둔다. 모든 digest 중복을 unknown 처리하거나 기대 라벨로 판정을 교정하는 방식으로 성공률을 만들지 않는다.
5. 이 증거가 모이기 전에는 native 내용 불일치의 원인 해결·운영 전체의 결정론적 보장을 주장하지 않는다. 이번 완료 범위는 요청 추적·무효화·실패 처리·USD 비교와 정의된 조건의 검증이다.
