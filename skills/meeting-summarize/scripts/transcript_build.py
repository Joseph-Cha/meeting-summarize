#!/usr/bin/env python3
"""녹취록 병합기: 전사 리포트(JSON, 단어 타임스탬프) + 화자 분리(RTTM) → 화자 분리 녹취록 txt.
transcribe.sh가 호출한다. 표준 라이브러리만 쓴다.

사용: transcript_build.py --report audio.json --rttm audio.rttm --out 녹취록.txt --title 제목 --author 녹음자
        [--start "YYYY-MM-DD HH:MM"] [--audio 원본.m4a] [--duration 초]
        [--snap 1.0] [--min-block 1.0] [--max-lines 8] [--max-span 60]

출력 형식(transcripts.py가 읽는 형식):
  1행 제목 / 2행 "YYYY.MM.DD 요일 오전|오후 H:MM ・ N분 N초" / 3행 녹음자 / 빈 줄 2개 /
  "참석자 N MM:SS" 줄 + 발화 줄들 + 빈 줄 … (1시간부터 "H:MM:SS", 0 채움 없음). 푸터 없음.
--start 가 없으면 원본 파일 생성 시각 − 길이로 추정하고 2행 끝에 "(시작 시각 추정)"을 붙인다.

처리 순서(PoC에서 정답지 대조로 검증한 규칙):
  단어마다 겹침이 가장 긴 화자 구간 배정 → 한 세그먼트 안 소수 화자(<snap초)는 다수 화자로(스냅)
  → 같은 화자 사이에 낀 짧은 전환(<min-block초) 되돌림 → 반복 환각·타 문자 제거
  → 쉼 기반 줄바꿈 → 같은 화자라도 max-lines 줄·max-span 초마다 새 블록.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

WEEKDAY = "월화수목금토일"
FOREIGN = re.compile(r"[Ͱ-ϿЀ-ӿ֐-ۿ฀-๿぀-ヿ一-鿿]+")
DASH = re.compile(r"(?:^|(?<=\s))-\s*(?=[가-힣A-Za-z0-9])")


# ── 입력 ──────────────────────────────────────────────────────────────────────
def load_report(path):
    """전사 리포트 JSON → 단위(단어) 목록. 단어 타임스탬프가 없는 세그먼트는 세그먼트 자체가 단위."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = data[0]
    units = []
    for i, s in enumerate(data.get("segments", [])):
        words = [w for w in (s.get("words") or []) if (w.get("word") or "").strip()]
        if words:
            for w in words:
                st, en = float(w["start"]), float(w["end"])
                units.append({"text": w["word"], "start": st, "end": max(en, st), "seg": i})
        else:
            text = (s.get("text") or "").strip()
            if text:
                units.append({"text": " " + text, "start": float(s["start"]), "end": float(s["end"]), "seg": i})
    units.sort(key=lambda u: (u["start"], u["end"]))
    duration = (data.get("timings") or {}).get("inputAudioSeconds")
    return units, duration


def load_rttm(path):
    """RTTM → [{start, end, speaker}] (화자 id는 등장 순 0,1,2…)."""
    turns, ids = [], {}
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        f = ln.split()
        if len(f) >= 8 and f[0] == "SPEAKER":
            start, dur = float(f[3]), float(f[4])
            turns.append({"start": start, "end": start + dur, "speaker": f[7]})
    turns.sort(key=lambda t: t["start"])
    for t in turns:
        t["speaker"] = ids.setdefault(t["speaker"], len(ids))
    return turns


# ── 화자 배정 ──────────────────────────────────────────────────────────────────
def assign_speakers(units, turns, gap_tolerance=1.0):
    """겹침이 가장 긴 구간의 화자. 겹침이 없으면 gap_tolerance 이내 가장 가까운 구간, 그것도 없으면 직전 화자."""
    turns = sorted(turns, key=lambda t: t["start"])
    j, prev = 0, None
    for u in units:
        while j < len(turns) and turns[j]["end"] < u["start"] - gap_tolerance:
            j += 1
        best, best_ov, nearest, near_d = None, 0.0, None, None
        k = j
        while k < len(turns) and turns[k]["start"] <= u["end"] + gap_tolerance:
            t = turns[k]
            ov = min(u["end"], t["end"]) - max(u["start"], t["start"])
            if ov > best_ov:
                best, best_ov = t["speaker"], ov
            d = max(t["start"] - u["end"], u["start"] - t["end"], 0.0)
            if near_d is None or d < near_d:
                nearest, near_d = t["speaker"], d
            k += 1
        if best is not None:
            u["speaker"] = best
        elif nearest is not None and near_d <= gap_tolerance:
            u["speaker"] = nearest
        else:
            u["speaker"] = prev
        prev = u["speaker"]
    first = next((u["speaker"] for u in units if u["speaker"] is not None), 0)
    for u in units:
        if u["speaker"] is None:
            u["speaker"] = first
    return units


