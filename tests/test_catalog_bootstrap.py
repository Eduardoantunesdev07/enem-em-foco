from pathlib import Path
import tempfile
import unittest

from app.storage import ROOT, connect, initialize
from app.service import start_attempt, save_answer, serialize_attempt


class CatalogBootstrapTests(unittest.TestCase):
    def test_fresh_install_has_catalog_without_personal_history(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            path = Path(folder) / 'new.sqlite3'
            initialize(path)
            with connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM exams').fetchone()[0], 6)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0], 555)
                for table in ('attempts', 'answers', 'error_notes'):
                    self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_restart_preserves_answers(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            path = Path(folder) / 'existing.sqlite3'
            initialize(path)
            with connect(path) as db:
                attempt_id = start_attempt(db, 20251, 'ingles')
                question_id = serialize_attempt(db, attempt_id)['questions'][0]['id']
                save_answer(db, attempt_id, question_id, 'D')
            initialize(path)
            with connect(path) as db:
                self.assertEqual(serialize_attempt(db, attempt_id)['questions'][0]['selected_option'], 'D')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0], 555)
