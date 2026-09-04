# meeting-summarize

> **회의 녹취록을 넣으면, 8항목 내부 회의록이 나옵니다 — 리뷰 피드백은 규칙으로 쌓입니다.**

화자 분리 녹취록(txt)을 주면 `일시 · 장소 · 참석대상 · 주요 안건 · 협의 사항 · 특이사항 · Follow-Up · 소감` 8항목 회의록을 씁니다. 상대의 창업기·제품 개발 이야기는 마케팅 자산으로 반드시 남기고, Follow-Up에는 상대가 기다리는 약속만 넣습니다. 정리본에 대한 상사·동료 피드백을 붙여 주면 그 회의록을 고치는 동시에 다음 회의록에도 적용할 규칙으로 저장합니다.

## 설치

이 플러그인은 `joseph-cha-plugins` 마켓플레이스(저장소 `Joseph-Cha/lecture-analysis`)에 등록되어 있습니다.

```
/plugin marketplace add Joseph-Cha/lecture-analysis      # 이미 추가했다면: /plugin marketplace update joseph-cha-plugins
/plugin install meeting-summarize@joseph-cha-plugins
```

설치 후 Claude Code를 재시작하세요(플러그인은 시작 시 로드됩니다).

마켓플레이스 없이 쓰려면 저장소를 클론해 스킬 폴더를 개인 스킬 폴더에 링크합니다.

```bash
ln -s "$(pwd)/skills/meeting-summarize" ~/.claude/skills/meeting-summarize
```

## 사용

```
회의록 정리해 줘                       # iCloud 회의록 폴더의 녹취록 목록을 보여주고 고르게 함
지리산 농부들 미팅 회의록 정리해 줘     # 파일명·제목이 맞는 녹취록을 바로 정리
이 파일 정리해 줘: ~/Downloads/xxx.txt  # 다른 경로도 가능
```

기본 입력 폴더는 `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/회의록` 입니다(단축어 앱이 클로바노트 녹취록을 내보내는 위치). 정리본은 원본과 같은 폴더에 `{원본명}_회의록.md`로 저장되고, 전문이 대화에도 출력됩니다.

정리 중 한 번 확인을 요청합니다: 녹취록의 `참석자 N`을 누구로 볼지(근거 포함)와 장소. 나머지는 자동입니다.

### 피드백 반영

```
아래는 회의록에 대한 피드백이야. 반영해 줘.
1) 미팅 초기 사장님의 경험·개발 이야기가 빠졌다 ...
```

회의록을 `_v2`로 고치고, 일반 규칙은 `skills/meeting-summarize/references/feedback.md`에 `F-NN` 항목으로 추가합니다. 이후 모든 회의록은 이 로그를 대조한 뒤 나옵니다.

## 구성

```
skills/meeting-summarize/
  SKILL.md                    절차·규칙
  scripts/transcripts.py      녹취록 목록·일시·화자 통계(헤더 파싱)
  references/template.md      8항목 형식과 항목별 규칙
  references/context.md       우리 측 정보(조직·구성원·사업) — 직접 편집
  references/feedback.md      리뷰 피드백 → 규칙 로그 — 자동 누적
  references/example.md       완성 예시(피드백 반영본)
```

`context.md`는 사용자가 유지보수합니다. 새 멤버·새 사업이 생기면 여기에 적어야 `참석자 N` 매핑과 "우리에게 해당되는 사항"이 정확해집니다.

## 데이터는 어디로 가나요?

녹취록 본문은 Claude Code를 통해 Anthropic으로 전송됩니다. 회의 상대에게 녹음·정리 사실을 알리고, 외부 공유가 부적절한 내용은 녹취록을 내보내기 전에 잘라내세요. 정리본은 내부용 문서로 상대의 리스크를 순화하지 않으므로 외부로 그대로 보내지 마세요.