def snap_to_segment(units, min_split):
    """한 세그먼트(대개 한 문장) 안에서 소수 화자의 발화가 min_split초 미만이면 다수 화자로 맞춘다."""
    by_seg = {}
    for u in units:
        by_seg.setdefault(u["seg"], []).append(u)
    changed = 0
    for ws in by_seg.values():
        share = {}
        for u in ws:
            share[u["speaker"]] = share.get(u["speaker"], 0.0) + (u["end"] - u["start"])
        if len(share) < 2:
            continue
        major = max(share, key=share.get)
        if sum(v for k, v in share.items() if k != major) < min_split:
            for u in ws:
                if u["speaker"] != major:
                    u["speaker"] = major
                    changed += 1
    return changed


def smooth(units, min_block):
    """같은 화자 사이에 낀 min_block초 미만의 전환은 그 화자로 되돌린다."""
    runs = []
    for u in units:
        if runs and runs[-1]["speaker"] == u["speaker"]:
            runs[-1]["items"].append(u)
        else:
            runs.append({"speaker": u["speaker"], "items": [u]})
    changed = 0
    for i in range(1, len(runs) - 1):
        r = runs[i]
        dur = r["items"][-1]["end"] - r["items"][0]["start"]
        if dur < min_block and runs[i - 1]["speaker"] == runs[i + 1]["speaker"]:
            for u in r["items"]:
                u["speaker"] = runs[i - 1]["speaker"]
                changed += 1
    return changed


# ── 정리·블록 ───────────────────────────────────────────────────────────────────
def clean_units(units, max_repeat=2):
    """(a) 한국어 발화에 섞인 타 문자(키릴·가나·한자 등)와 자막식 줄머리 대시 제거 (b) 같은 단어가 연속 max_repeat회를 넘으면 잘라냄."""
    out, prev, run, removed, dropped = [], None, 0, 0, 0
    for u in units:
        t = FOREIGN.sub("", u["text"])
        t = DASH.sub(" ", t)  # 자막식 대화 대시("-어디?")는 녹취록에 없는 표기
        removed += len(u["text"]) - len(t)
        key = re.sub(r"[\s.,?!]", "", t)
        if not key:
            continue
        if key == prev:
            run += 1
            if run > max_repeat:
                dropped += 1
                continue
        else:
            prev, run = key, 1
        u["text"] = t
        out.append(u)
    return out, removed, dropped


def build_blocks(units):
    """연속 같은 화자 단위 → 화자 턴."""
    blocks = []
    for u in units:
        if blocks and blocks[-1]["speaker"] == u["speaker"]:
            blocks[-1]["items"].append(u)
        else:
            blocks.append({"speaker": u["speaker"], "start": u["start"], "items": [u]})
    return [b for b in blocks if "".join(x["text"] for x in b["items"]).strip()]


def block_lines(block, pause=0.6, hard_pause=1.5, max_len=200):
    """호흡 단위 줄 나눔: 문장 끝 뒤 pause초 이상 쉬면 줄바꿈, hard_pause 이상이면 문장 중간이라도, max_len 넘으면 다음 문장 끝에서."""
    lines, cur, line_start = [], "", None
    items = block["items"]
    for i, u in enumerate(items):
        if line_start is None:
            line_start = u["start"]
        cur += u["text"]
        nxt = items[i + 1] if i + 1 < len(items) else None
        gap = (nxt["start"] - u["end"]) if nxt else 99
        sent_end = u["text"].rstrip().endswith((".", "?", "!"))
        if nxt is None or gap >= hard_pause or (sent_end and (gap >= pause or len(cur) >= max_len)):
            line = re.sub(r"\s+", " ", cur).strip()
            if line:
                lines.append((line, line_start))
            cur, line_start = "", None
    return lines


