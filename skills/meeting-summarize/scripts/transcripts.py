#!/usr/bin/env python3
"""회의 녹취록(화자 분리 txt) 목록·메타 추출, 회의록 점검, 데이터 폴더 설정.

사용:
  transcripts.py list [DIR]   DIR(기본: config의 input_dir)의 txt를 표로 나열, 녹취록 없는 녹음(m4a 등)은 전사 대상으로 표시
  transcripts.py meta FILE    파일 하나의 일시·작성자·화자 통계를 표로 출력
  transcripts.py check MD     정리된 회의록(md)의 분량 예산·녹취 말투·표시 규칙을 점검(R-04). 위반은 exit 1, 경고는 exit 0
  transcripts.py config                  데이터 폴더 위치와 context.md·feedback.md·설정 상태
  transcripts.py config get KEY          설정값 하나(없으면 빈 줄)
  transcripts.py config set KEY VALUE    KEY: input_dir | author | storytelling(on/off)

데이터 폴더(조직 정보·피드백 규칙·설정)는 스킬 폴더 밖에 둔다 — 기본 ~/.claude/meeting-summarize,
환경변수 MEETING_SUMMARIZE_HOME 으로 바꾼다. 플러그인 업데이트가 덮어쓰지 않고, 배포물에 조직 정보가 섞이지 않는다.

녹취록 헤더 형식(1~3행) — transcribe.sh 가 만드는 형식이며, 같은 구조의 txt는 출처와 무관하게 읽는다:
  <제목>
  YYYY.MM.DD 요일 오전|오후 H:MM ・ [N시간] [N분] [N초] [(시작 시각 추정)]
  <작성자>
본문은 "참석자 N MM:SS" 줄(1시간부터 H:MM:SS) 뒤에 발화가 이어진다.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_KEYS = {
    "input_dir": "녹취록·녹음 기본 폴더",
    "author": "회의록 작성자(녹음자) 기본값",
    "storytelling": "대외 미팅 5-1 스토리텔링(on/off)",
}
HEADER_RE = re.compile(
    r"^(\d{4})\.(\d{2})\.(\d{2})\s+(\S)\s+(오전|오후)\s+(\d{1,2}):(\d{2})\s*・\s*"
    r"(?:(\d+)시간\s*)?(?:(\d+)분\s*)?(?:(\d+)초)?"
)
SPEAKER_RE = re.compile(r"^(참석자\s*\d+)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$")


def parse_header(lines):
    """헤더 3행 → dict. 형식이 다르면 None 필드로 둔다(추측하지 않는다)."""
    title = lines[0].strip() if lines else ""
    author = lines[2].strip() if len(lines) > 2 else ""
    line2 = lines[1].strip() if len(lines) > 1 else ""
    m = HEADER_RE.match(line2) if line2 else None
    estimated = "추정" in line2  # transcribe.sh 가 시작 시각을 추정했을 때 붙이는 표시
    if not m:
        return {"title": title, "author": author, "start": None, "minutes": None,
                "weekday": None, "estimated": estimated}
    y, mo, d, wd, ampm, h, mi, hh, mm, ss = m.groups()
    h = int(h) % 12 + (12 if ampm == "오후" else 0)
    start = datetime(int(y), int(mo), int(d), h, int(mi))
    secs = int(hh or 0) * 3600 + int(mm or 0) * 60 + int(ss or 0)
    return {"title": title, "author": author, "start": start,
            "minutes": round(secs / 60), "weekday": wd, "estimated": estimated}


def fmt_when(h):
    """'2026년 9월 2일(수) 13:31 ~ 14:33 (약 62분)' — 회의록 1번 항목 그대로."""
    if not h["start"]:
        return "헤더에서 일시를 읽지 못함(녹취 본문·사용자에게 확인)"
    s = h["start"]
    e = s + timedelta(minutes=h["minutes"] or 0)
    when = (f"{s.year}년 {s.month}월 {s.day}일({h['weekday']}) "
            f"{s:%H:%M} ~ {e:%H:%M} (약 {h['minutes']}분)")
    if h.get("estimated"):
        when += " (확인 필요)"  # 회의록 1번에는 추론 설명 없이 표시만 남긴다
    return when


def speaker_stats(lines):
    stats = {}
    cur = None
    for ln in lines[3:]:
        m = SPEAKER_RE.match(ln.strip())
        if m:
            cur = m.group(1).replace(" ", "")
            st = stats.setdefault(cur, {"turns": 0, "chars": 0, "first": m.group(2),
                                        "sample": ""})
            st["turns"] += 1
        elif cur and ln.strip():
            st = stats[cur]
            st["chars"] += len(ln.strip())
            if not st["sample"]:
                st["sample"] = ln.strip()[:60]
    return stats


def data_home():
    env = os.environ.get("MEETING_SUMMARIZE_HOME")
    return Path(env).expanduser() if env else Path.home() / ".claude" / "meeting-summarize"


def load_config():
    p = data_home() / "config.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def input_dir():
    d = load_config().get("input_dir")
    return Path(d).expanduser() if d else None


def cmd_config(args):
    home = data_home()
    cfg = load_config()
    if args[:1] == ["get"] and len(args) == 2:
        print(cfg.get(args[1], ""))
        return 0
    if args[:1] == ["set"] and len(args) == 3:
        key, value = args[1], args[2]
        if key not in CONFIG_KEYS:
            print(f"알 수 없는 설정: {key} (가능: {', '.join(CONFIG_KEYS)})")
            return 2
        if key == "storytelling" and value not in ("on", "off"):
            print("storytelling 은 on 또는 off")
            return 2
        if key == "input_dir":
            d = Path(value).expanduser()
            if not d.is_dir():
                print(f"폴더 없음: {d}")
                return 2
            value = str(d.resolve()) if not d.is_absolute() else str(d)
        cfg[key] = value
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{key} = {value}")
        return 0
    if args:
        print("사용: config | config get KEY | config set KEY VALUE")
        return 2
    print(f"데이터 폴더: {home} (환경변수 MEETING_SUMMARIZE_HOME 으로 변경)")
    ctx, fb, ex = home / "context.md", home / "feedback.md", home / "example.md"
    print("- context.md: " + ("있음" if ctx.is_file() else "없음 — 첫 실행 설정 필요(SKILL.md '첫 실행')"))
    if fb.is_file():
        n = len(re.findall(r"^## F-\d+", fb.read_text(encoding="utf-8", errors="replace"), re.M))
        print(f"- feedback.md: 있음(규칙 {n}건)")
    else:
        print("- feedback.md: 없음 — 첫 피드백 때 만든다(기본 규칙 references/rules.md 만 적용)")
    print("- example.md: " + ("있음 — 스킬 기본 예시보다 우선" if ex.is_file() else "없음 — 스킬 기본 예시 사용"))
    print("설정(config.json):")
    for key, desc in CONFIG_KEYS.items():
        default = "on(기본)" if key == "storytelling" else "미설정"
        print(f"- {key}: {cfg.get(key) or default}  # {desc}")
    return 0


AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".mp4", ".mov"}


def cmd_list(d):
    files = sorted(p for p in d.iterdir() if p.suffix.lower() == ".txt")
    if not files:
        audio = [p.name for p in sorted(d.iterdir()) if p.suffix.lower() in AUDIO_EXT]
        print(f"txt 파일 없음: {d}" + (f"\n녹음만 있음(전사 필요): " + ", ".join(audio) if audio else ""))
        return 1
    print(f"폴더: {d}")
    print("(meta에는 아래 '파일' 열의 이름만 넘겨도 된다 — 이 폴더에서 찾는다)\n")
    print("| # | 파일 | 제목 | 일시 | 길이 | 작성자 | 크기 |")
    print("|---|---|---|---|---|---|---|")
    for i, p in enumerate(files, 1):
        h = parse_header(p.read_text(encoding="utf-8", errors="replace").splitlines())
        when = f"{h['start']:%Y-%m-%d %H:%M}" if h["start"] else "?"
        mins = f"{h['minutes']}분" if h["minutes"] is not None else "?"
        print(f"| {i} | {p.name} | {h['title']} | {when} | {mins} | {h['author']} | "
              f"{p.stat().st_size // 1024}KB |")
    stems = {p.stem for p in files}
    audio = [p for p in sorted(d.iterdir()) if p.suffix.lower() in AUDIO_EXT and p.stem not in stems]
    if audio:
        print("\n녹취록이 없는 녹음(전사 필요 — `scripts/transcribe.sh \"<파일>\" --start \"YYYY-MM-DD HH:MM\" --speakers N`):")
        for p in audio:
            print(f"- {p.name} ({p.stat().st_size // 1048576}MB)")
    return 0


def cmd_meta(p):
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    h = parse_header(lines)
    print(f"파일: {p}")
    print(f"제목: {h['title']}")
    print(f"일시: {fmt_when(h)}")
    if h.get("estimated"):
        print("주의: 시작 시각은 파일 시각에서 추정한 값 — 사용자에게 확인받고, 확인되면 '(확인 필요)'를 뗀다")
    print(f"작성자(녹음자): {h['author']}")
    print(f"본문: {len(lines)}행\n")
    st = speaker_stats(lines)
    print("| 화자 | 발화 수 | 글자 수 | 첫 발화 | 첫 발화 샘플 |")
    print("|---|---|---|---|---|")
    for k in sorted(st, key=lambda k: -st[k]["chars"]):
        v = st[k]
        print(f"| {k} | {v['turns']} | {v['chars']} | {v['first']} | {v['sample']} |")
    return 0


BUDGET = {"lines": 80, "chars": 3500, "tables": 2, "table_rows": 8,
          "bullets_per_sub": 5, "bullets_6": 6, "rows_7": 8, "bullets_8": 4}
NEAR = 0.9  # 상한의 90%를 넘으면 위반은 아니지만 "상한 근접" 경고
UNCERTAIN_RE = re.compile(r"\((?:[^()]*?)(?:확인 필요|추정|잠정|불명확|녹취 표기)[^()]*\)|미확인")
LABEL_RE = re.compile(r"^\s*[*-]\s+\*\*([^*]+)\*\*\s*:")
REASONING = ("추정", "이므로", "근거", "으로 보아", "때문에")
LABELS_6 = ("핵심 제약", "선행 과제", "기회", "우리", "내부 참고", "리스크", "소통 채널",
            "결정", "보류", "전제", "다음 회의")
SPOKEN = ("거든요", "잖아요", "그러니까", "약간 ", " 이제 ", "그쵸", "네네", "어쨌든", "막 ")


def cmd_check(p):
    """회의록 md의 분량·말투 점검(R-04). 위반 0건이면 exit 0, 있으면 exit 1."""
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    issues, warnings = [], []
    nonblank = [l for l in lines if l.strip()]
    chars = sum(len(l.replace(" ", "")) for l in nonblank)
    if len(nonblank) > BUDGET["lines"]:
        issues.append(f"전체 {len(nonblank)}줄 > {BUDGET['lines']}줄")
    elif len(nonblank) > BUDGET["lines"] * NEAR:
        warnings.append(f"상한 근접: 전체 {len(nonblank)}줄 (상한 {BUDGET['lines']}줄) — 상한은 목표가 아니다")
    if chars > BUDGET["chars"]:
        issues.append(f"전체 {chars}자(공백 제외) > {BUDGET['chars']}자")
    elif chars > BUDGET["chars"] * NEAR:
        warnings.append(f"상한 근접: 전체 {chars}자 (상한 {BUDGET['chars']}자, 목표 2,800~3,000자) — 덜어낼 불릿을 찾는다")
    # 섹션 나누기
    sec, cur = {}, None
    for l in lines:
        m = re.match(r"^(#{2,3})\s+(\S+)", l)
        if m:
            cur = m.group(2)
            sec[cur] = []
        elif cur:
            sec[cur].append(l)
    tables = 0
    for name, body in sec.items():
        rows = [l for l in body if l.startswith("|") and not re.match(r"^\|\s*-", l)]
        if rows:
            tables += 1
            if not name.startswith("3.") and len(rows) - 1 > BUDGET["table_rows"]:
                issues.append(f"{name} 표 {len(rows)-1}행 > {BUDGET['table_rows']}행")
        bullets = [l for l in body if re.match(r"^\s*[*-]\s", l)]
        if name.startswith("5-") and len(bullets) > BUDGET["bullets_per_sub"]:
            issues.append(f"{name} 불릿 {len(bullets)}개 > {BUDGET['bullets_per_sub']}개")
        if name.startswith("6.") and len(bullets) > BUDGET["bullets_6"]:
            issues.append(f"6번 불릿 {len(bullets)}개 > {BUDGET['bullets_6']}개")
        if name.startswith("7.") and rows and len(rows) - 1 > BUDGET["rows_7"]:
            issues.append(f"7번 {len(rows)-1}행 > {BUDGET['rows_7']}행")
        if name.startswith("8.") and len(bullets) > BUDGET["bullets_8"]:
            issues.append(f"8번 불릿 {len(bullets)}개 > {BUDGET['bullets_8']}개")
        if name.startswith(("1.", "2.")):
            for l in body:
                hit = next((w for w in REASONING if w in l), None)
                if hit:
                    issues.append(f"{name[0]}번에 추론·근거 서술 '{hit}' — 값만 쓰고 모르면 '(확인 필요)': {l.strip()[:50]}…")
        for b in bullets:
            m = LABEL_RE.match(b)
            if m and re.match(r"5-([2-9]|\d{2})", name) and m.group(1).strip() != "합의":
                issues.append(f"{name} template에 없는 굵은 라벨 '{m.group(1)}' — 5번의 굵은 라벨은 '합의'뿐")
            if m and name.startswith("6.") and not m.group(1).strip().startswith(LABELS_6):
                warnings.append(f"6번 template에 없는 라벨 '{m.group(1)}' — feedback.md 규칙으로 정한 라벨이면 무시")
        for b in bullets:
            sents = [s for s in re.split(r"[.!?]\s", b) if s.strip()]
            if len(sents) >= 4 or len(b.strip()) > 160:
                issues.append(f"{name} 불릿이 길다(4문장 이상 또는 160자 초과): {b.strip()[:50]}…")
            for w in SPOKEN:
                if w in b:
                    issues.append(f"{name} 녹취 말투 '{w.strip()}': {b.strip()[:50]}…")
                    break
    if tables - (1 if any(k.startswith("3.") for k in sec) else 0) > BUDGET["tables"]:
        issues.append(f"표 {tables}개(참석대상 제외 {tables-1}) > {BUDGET['tables']}개")
    for l in lines:
        if len(UNCERTAIN_RE.findall(l)) >= 2:
            issues.append(f"한 줄에 불확실성 표시 2개 이상 — 한 줄에 하나만: {l.strip()[:50]}…")
        if re.search(r"참석자\s*\d+", l):
            issues.append(f"본문에 '참석자 N' 라벨 — 이름·직함으로 쓰고 매핑 근거는 사용자 보고에: {l.strip()[:50]}…")
    if "내부 참고(6번)" in text and not any(
            "내부 참고" in l for k, body in sec.items() if k.startswith("6.") for l in body):
        issues.append("5번에 '→ 내부 참고(6번)'이 있는데 6번에 '내부 참고' 불릿이 없음(끊긴 참조)")
    if "전문 별도 공유" not in text:
        issues.append("제목 아래 '녹취록: … (전문 별도 공유)' 줄 없음")
    quotes = text.count("「") + text.count("\u201c")
    if quotes > 3:
        issues.append(f"인용 {quotes}곳(「」·“”) > 3곳 — 발언 인용은 스토리 훅 1~2개만, 나머지는 결론형으로")
    body_tables = tables - (1 if any(k.startswith("3.") for k in sec) else 0)
    print(f"파일: {p}\n줄(공백 제외): {len(nonblank)} / 글자(공백 제외): {chars} / "
          f"표: {body_tables}개(참석대상 제외, 상한 {BUDGET['tables']})")
    for w in warnings:
        print("경고 — " + w)
    if not issues:
        print("분량·말투 점검: 위반 없음")
        return 0
    print(f"분량·말투 점검: 위반 {len(issues)}건")
    for i in issues:
        print(" - " + i)
    return 1


def main(argv):
    if len(argv) < 2 or argv[1] not in ("list", "meta", "check", "config"):
        print(__doc__)
        return 2
    if argv[1] == "config":
        return cmd_config(argv[2:])
    if argv[1] == "check":
        if len(argv) < 3 or not Path(argv[2]).expanduser().is_file():
            print("check MD 필요(파일 없음)")
            return 2
        return cmd_check(Path(argv[2]).expanduser())
    if argv[1] == "list":
        d = Path(argv[2]).expanduser() if len(argv) > 2 else input_dir()
        if d is None:
            print("기본 입력 폴더 미설정 — `list <폴더>`로 지정하거나 "
                  "`config set input_dir <폴더>`로 기본값을 정한다")
            return 2
        if not d.is_dir():
            print(f"폴더 없음: {d}")
            return 2
        return cmd_list(d)
    if len(argv) < 3:
        print("meta FILE 필요")
        return 2
    p = Path(argv[2]).expanduser()
    base = input_dir()
    if not p.is_file() and not p.is_absolute() and base and (base / p).is_file():
        p = base / p  # 파일명만 받으면 기본 폴더에서 찾는다
    if not p.is_file():
        print(f"파일 없음: {p}" + (f" (기본 폴더에도 없음: {base})" if base else ""))
        return 2
    return cmd_meta(p)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
