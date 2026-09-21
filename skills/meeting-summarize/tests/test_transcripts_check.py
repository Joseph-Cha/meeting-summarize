"""transcripts.py check 단위 테스트 — python3 -m unittest discover -s skills/meeting-summarize/tests

기준 문서는 references/example.md(위반 0건)이고, 한 곳씩 망가뜨려 해당 점검이 잡는지 본다.
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import transcripts  # noqa: E402

EXAMPLE = (HERE.parent / "references" / "example.md").read_text(encoding="utf-8")


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, text):
        p = Path(self.tmp.name) / "m.md"
        p.write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = transcripts.main(["transcripts.py", "check", str(p)])
        return code, out.getvalue()

    def mutate(self, old, new):
        self.assertEqual(EXAMPLE.count(old), 1, old)
        return EXAMPLE.replace(old, new)

    def test_example_is_clean(self):
        code, out = self.check(EXAMPLE)
        self.assertEqual(code, 0, out)
        self.assertIn("위반 없음", out)
        self.assertNotIn("경고", out)

    def test_two_uncertainty_marks_on_one_line(self):
        code, out = self.check(self.mutate(
            "* 유통기한 3년.", "* 유통기한 3년(확인 필요), 산도 4.5%(녹취상 불명확)."))
        self.assertEqual(code, 1)
        self.assertIn("불확실성 표시", out)

    def test_single_uncertainty_mark_is_fine(self):
        code, out = self.check(self.mutate("* 유통기한 3년.", "* 유통기한 3년(확인 필요)."))
        self.assertEqual(code, 0, out)

    def test_speaker_label_in_body(self):
        code, out = self.check(self.mutate(
            "| 노을트레이드 | 박도윤 대표 | 해외 바이어 네트워크 |",
            "| 노을트레이드 | 박도윤 대표 | 해외 바이어 네트워크 (참석자 3) |"))
        self.assertEqual(code, 1)
        self.assertIn("참석자 N", out)

    def test_reasoning_in_when_and_where(self):
        code, out = self.check(self.mutate(
            "* 솔마루 식초 양조장 사무실 (경북 상주시)",
            "* 솔마루 식초 양조장 사무실 — 옹기 언급이 있으므로 양조장으로 추정"))
        self.assertEqual(code, 1)
        self.assertIn("2번", out)
        code, out = self.check(self.mutate(
            "(약 68분)", "(약 68분) — 파일 생성 시각을 근거로 계산"))
        self.assertEqual(code, 1)
        self.assertIn("1번", out)

    def test_unknown_bold_label_in_section_5(self):
        code, out = self.check(self.mutate(
            "* 대표 희망: 3년 감식초", "* **정리(합의 아님)**: 3년 감식초"))
        self.assertEqual(code, 1)
        self.assertIn("정리(합의 아님)", out)

    def test_unknown_bold_label_in_section_6_is_warning_only(self):
        code, out = self.check(self.mutate("* **기회**:", "* **메모**:"))
        self.assertEqual(code, 0, out)
        self.assertIn("경고", out)
        self.assertIn("메모", out)

    def test_dangling_internal_reference(self):
        text = "\n".join(l for l in EXAMPLE.splitlines() if not l.startswith("* **내부 참고"))
        code, out = self.check(text)
        self.assertEqual(code, 1)
        self.assertIn("내부 참고", out)

    def test_near_limit_is_warning_not_violation(self):
        # 불릿 수는 그대로 두고 짧은 불릿의 길이만 늘려 상한 3,500자의 90%(3,150자)를 넘긴다
        pad = "가나다라마바사아자차" * 9  # 90자 — 불릿 160자 상한 안
        total = sum(len(l.replace(" ", "")) for l in EXAMPLE.splitlines() if l.strip())
        lines = []
        for l in EXAMPLE.splitlines():
            if l.startswith("* ") and len(l) < 60 and total < 3200:
                l, total = l.rstrip(".") + " " + pad + ".", total + len(pad) + 1
            lines.append(l)
        self.assertGreaterEqual(total, 3200)
        self.assertLess(total, 3500)
        code, out = self.check("\n".join(lines))
        self.assertEqual(code, 0, out)
        self.assertIn("상한 근접", out)


if __name__ == "__main__":
    unittest.main()
