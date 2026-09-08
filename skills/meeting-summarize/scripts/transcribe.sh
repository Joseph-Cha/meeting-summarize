#!/bin/bash
# 녹음(m4a 등) → 화자 분리 녹취록 txt. 완전 로컬(오디오는 기기 밖으로 나가지 않는다).
#   ffmpeg(16kHz mono wav) → whisperkit-cli transcribe(ASR, 단어 타임스탬프) → whisperkit-cli diarize(화자 분리)
#   → transcript_build.py(병합·정리·형식) → <녹음 폴더>/<녹음명>.txt
# 사용: transcribe.sh <녹음 파일> [--start "YYYY-MM-DD HH:MM"] [--speakers N] [--author 이름] [--title 제목]
#                    [--out 경로] [--force] [--work DIR] [--model 이름]
#   --start    녹음 시작 시각. 없으면 파일 생성 시각−길이로 추정하고 헤더에 "(시작 시각 추정)" 표시
#   --speakers 참석자 수(아는 경우 지정 권장). 없으면 자동 추정
#   --author   녹음자(헤더 3행, 기본 $USER_NAME 또는 "녹음자")
#   --model    WhisperKit 모델(기본 large-v3-v20240930_turbo). 첫 실행 때 약 1.6GB + 화자 분리 모델 자동 다운로드
# 종료 코드: 0 성공 / 1 처리 실패 / 2 사용법·의존성·기존 파일
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
die() { echo "오류: $1" >&2; exit "${2:-1}"; }

[ $# -ge 1 ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
AUDIO="$1"; shift
START=""; SPEAKERS=""; AUTHOR="${USER_NAME:-녹음자}"; TITLE=""; OUT=""; FORCE=0; WORK=""; MODEL="large-v3-v20240930_turbo"
while [ $# -gt 0 ]; do
  case "$1" in
    --start) START="$2"; shift 2 ;;
    --speakers) SPEAKERS="$2"; shift 2 ;;
    --author) AUTHOR="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --work) WORK="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) die "알 수 없는 인자: $1" 2 ;;
  esac
done
[ -f "$AUDIO" ] || die "녹음 파일 없음: $AUDIO" 2
for t in ffmpeg ffprobe whisperkit-cli python3; do
  command -v "$t" >/dev/null || die "$t 가 없습니다. 설치: brew install ffmpeg whisperkit-cli" 2
done
whisperkit-cli --help 2>/dev/null | grep -q "diarize" || die "whisperkit-cli 에 diarize 가 없습니다(1.1.0 이상 필요): brew upgrade whisperkit-cli" 2

stem="$(basename "${AUDIO%.*}")"
[ -n "$TITLE" ] || TITLE="$stem"
[ -n "$OUT" ] || OUT="$(cd "$(dirname "$AUDIO")" && pwd)/$stem.txt"
if [ -e "$OUT" ] && [ "$FORCE" -ne 1 ]; then
  die "이미 있음: $OUT — 덮어쓰려면 --force, 다른 이름은 --out" 2
fi
if [ -z "$WORK" ]; then
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/transcribe.XXXXXX")"
  trap 'rm -rf "$WORK"' EXIT
else
  mkdir -p "$WORK"
fi

DUR="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$AUDIO")"
printf '입력: %s (%.0f초)\n' "$AUDIO" "$DUR"
t0=$(date +%s)
echo "[1/4] 오디오 변환 (16kHz mono)"
ffmpeg -v error -y -i "$AUDIO" -ac 1 -ar 16000 -c:a pcm_s16le "$WORK/audio.wav"

echo "[2/4] 음성 인식 — whisperkit-cli transcribe ($MODEL, 한국어). 첫 실행은 모델 다운로드 포함"
t1=$(date +%s)
whisperkit-cli transcribe --audio-path "$WORK/audio.wav" --model "$MODEL" --language ko \
  --word-timestamps --report --report-path "$WORK" > "$WORK/transcribe.log" 2>&1 \
  || die "음성 인식 실패 — 로그: $WORK/transcribe.log (--work 로 폴더를 지정하면 남습니다)"
[ -f "$WORK/audio.json" ] || die "전사 리포트가 생성되지 않음: $WORK/audio.json"
printf '      %d초\n' $(( $(date +%s) - t1 ))

echo "[3/4] 화자 분리 — whisperkit-cli diarize${SPEAKERS:+ (참석자 ${SPEAKERS}명 지정)}"
t2=$(date +%s)
NARG=(); [ -n "$SPEAKERS" ] && NARG=(--num-speakers "$SPEAKERS")
# ${arr[@]+"${arr[@]}"}: macOS 기본 bash 3.2에서 set -u 와 빈 배열이 충돌하지 않게 하는 관용구
whisperkit-cli diarize --audio-path "$WORK/audio.wav" --rttm-path "$WORK/audio.rttm" ${NARG[@]+"${NARG[@]}"} \
  > "$WORK/diarize.log" 2>&1 || die "화자 분리 실패 — 로그: $WORK/diarize.log"
[ -f "$WORK/audio.rttm" ] || die "화자 구간 파일이 생성되지 않음"
printf '      %d초\n' $(( $(date +%s) - t2 ))

echo "[4/4] 녹취록 병합 → $OUT"
SARG=(); [ -n "$START" ] && SARG=(--start "$START")
python3 "$HERE/transcript_build.py" --report "$WORK/audio.json" --rttm "$WORK/audio.rttm" --out "$OUT" \
  --title "$TITLE" --author "$AUTHOR" --audio "$AUDIO" --duration "$DUR" ${SARG[@]+"${SARG[@]}"}
printf '완료: 총 %d초\n' $(( $(date +%s) - t0 ))
