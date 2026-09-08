# meeting-summarize

> **회의 녹음을 넣으면, 녹취록과 8항목 내부 회의록이 나옵니다 — 리뷰 피드백은 규칙으로 쌓입니다.**

녹음 파일(m4a)을 주면 기기 안에서 화자 분리 녹취록(txt)을 만들고, 그 녹취록으로 `일시 · 장소 · 참석대상 · 주요 안건 · 협의 사항 · 특이사항 · Follow-Up · 소감` 8항목 회의록(md)을 씁니다. 이미 만들어진 녹취록 txt가 있으면 그것부터 시작해도 됩니다. 회의록은 **요약본**입니다 — 녹취 전문은 별도 공유하고, 회의록에는 주요 항목·논의 결론·액션만 분량 예산(A4 1~2장) 안에 담습니다. 대외 미팅이면 상대의 창업기·제품 개발 이야기를 마케팅 훅으로 남기고, 내부 회의면 안건별 결론·보류·액션 중심으로 씁니다. Follow-Up에는 상대가 기다리는 약속만 넣습니다. 저장 전에 검증 패스(작성자 체크 + 녹취 대조 서브에이전트)를 거쳐 검증 메모를 함께 보고합니다. 정리본에 대한 상사·동료 피드백을 붙여 주면 그 회의록을 고치는 동시에 다음 회의록에도 적용할 규칙으로 저장합니다.

```
녹음 파일(m4a) ─▶ 녹취록 전환(scripts/transcribe.sh, 완전 로컬) ─▶ 회의록 요약(스킬)
                    └▶ {녹음명}.txt                                  └▶ {녹음명}_회의록.md
```

## 설치

이 플러그인은 `joseph-cha-plugins` 마켓플레이스(저장소 `Joseph-Cha/lecture-analysis`)에 등록되어 있습니다.

```
/plugin marketplace add Joseph-Cha/lecture-analysis      # 이미 추가했다면: /plugin marketplace update joseph-cha-plugins
/plugin install meeting-summarize@joseph-cha-plugins
```

설치 후 Claude Code를 재시작하세요(플러그인은 시작 시 로드됩니다).

**녹음 → 녹취록 전환에 필요한 도구** (macOS Apple Silicon, 한 번만):

```bash
brew install ffmpeg whisperkit-cli
```

첫 전환 때 음성 인식 모델(약 1.6GB)과 화자 분리 모델이 자동으로 내려받아집니다(`~/Documents/huggingface/` 아래). 이후에는 78분 녹음 기준 5~10분이 걸립니다. 녹취록 txt만 쓴다면 이 도구는 필요 없습니다.

마켓플레이스 없이 쓰려면 저장소를 클론해 스킬 폴더를 개인 스킬 폴더에 링크합니다.

```bash
ln -s "$(pwd)/skills/meeting-summarize" ~/.claude/skills/meeting-summarize
```

## 사용

```
회의록 정리해 줘                                  # iCloud 회의록 폴더의 녹취록·녹음 목록을 보여주고 고르게 함
이 녹음으로 회의록 정리해 줘: ~/Downloads/xxx.m4a  # 녹취록 전환부터 시작 — 녹음 시작 시각·참석자 수를 물어봄
지리산 농부들 미팅 회의록 정리해 줘                 # 파일명·제목이 맞는 녹취록을 바로 정리
```

기본 입력 폴더는 `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/회의록` 입니다(단축어 앱이 녹음·녹취록을 내보내는 위치). 녹음만 있으면 같은 폴더에 `{녹음명}.txt`를 만들고, 정리본은 `{녹음명}_회의록.md`로 저장되며 전문이 대화에도 출력됩니다.

정리 중 한 번 확인을 요청합니다: 녹취록의 `참석자 N`을 누구로 볼지(근거 포함)와 장소, 녹음에서 전환했다면 녹음 시작 시각(m4a에는 시각 정보가 없습니다). 나머지는 자동입니다. 저장 전에 검증 패스를 돌리고, 결과(대조·수정·확인 필요 건수)를 회의록과 함께 보고합니다.

터미널에서 녹취록만 만들 수도 있습니다.

```bash
bash skills/meeting-summarize/scripts/transcribe.sh "회의.m4a" --start "2026-09-04 09:37" --speakers 4 --author 차동훈
```

### 녹취록 형식

