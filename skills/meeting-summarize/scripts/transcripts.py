#!/usr/bin/env python3
"""회의 녹취록(화자 분리 txt) 목록·메타 추출.

사용:
  transcripts.py list [DIR]   DIR(기본: iCloud 회의록 폴더)의 txt를 표로 나열
  transcripts.py meta FILE    파일 하나의 일시·작성자·화자 통계를 표로 출력
  transcripts.py check MD     정리된 회의록(md)의 분량 예산·녹취 말투를 점검(F-04)

녹취록 헤더 형식(1~3행):
  <제목>
  YYYY.MM.DD 요일 오전|오후 H:MM ・ [N시간] [N분] [N초]
  <작성자>
본문은 "참석자 N MM:SS" 줄 뒤에 발화가 이어진다.
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DIR = Path.home() / (
    "Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/회의록"
)
HEADER_RE = re.compile(
    r"^(\d{4})\.(\d{2})\.(\d{2})\s+(\S)\s+(오전|오후)\s+(\d{1,2}):(\d{2})\s*・\s*"
    r"(?:(\d+)시간\s*)?(?:(\d+)분\s*)?(?:(\d+)초)?"
)
SPEAKER_RE = re.compile(r"^(참석자\s*\d+)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$")


def parse_header(lines):
    """헤더 3행 → dict. 형식이 다르면 None 필드로 둔다(추측하지 않는다)."""
    title = lines[0].strip() if lines else ""
    author = lines[2].strip() if len(lines) > 2 else ""
    m = HEADER_RE.match(lines[1].strip()) if len(lines) > 1 else None
    if not m:
        return {"title": title, "author": author, "start": None, "minutes": None,
                "weekday": None}
    y, mo, d, wd, ampm, h, mi, hh, mm, ss = m.groups()
    h = int(h) % 12 + (12 if ampm == "오후" else 0)
    start = datetime(int(y), int(mo), int(d), h, int(mi))
    secs = int(hh or 0) * 3600 + int(mm or 0) * 60 + int(ss or 0)
    return {"title": title, "author": author, "start": start,
            "minutes": round(secs / 60), "weekday": wd}


def fmt_when(h):
    """'2026년 9월 2일(수) 13:31 ~ 14:33 (약 62분)' — 회의록 1번 항목 그대로."""
    if not h["start"]:
        return "헤더에서 일시를 읽지 못함(녹취 본문·사용자에게 확인)"
    s = h["start"]
    e = s + timedelta(minutes=h["minutes"] or 0)
    return (f"{s.year}년 {s.month}월 {s.day}일({h['weekday']}) "
            f"{s:%H:%M} ~ {e:%H:%M} (약 {h['minutes']}분)")


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


def cmd_list(d):
    files = sorted(p for p in d.iterdir() if p.suffix.lower() == ".txt")
    if not files:
        print(f"txt 파일 없음: {d}")
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
    others = [p.name for p in d.iterdir() if p.suffix.lower() != ".txt"
              and not p.name.startswith(".")]
    if others:
        print("\n녹취록이 아닌 파일(오디오 등, 정리 대상 아님): " + ", ".join(others))
    return 0


def cmd_meta(p):
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    h = parse_header(lines)
    print(f"파일: {p}")
    print(f"제목: {h['title']}")
    print(f"일시: {fmt_when(h)}")
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
SPOKEN = ("거든요", "잖아요", "그러니까", "약간 ", " 이제 ", "그쵸", "네네", "어쨌든", "막 ")


def cmd_check(p):
    """회의록 md의 분량·말투 점검. 위반 0건이면 exit 0, 있으면 exit 1."""
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    issues = []
    nonblank = [l for l in lines if l.strip()]
    chars = sum(len(l.replace(" ", "")) for l in nonblank)
    if len(nonblank) > BUDGET["lines"]:
        issues.append(f"전체 {len(nonblank)}줄 > {BUDGET['lines']}줄")
    if chars > BUDGET["chars"]:
        issues.append(f"전체 {chars}자(공백 제외) > {BUDGET['chars']}자")
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
    if "전문 별도 공유" not in text:
        issues.append("제목 아래 '녹취록: … (전문 별도 공유)' 줄 없음")
    quotes = text.count("「") + text.count("\u201c")
    if quotes > 3:
        issues.append(f"인용 {quotes}곳(「」·“”) > 3곳 — 발언 인용은 스토리 훅 1~2개만, 나머지는 결론형으로")
    print(f"파일: {p}\n줄(공백 제외): {len(nonblank)} / 글자(공백 제외): {chars} / 표: {tables}")
    if not issues:
        print("분량·말투 점검: 위반 없음")
        return 0
    print(f"분량·말투 점검: 위반 {len(issues)}건")
    for i in issues:
        print(" - " + i)
    return 1


def main(argv):
    if len(argv) < 2 or argv[1] not in ("list", "meta", "check"):
        print(__doc__)
        return 2
    if argv[1] == "check":
        if len(argv) < 3 or not Path(argv[2]).expanduser().is_file():
            print("check MD 필요(파일 없음)")
            return 2
        return cmd_check(Path(argv[2]).expanduser())
    if argv[1] == "list":
        d = Path(argv[2]).expanduser() if len(argv) > 2 else DEFAULT_DIR
        if not d.is_dir():
            print(f"폴더 없음: {d}")
            return 2
        return cmd_list(d)
    if len(argv) < 3:
        print("meta FILE 필요")
        return 2
    p = Path(argv[2]).expanduser()
    if not p.is_file() and not p.is_absolute() and (DEFAULT_DIR / p).is_file():
        p = DEFAULT_DIR / p  # 파일명만 받으면 기본 폴더에서 찾는다
    if not p.is_file():
        print(f"파일 없음: {p} (기본 폴더에도 없음: {DEFAULT_DIR})")
        return 2
    return cmd_meta(p)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
