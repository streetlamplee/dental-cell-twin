---
type: learning
date: 2026-10-21
tags: [visiontwin, kit, build]
related: ["[[2026-10-21 Kit 110.4.0 kit_base_editor 기반 앱 구성]]", "[[cmd PATH 빈 항목 문제]]"]
---

# kit-app-template 비대화형 생성 (replay)

## 요약
`repo.bat template new`와 `template list`는 대화형 콘솔 UI(prompt_toolkit)를 쓰기 때문에 콘솔이 없는 환경에서는 `NoConsoleScreenBufferError`로 실패한다. 대신 `repo.bat template replay <toml>`을 쓰면 프롬프트 없이 앱이나 확장을 만들 수 있다.

## 내용
- **EULA:** 처음 실행하면 NVIDIA 약관 동의를 묻는다. 동의하면 루트에 `.omniverse_eula_accepted.txt`가 생기고, 이후에는 묻지 않는다(git 제외 파일). 2026-10-21 사용자가 동의했다.
- **replay 파일 형식:** `[템플릿키]` 섹션 아래에 변수를 적는다. 템플릿 키는 `_repo/deps/kit_core_templates/core_templates.toml`에서 확인한다.
  ```toml
  [kit_base_editor]
  application_name = "visiontwin.app"
  application_display_name = "VisionTwin"
  version = "0.1.0"
  ```
- 이 프로젝트의 replay 파일: `scripts/replay/visiontwin_app.toml`, `scripts/replay/visiontwin_factory_ext.toml`
- 실행: `.\scripts\new_from_template.ps1 -PlaybackFile scripts\replay\<file>.toml`
- **빌드 산출물은 소스와 링크로 연결된다:** `_build/.../exts/visiontwin.factory/visiontwin`은 `source/...`를 가리키므로, Python이나 `extension.toml`을 고쳐도 다시 빌드할 필요가 없다. 새 확장이나 앱을 추가할 때만 빌드한다.

## 관련
- [[스크립트 목록]]
