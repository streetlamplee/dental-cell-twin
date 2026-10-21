# VisionTwin 프로젝트 규칙

계획서: [VisionTwin_7Day_Agent_Plan.md](VisionTwin_7Day_Agent_Plan.md)

항상 지킬 규칙(세부 내용은 각 skill 참고):

1. **빌드/테스트/실행은 스크립트로** — `scripts/`에 있는 관련 스크립트를 먼저 찾아서 쓰고, 없으면 만들어 저장한 뒤 실행한다. 스크립트 하나는 목적 하나, 인자가 많은 만능 스크립트는 만들지 않는다. → skill `script-workflow`
2. **모든 변경과 새로 알게 된 점은 docs에 기록** — 코드 수정, 기획 변경, 새로 알게 된 점을 `docs/`에 Obsidian 노트(노트 하나 = 주제 하나)로 남긴다. → skill `obsidian-docs`