# ── 출력 ───────────────────────────────────────────────────────────────────────
def fmt_ts(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def header(title, start, author, duration_sec, estimated=False):
    ampm = "오전" if start.hour < 12 else "오후"
    h12 = start.hour % 12 or 12
    d = int(round(duration_sec))
    line2 = f"{start:%Y.%m.%d} {WEEKDAY[start.weekday()]} {ampm} {h12}:{start.minute:02d} ・ {d // 60}분 {d % 60}초"
    if estimated:
        line2 += " (시작 시각 추정)"
    return f"{title}\n{line2}\n{author}\n\n"


def render(blocks, title, start, author, duration_sec, estimated=False, max_lines=8, max_span=60.0):
    """블록 → 녹취록 전문. 화자 번호는 첫 등장 순. 같은 화자라도 max_lines 줄·max_span 초마다 새 블록."""
    order = {}
    for b in blocks:
        order.setdefault(b["speaker"], len(order) + 1)
    out, nblocks = [header(title, start, author, duration_sec, estimated)], 0

    def emit(spk, t0, lines):
        nonlocal nblocks
        out.append(f"\n참석자 {order[spk]} {fmt_ts(t0)}\n" + "\n".join(lines) + "\n")
        nblocks += 1

    for b in blocks:
        sub, sub_start = [], None
        for line, t in block_lines(b):
            if sub and (len(sub) >= max_lines or t - sub_start >= max_span):
                emit(b["speaker"], sub_start, sub)
                sub, sub_start = [], None
            if sub_start is None:
                sub_start = t
            sub.append(line)
        if sub:
            emit(b["speaker"], sub_start, sub)
    return "".join(out), order, nblocks


def guess_start(audio_path, duration_sec):
    """원본 파일 생성(birth) 시각 − 길이. 내보내기·복사 시각일 수 있으므로 추정치다."""
    st = os.stat(audio_path)
    birth = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.fromtimestamp(birth) - timedelta(seconds=duration_sec)


def build(units, turns, snap=1.0, min_block=1.0):
    """단위 + 화자 구간 → 블록 (통계 dict 포함)."""
    units, removed, dropped = clean_units(units)
    assign_speakers(units, turns)
    snapped = snap_to_segment(units, snap) if snap > 0 else 0
    smoothed = smooth(units, min_block) if min_block > 0 else 0
    blocks = build_blocks(units)
    return blocks, {"units": len(units), "snapped": snapped, "smoothed": smoothed,
                    "foreign_chars": removed, "repeats_dropped": dropped}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--rttm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--start", help="녹음 시작 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--audio", help="--start 추정용 원본 오디오")
    ap.add_argument("--duration", type=float, help="오디오 길이(초). 없으면 리포트·마지막 단어 시각")
    ap.add_argument("--snap", type=float, default=1.0)
    ap.add_argument("--min-block", type=float, default=1.0)
    ap.add_argument("--max-lines", type=int, default=8)
    ap.add_argument("--max-span", type=float, default=60.0)
    args = ap.parse_args(argv)

    units, rep_dur = load_report(args.report)
    turns = load_rttm(args.rttm)
    if not units:
        print("전사 결과가 비어 있음", file=sys.stderr)
        return 1
    duration = args.duration or rep_dur or max(u["end"] for u in units)
    blocks, stats = build(units, turns, args.snap, args.min_block)

    estimated = False
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    elif args.audio:
        start, estimated = guess_start(args.audio, duration), True
    else:
        print("--start 또는 --audio 가 필요합니다", file=sys.stderr)
        return 2
    text, order, nblocks = render(blocks, args.title, start, args.author, duration, estimated,
                                  args.max_lines, args.max_span)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")

    chars = {}
    for b in blocks:
        chars[order[b["speaker"]]] = chars.get(order[b["speaker"]], 0) + sum(len(u["text"].strip()) for u in b["items"])
    print(f"화자 {len(order)}명 / 블록 {nblocks}개 / " + ", ".join(f"참석자 {k} {v}자" for k, v in sorted(chars.items())))
    print(f"정리: 반복 {stats['repeats_dropped']}개·타 문자 {stats['foreign_chars']}자 제거, 스냅 {stats['snapped']}·스무딩 {stats['smoothed']}")
    if estimated:
        print(f"주의: 녹음 시작 시각을 파일 생성 시각−길이로 추정({start:%Y-%m-%d %H:%M}) — 확인 필요", file=sys.stderr)
    print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
