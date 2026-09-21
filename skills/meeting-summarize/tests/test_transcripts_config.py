"""transcripts.py 데이터 폴더·설정 단위 테스트 — python3 -m unittest discover -s skills/meeting-summarize/tests"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import transcripts  # noqa: E402

TRANSCRIPT = "주간 회의\n2026.09.04 금 오전 9:37 ・ 12분 3초\n홍길동\n\n참석자 1 00:00\n안녕하세요.\n"


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = transcripts.main(["transcripts.py", *argv])
    return code, out.getvalue()


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "data"
        self.env = mock.patch.dict(os.environ, {"MEETING_SUMMARIZE_HOME": str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_data_home_env_and_default(self):
        self.assertEqual(transcripts.data_home(), self.home)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEETING_SUMMARIZE_HOME")
            self.assertEqual(transcripts.data_home(), Path.home() / ".claude" / "meeting-summarize")

    def test_show_reports_missing_context(self):
        code, out = run("config")
        self.assertEqual(code, 0)
        self.assertIn(str(self.home), out)
        self.assertIn("context.md: 없음", out)
        self.assertIn("input_dir: 미설정", out)
        self.assertIn("storytelling: on", out)

    def test_show_reports_existing_files(self):
        self.home.mkdir(parents=True)
        (self.home / "context.md").write_text("# 우리 측 컨텍스트\n", encoding="utf-8")
        (self.home / "feedback.md").write_text("## F-01 · 2026-01-01 · 리뷰\n\n## F-02 · 2026-01-02 · 리뷰\n", encoding="utf-8")
        _, out = run("config")
        self.assertIn("context.md: 있음", out)
        self.assertIn("feedback.md: 있음(규칙 2건)", out)

    def test_set_get_roundtrip(self):
        notes = Path(self.tmp.name) / "notes"
        notes.mkdir()
        self.assertEqual(run("config", "set", "input_dir", str(notes))[0], 0)
        self.assertEqual(run("config", "set", "author", "홍길동")[0], 0)
        self.assertEqual(run("config", "get", "author"), (0, "홍길동\n"))
        saved = json.loads((self.home / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, {"input_dir": str(notes), "author": "홍길동"})

    def test_get_unset_is_empty(self):
        self.assertEqual(run("config", "get", "author"), (0, "\n"))

    def test_set_rejects_unknown_key_and_bad_value(self):
        self.assertEqual(run("config", "set", "nope", "x")[0], 2)
        self.assertEqual(run("config", "set", "storytelling", "maybe")[0], 2)
        self.assertEqual(run("config", "set", "input_dir", str(Path(self.tmp.name) / "missing"))[0], 2)
        self.assertFalse((self.home / "config.json").exists())

    def test_list_without_dir_or_config_asks_for_folder(self):
        code, out = run("list")
        self.assertEqual(code, 2)
        self.assertIn("config set input_dir", out)

    def test_list_and_meta_use_configured_dir(self):
        notes = Path(self.tmp.name) / "notes"
        notes.mkdir()
        (notes / "주간 회의.txt").write_text(TRANSCRIPT, encoding="utf-8")
        run("config", "set", "input_dir", str(notes))
        code, out = run("list")
        self.assertEqual(code, 0)
        self.assertIn("주간 회의.txt", out)
        code, out = run("meta", "주간 회의.txt")
        self.assertEqual(code, 0)
        self.assertIn("일시: 2026년 9월 4일(금) 09:37 ~ 09:49 (약 12분)", out)


if __name__ == "__main__":
    unittest.main()
