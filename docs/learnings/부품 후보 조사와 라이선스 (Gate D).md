---
type: learning
date: 2026-10-22
tags: [visiontwin, cad, license, gate-d, day6]
related: ["[[2026-10-22 실제 CAD 부품을 제품으로 사용]]", "[[2026-10-22 Day6 실제 CAD 부품 제품]]"]
---

# 부품 후보 조사와 라이선스 (Gate D)

## 결론
**Gate D 통과.** FreeCAD-library의 **KFL08 플랜지 베어링**(작성자 hasecilu, **CC-BY-3.0**)을 선택했다. 어셈블리 구조라서 "베어링 인서트 누락" 결함이 위에서 보인다.

## 출처별 라이선스 확인 (2026-10-22)
| 출처 | 라이선스 | 판단 |
|---|---|---|
| NIST MBE PMI CAD 모델 | NIST 직원 저작물. 미국 내 저작권 없음. 복제, 수정, 재배포 가능. NIST 출처 표기 요청, 수정본은 변경 사항 표시 | 사용 가능. 다만 STEP은 **단일 가공 부품**이고, 어셈블리는 네이티브 CAD로만 제공 |
| KiCad 3D 모델 (`kicad-packages3D`) | 저장소 LICENSE.md는 CC-BY-SA 4.0 + 예외, **파일 헤더는 GPL-3.0-or-later + 예외** | **불명확 → 커밋하지 않음**. 또한 DIP-8은 단일 솔리드 |
| FreeCAD-library | `LICENSE-Assets`: 모든 부품과 STEP 내보내기가 **CC-BY-3.0 Unported**. 작성자는 git 기록에 있음 | ✅ 사용 |

- KiCad 3D 모델 파일은 Git LFS에 있다. 일반 raw URL은 404가 나고, GitLab API의 `.../repository/files/<path>/raw?ref=master&lfs=true`로 받아야 한다.

## 후보 구조 (`scripts/inspect_step.ps1`)
| 부품 | 구조 | 누락 결함 가능성 | 상태 |
|---|---|---|---|
| **KFL08** | 어셈블리 35 솔리드: Case, Rings, Seals, Balls ×7, Cages, Rivets, Set screws | 베어링 인서트(Rings+Seals+Balls+Cages+Rivets)를 빼면 보어가 비어 보임 | **selected** |
| KP08 | 같은 베어링 인서트, 필로우 블록 하우징 | 가능 | candidate (예비) |
| SC8UU | Case + 내부 부싱 3 솔리드 | 부싱이 케이스 안에 있어서 위에서 안 보임 | rejected |
| SK08, L-plate | 단일 솔리드 | 불가 | rejected |
| ZZ/2RS 볼베어링 | 실드가 볼을 덮음 | 위에서 안 보임 | 검토 제외 |

## CC-BY-3.0 의무와 적용
- 작성자, 제목, URI, 라이선스 표기 → `assets/parts/LICENSES.md`
- 수정본(변환, 배율, 재도색, 인서트 제거)은 변경 사항을 명시하고, 원작자가 이 프로젝트를 보증하지 않는다고 적는다.
- 원본 STEP은 수정하지 않고 커밋한다(SHA256은 `sources.json`, 특정 커밋에 고정한 URL).