스킬이 만들고 읽는 녹취록은 화자 분리 txt입니다. 같은 구조로 만든 파일이면 출처와 상관없이 그대로 읽습니다.

```
<제목>
YYYY.MM.DD 요일 오전|오후 H:MM ・ N분 N초
<녹음자>

참석자 1 00:00
발화 …

참석자 2 01:41
발화 …
```

### 정확도

같은 녹음의 상용 앱 녹취록과 대조한 실측(2026-09-07, 103분 내부 회의 4인): 화자 라벨 일치율 0.94, 글자 불일치율(CER) 0.16 — 화자 분리는 상용 앱 수준이고, 고유명사·숫자는 100자 중 16자가 달랐습니다. 그래서 자체 전환 녹취록으로 만든 회의록은 수치·이름에 "(확인 필요)"가 더 자주 붙습니다.

### 피드백 반영

```
아래는 회의록에 대한 피드백이야. 반영해 줘.
1) 미팅 초기 사장님의 경험·개발 이야기가 빠졌다 ...
```

회의록을 `_v2`로 고치고, 일반 규칙은 `skills/meeting-summarize/references/feedback.md`에 `F-NN` 항목으로 추가합니다. 이후 모든 회의록은 이 로그를 대조한 뒤 나옵니다. 규칙은 소스 저장소에 기록해야 하며(플러그인 캐시는 업데이트 때 덮어써집니다), 반영본은 새 버전으로 배포합니다.

## 구성

```
skills/meeting-summarize/
  SKILL.md                      절차·규칙
  scripts/transcribe.sh         녹음 → 녹취록 txt (ffmpeg → whisperkit-cli transcribe/diarize → transcript_build.py)
  scripts/transcript_build.py   전사 리포트 + 화자 구간 → 녹취록 형식(단어별 화자 배정·환각 정리·블록 분할, 표준 라이브러리만)
  scripts/transcripts.py        녹취록·녹음 목록, 일시·화자 통계(헤더 파싱), 회의록 분량·말투 점검(check)
  tests/                        transcript_build.py 단위 테스트 (python3 -m unittest discover -s skills/meeting-summarize/tests)
  references/template.md        8항목 형식과 항목별 규칙
  references/context.md         우리 측 정보(조직·구성원·사업) — 직접 편집
  references/feedback.md        리뷰 피드백 → 규칙 로그 — 자동 누적
  references/example.md         완성 예시(피드백 반영본)
```

`context.md`는 사용자가 유지보수합니다. 새 멤버·새 사업이 생기면 여기에 적어야 `참석자 N` 매핑과 "우리에게 해당되는 사항"이 정확해집니다.

## 데이터는 어디로 가나요?

- **녹음 파일은 기기 밖으로 나가지 않습니다.** 음성 인식과 화자 분리는 `whisperkit-cli`가 Mac 안에서 처리합니다(모델 다운로드 외 네트워크 사용 없음).
- 녹취록 본문(텍스트)은 회의록을 쓰는 과정에서 Claude Code를 통해 Anthropic으로 전송됩니다. 회의 상대에게 녹음·정리 사실을 알리고, 외부 공유가 부적절한 내용은 녹취록에서 잘라낸 뒤 정리를 요청하세요.
- 정리본은 내부용 문서로 상대의 리스크를 순화하지 않으므로 외부로 그대로 보내지 마세요.

## 라이선스·고지

이 저장소(스크립트·문서)는 THE GOSPEL LICENSE(`LICENSE`)를 따릅니다. 아래 도구와 모델은 **동봉하지 않으며** 사용자가 직접 설치·다운로드합니다.

- WhisperKit / `whisperkit-cli` — MIT, © 2024 argmax, inc.
- 음성 인식 모델 `argmaxinc/whisperkit-coreml` — MIT (OpenAI Whisper, MIT © 2022 OpenAI 기반)
- 화자 분리 모델 `argmaxinc/speakerkit-coreml` — 원본 가중치: pyannote `segmentation-3.0` (MIT; Plaquet & Bredin 2023, Bredin 2023), WeSpeaker VoxCeleb 기반 임베더 (CC-BY-4.0), BUT VBx 클러스터러 (Apache-2.0)
- ffmpeg — GPL-3.0-or-later(Homebrew 빌드). 이 스킬은 명령행 호출만 하며 바이너리를 재배포하지 않습니다.
