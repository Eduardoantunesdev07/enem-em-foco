"""HTTP integration checks against an isolated copy of the database."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

from app.storage import DB_PATH, ROOT


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        path = Path(cls.temp.name) / 'http.sqlite3'
        source, target = sqlite3.connect(DB_PATH), sqlite3.connect(path)
        source.backup(target)
        source.close()
        target.close()
        cls.process = subprocess.Popen([sys.executable,'-u','server.py','--port','0','--database',str(path)],cwd=ROOT,
                                       stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        cls.base = cls.process.stdout.readline().strip().split()[-1]
        if not cls.base.startswith('http://127.0.0.1:'):
            cls.process.terminate()
            raise RuntimeError('Test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.process.stdout.close()
        cls.temp.cleanup()

    def request(self,path,data=None,headers=None):
        request = urllib.request.Request(self.base+path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers or ({'Content-Type':'application/json'} if data is not None else {}))
        with urllib.request.urlopen(request,timeout=10) as response:
            return response.status,json.load(response)

    def test_catalog_and_hidden_files(self):
        status,catalog = self.request('/api/exams')
        self.assertEqual((status,len(catalog['exams']),catalog['question_count']),(200,6,555))
        self.assertNotIn('correct_option',json.dumps(catalog))
        for path in ['/data/enem.sqlite3','/data/official/2025/dia1_gabarito.pdf','/database/schema.sql','/../server.py']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path)
            self.assertEqual(error.exception.code,404)

    def test_full_answer_correction_flow(self):
        _, created = self.request('/api/attempts',{'exam_id':20251,'language':'espanhol'})
        path = '/api/attempts/'+created['id']
        _,draft = self.request(path)
        self.assertNotIn('correct_option',json.dumps(draft))
        q1,q2 = draft['questions'][:2]
        self.request(path+'/answer',{'question_id':q1['id'],'option':'B'})
        self.request(path+'/answer',{'question_id':q2['id'],'option':'B'})
        _,result = self.request(path+'/submit',{})
        self.assertEqual((result['score']['correct'],result['score']['wrong'],result['score']['blank']),(1,1,88))
        self.assertEqual(result['questions'][1]['correct_option'],'A')
        self.request('/api/notes',{'question_id':q2['id'],'reason':'interpretacao','note':'HTTP integration test'})
        _, reopened = self.request(path)
        self.assertEqual(reopened['questions'][1]['note'],'HTTP integration test')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(path+'/answer',{'question_id':q1['id'],'option':'A'})
        self.assertEqual(error.exception.code,400)

    def test_cross_origin_write_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/attempts',{'exam_id':20251},headers={'Content-Type':'application/json','Origin':'https://example.org'})
        self.assertEqual(error.exception.code,403)

    def test_video_catalog_covers_all_exam_areas_each_year(self):
        status,catalog = self.request('/api/videos')
        self.assertEqual(status,200)
        videos = catalog['videos']
        self.assertEqual(len({v['youtube_id'] for v in videos}),len(videos))
        for year in (2023,2024,2025):
            corrections = [v for v in videos if v['kind']=='correcao' and v['year']==year]
            self.assertEqual({v['day'] for v in corrections},{1,2})
            self.assertEqual({a for v in corrections for a in v['areas']},{'linguagens','humanas','natureza','matematica'})
        lessons = [v for v in videos if v['kind']=='conteudo']
        self.assertTrue({'linguagens','humanas','natureza','matematica','redacao'} <= {a for v in lessons for a in v['areas']})
        for video in videos:
            self.assertRegex(video['youtube_id'],r'^[A-Za-z0-9_-]{11}$')
            self.assertTrue(video['teacher'])
            self.assertTrue(video['channel_url'].startswith('https://www.youtube.com/@'))
            self.assertTrue(video['source_url'].startswith('https://'))


if __name__ == '__main__':
    unittest.main()
