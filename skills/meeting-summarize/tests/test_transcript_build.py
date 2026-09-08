"""transcript_build.py 단위 테스트 — python3 -m unittest discover -s skills/meeting-summarize/tests"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import transcript_build as tb  # noqa: E402
import transcripts  # noqa: E402


def W(text, start, end, seg=0):
    return {"text": " " + text, "start": start, "end": end, "seg": seg}


class AssignTests(unittest.TestCase):
    def test_overlap_nearest_carry(self):
        turns = [{"start": 0, "end": 5, "speaker": 0}, {"start": 5.5, "end": 10, "speaker": 1}]
        units = [W("a", 0, 1), W("b", 5.2, 5.45), W("c", 6, 7), W("d", 20, 21)]
        tb.assign_speakers(units, turns)
        self.assertEqual([u["speaker"] for u in units], [0, 1, 1, 1])  # b: 겹침 없음 → 더 가까운 구간(5.5, 0.05초), d: 직전 화자 유지

    def test_snap_minor_share(self):
        units = [W("왜냐하면", 100, 100.4, seg=3), W("우리는", 100.4, 100.6, seg=3), W("1차에", 100.6, 102, seg=3), W("이렇게.", 102, 103, seg=3)]
        for u, s in zip(units, [0, 0, 1, 1]):
            u["speaker"] = s
        self.assertEqual(tb.snap_to_segment(units, 1.0), 2)
        self.assertEqual({u["speaker"] for u in units}, {1})

    def test_smooth_short_interjection(self):
        units = [W("a", 0, 3), W("네", 3.1, 3.4), W("b", 3.6, 6)]
        for u, s in zip(units, [0, 1, 0]):
            u["speaker"] = s
        self.assertEqual(tb.smooth(units, 1.0), 1)
        self.assertEqual(units[1]["speaker"], 0)

    def test_clean_repeats_and_foreign(self):
        units = [W("수고하셨습니다", i, i + 1) for i in range(5)] + [W("오늘ось", 10, 11)]
        out, removed, dropped = tb.clean_units(units)
        self.assertEqual(dropped, 3)
        self.assertEqual(removed, 3)
        self.assertEqual(out[-1]["text"].strip(), "오늘")

    def test_clean_subtitle_dash(self):
        out, removed, _ = tb.clean_units([W("-어디?", 0, 1), W("B2B-거래", 1, 2), W("- 네", 2, 3)])
        self.assertEqual([u["text"].strip() for u in out], ["어디?", "B2B-거래", "네"])


class RenderTests(unittest.TestCase):
    def blocks(self):
        units = [W("다들 잘 보내셨죠?", 0, 1), W("반갑습니다.", 1.2, 2), W("네.", 3, 3.5), W("시작하죠.", 3.6, 4.5)]
        for u, s in zip(units, [0, 0, 1, 1]):
            u["speaker"] = s
        return tb.build_blocks(units)

    def test_header_and_timestamps(self):
        text, order, n = tb.render(self.blocks(), "제목", datetime(2026, 9, 4, 9, 37), "차동훈", 6167)
        lines = text.splitlines()
        self.assertEqual(lines[0], "제목")
        self.assertEqual(lines[1], "2026.09.04 금 오전 9:37 ・ 102분 47초")  # 60분 넘어도 '시간' 없음, 0 채움 없음
        self.assertEqual(lines[2], "차동훈")
        self.assertEqual(lines[3:5], ["", ""])
        self.assertEqual(lines[5], "참석자 1 00:00")
        self.assertNotIn("clovanote", text)
        self.assertEqual(n, 2)
        self.assertEqual(order, {0: 1, 1: 2})

    def test_afternoon_and_estimated(self):
        h = tb.header("t", datetime(2026, 9, 7, 14, 0), "a", 4677, estimated=True)
        self.assertTrue(h.splitlines()[1].startswith("2026.09.07 월 오후 2:00 ・ 77분 57초 (시작 시각 추정)"))

    def test_fmt_ts_hour_rollover(self):
        self.assertEqual(tb.fmt_ts(59), "00:59")
        self.assertEqual(tb.fmt_ts(3601), "1:00:01")

    def test_block_split_by_lines(self):
        units = [W(f"문장 {i}.", i * 2, i * 2 + 1) for i in range(20)]
        for u in units:
            u["speaker"] = 0
        text, _, n = tb.render(tb.build_blocks(units), "t", datetime(2026, 1, 1, 9, 0), "a", 40, max_lines=8, max_span=1000)
        self.assertEqual(n, 3)  # 20줄 → 8 + 8 + 4
        self.assertEqual(text.count("참석자 1 "), 3)

    def test_block_lines_pause(self):
        b = {"speaker": 0, "start": 0, "items": [W("첫 문장.", 0, 1), W("둘째.", 1.2, 2), W("셋째.", 3.5, 4)]}
        self.assertEqual([l for l, _ in tb.block_lines(b)], ["첫 문장. 둘째.", "셋째."])

    def test_roundtrip_with_transcripts_py(self):
        text, _, _ = tb.render(self.blocks(), "회의", datetime(2026, 9, 4, 9, 37), "차동훈", 6167)
        h = transcripts.parse_header(text.splitlines())
        self.assertEqual(h["start"], datetime(2026, 9, 4, 9, 37))
        self.assertEqual(h["minutes"], 103)
        self.assertEqual(transcripts.fmt_when(h), "2026년 9월 4일(금) 09:37 ~ 11:20 (약 103분)")
        st = transcripts.speaker_stats(text.splitlines())
        self.assertEqual(set(st), {"참석자1", "참석자2"})


class IOTests(unittest.TestCase):
    def test_load_report_and_rttm_and_main(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            report = {"segments": [
                {"start": 0, "end": 2, "text": "안녕하세요.", "words": [{"word": " 안녕하세요.", "start": 0, "end": 2, "probability": 0.9}]},
                {"start": 3, "end": 4, "text": "네.", "words": []}],
                "timings": {"inputAudioSeconds": 5.0}}
            (d / "a.json").write_text(json.dumps([report]), encoding="utf-8")
            (d / "a.rttm").write_text("SPEAKER a 1 0.000 2.500 <NA> <NA> B <NA> <NA>\nSPEAKER a 1 2.900 2.000 <NA> <NA> A <NA> <NA>\n")
            units, dur = tb.load_report(d / "a.json")
            self.assertEqual(len(units), 2)
            self.assertEqual(dur, 5.0)
            turns = tb.load_rttm(d / "a.rttm")
            self.assertEqual([t["speaker"] for t in turns], [0, 1])  # 등장 순 번호
            rc = tb.main(["--report", str(d / "a.json"), "--rttm", str(d / "a.rttm"), "--out", str(d / "o.txt"),
                          "--title", "t", "--author", "a", "--start", "2026-09-04 09:37"])
            self.assertEqual(rc, 0)
            out = (d / "o.txt").read_text(encoding="utf-8")
            self.assertIn("참석자 1 00:00\n안녕하세요.", out)
            self.assertIn("참석자 2 00:03\n네.", out)
            self.assertFalse(out.rstrip().endswith("naver.com"))


if __name__ == "__main__":
    unittest.main()
