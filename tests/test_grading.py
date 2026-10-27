import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.storage import DB_PATH, ROOT, connect, initialize
from app.service import InvalidRequest, start_attempt, save_answer, serialize_attempt, submit_attempt


class GradingTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.path = Path(self.temp.name) / 'test.sqlite3'
        source = sqlite3.connect(DB_PATH)
        target = sqlite3.connect(self.path)
        source.backup(target)
        source.close()
        target.close()
        self.db = connect(self.path)
        self.db.execute('DELETE FROM answers')
        self.db.execute('DELETE FROM attempts')
        self.db.execute('DELETE FROM error_notes')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_database_coverage(self):
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM exams').fetchone()[0],6)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM questions').fetchone()[0],555)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM questions WHERE cancelled=1').fetchone()[0],5)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_every_exam_and_language_perfect_answers(self):
        for exam in self.db.execute('SELECT id FROM exams').fetchall():
            for language in ('ingles','espanhol'):
                attempt_id = start_attempt(self.db,exam['id'],language)
                questions = self.db.execute("SELECT * FROM questions WHERE exam_id=? AND language IN ('comum',?)",(exam['id'],language)).fetchall()
                self.assertEqual(len(questions),90)
                for q in questions:
                    if not q['cancelled']:
                        save_answer(self.db,attempt_id,q['id'],q['correct_option'])
                score = submit_attempt(self.db,attempt_id)['score']
                self.assertEqual(score['percent'],100)
                self.assertEqual(score['wrong'],0)
                self.assertEqual(score['blank'],0)

    def test_keys_are_hidden_before_submission(self):
        attempt_id = start_attempt(self.db,20251,'ingles')
        result = serialize_attempt(self.db,attempt_id)
        self.assertNotIn('correct_option',json.dumps(result))
        self.assertNotIn('score',result)
        self.assertNotIn('cancelled',json.dumps(result))

    def test_wrong_blank_and_correct(self):
        attempt_id = start_attempt(self.db,20251,'ingles')
        questions = serialize_attempt(self.db,attempt_id)['questions']
        save_answer(self.db,attempt_id,questions[0]['id'],'D')
        save_answer(self.db,attempt_id,questions[1]['id'],'A')
        score = submit_attempt(self.db,attempt_id)['score']
        self.assertEqual((score['correct'],score['wrong'],score['blank']),(1,1,88))

    def test_cancelled_answers_excluded_even_if_answered(self):
        attempt_id = start_attempt(self.db,20252,'ingles')
        for q in self.db.execute('SELECT id FROM questions WHERE exam_id=20252 AND cancelled=1').fetchall():
            save_answer(self.db,attempt_id,q['id'],'A')
        score = submit_attempt(self.db,attempt_id)['score']
        self.assertEqual((score['valid'],score['cancelled'],score['blank'],score['wrong']),(87,3,87,0))

    def test_language_variants_have_their_own_answers(self):
        for language, expected in [('ingles','D'),('espanhol','B')]:
            attempt_id = start_attempt(self.db,20251,language)
            q = serialize_attempt(self.db,attempt_id)['questions'][0]
            save_answer(self.db,attempt_id,q['id'],expected)
            self.assertEqual(submit_attempt(self.db,attempt_id)['score']['correct'],1)

    def test_cannot_answer_other_exam_or_language(self):
        attempt_id = start_attempt(self.db,20251,'ingles')
        for query in ["SELECT id FROM questions WHERE exam_id=20241 LIMIT 1", "SELECT id FROM questions WHERE exam_id=20251 AND language='espanhol' LIMIT 1"]:
            with self.assertRaises(InvalidRequest):
                save_answer(self.db,attempt_id,self.db.execute(query).fetchone()[0],'A')

    def test_save_replace_clear_and_persist(self):
        attempt_id = start_attempt(self.db,20231,'ingles')
        q = serialize_attempt(self.db,attempt_id)['questions'][0]
        save_answer(self.db,attempt_id,q['id'],'A')
        save_answer(self.db,attempt_id,q['id'],'B')
        self.db.commit()
        with connect(self.path) as other:
            self.assertEqual(serialize_attempt(other,attempt_id)['questions'][0]['selected_option'],'B')
        other.close()
        save_answer(self.db,attempt_id,q['id'],None)
        self.assertIsNone(serialize_attempt(self.db,attempt_id)['questions'][0]['selected_option'])

    def test_correction_is_final_and_idempotent(self):
        attempt_id = start_attempt(self.db,20241,'espanhol')
        result = submit_attempt(self.db,attempt_id)
        self.assertEqual(submit_attempt(self.db,attempt_id),result)
        with self.assertRaises(InvalidRequest):
            save_answer(self.db,attempt_id,result['questions'][0]['id'],'A')

    def test_invalid_answer_rejected(self):
        attempt_id = start_attempt(self.db,20251,'ingles')
        q = serialize_attempt(self.db,attempt_id)['questions'][0]
        with self.assertRaises(InvalidRequest):
            save_answer(self.db,attempt_id,q['id'],'F')


if __name__ == '__main__':
    unittest.main()
