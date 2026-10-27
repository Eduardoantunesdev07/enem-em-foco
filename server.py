"""Local single-user web app. Run with: python server.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import urlparse

from app.storage import ROOT, connect, initialize
from app.service import InvalidRequest, get_attempt, serialize_attempt, start_attempt, save_answer, submit_attempt


class Handler(BaseHTTPRequestHandler):
    def json_response(self, value, status=200):
        content = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def file_response(self, path):
        if not path.is_file():
            return self.json_response({'error': 'Arquivo não encontrado.'}, 404)
        content = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'self'; frame-src https://www.youtube-nocookie.com; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.json_response({'error': 'Endereço não permitido.'}, 403)
        path = urlparse(self.path).path
        try:
            with connect() as db:
                if path == '/api/videos':
                    return self.json_response(json.loads((ROOT / 'data/videos.json').read_text(encoding='utf-8')))
                if path == '/api/exams':
                    exams = [dict(r) for r in db.execute('''SELECT e.id,e.year,e.day,e.color,e.booklet,e.page_count,e.source_page,
                        (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id AND q.language IN ('comum','ingles')) question_count
                        FROM exams e ORDER BY year DESC,day''')]
                    return self.json_response({'exams': exams, 'question_count': db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]})
                if path == '/api/history':
                    rows = db.execute('''SELECT a.*,e.year,e.day FROM attempts a JOIN exams e ON e.id=a.exam_id
                        ORDER BY a.created_at DESC,a.rowid DESC''').fetchall()
                    history = []
                    for row in rows:
                        item = dict(row)
                        if row['status'] == 'submitted':
                            item['score'] = serialize_attempt(db,row['id'])['score']
                        history.append(item)
                    return self.json_response(history)
                if path == '/api/errors':
                    rows = db.execute('''SELECT DISTINCT q.id,q.number,q.area,q.language,e.year,e.day,
                        n.reason,n.note,n.updated_at FROM answers a JOIN attempts t ON t.id=a.attempt_id
                        JOIN questions q ON q.id=a.question_id JOIN exams e ON e.id=q.exam_id
                        LEFT JOIN error_notes n ON n.question_id=q.id
                        WHERE t.status='submitted' AND q.cancelled=0 AND a.selected_option<>q.correct_option
                        ORDER BY e.year DESC,q.number''').fetchall()
                    return self.json_response([dict(r) for r in rows])
                match = re.fullmatch(r'/api/attempts/([\w-]+)',path)
                if match:
                    result = serialize_attempt(db,match[1])
                    result['exam']['page_count'] = db.execute('SELECT page_count FROM exams WHERE id=?', (result['exam_id'],)).fetchone()[0]
                    return self.json_response(result)
                match = re.fullmatch(r'/papers/(\d+)\.pdf',path)
                if match:
                    row = db.execute('SELECT paper_path FROM exams WHERE id=?',(int(match[1]),)).fetchone()
                    if row:
                        return self.file_response(ROOT / row[0])
                match = re.fullmatch(r'/pages/(\d+)/(\d+)\.webp',path)
                if match:
                    return self.file_response(ROOT / 'data/pages' / match[1] / f'{match[2]}.webp')
                if path in ('/', '/app.js', '/style.css', '/favicon.svg'):
                    return self.file_response(ROOT / 'web' / ('index.html' if path == '/' else path[1:]))
            return self.json_response({'error': 'Página não encontrada.'},404)
        except InvalidRequest as error:
            self.json_response({'error': str(error)},404)

    def do_POST(self):
        if not self.valid_host():
            return self.json_response({'error': 'Endereço não permitido.'},403)
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.json_response({'error': 'Origem não permitida.'},403)
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.json_response({'error': 'Envie os dados em JSON.'},415)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 0 or length > 100_000:
                raise InvalidRequest('Pedido muito grande.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise InvalidRequest('Dados inválidos.')
            path = urlparse(self.path).path
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if path == '/api/attempts':
                    attempt_id = start_attempt(db,int(data.get('exam_id',0)),data.get('language','ingles'))
                    db.commit()
                    return self.json_response({'id': attempt_id},201)
                match = re.fullmatch(r'/api/attempts/([\w-]+)/(answer|submit)',path)
                if match:
                    if match[2] == 'answer':
                        save_answer(db,match[1],int(data.get('question_id',0)),data.get('option'))
                        db.commit()
                        return self.json_response({'saved': True})
                    result = submit_attempt(db,match[1])
                    db.commit()
                    return self.json_response(result)
                if path == '/api/notes':
                    question_id = int(data.get('question_id',0))
                    reason, note = data.get('reason'), data.get('note','')
                    if reason not in ('conteudo','atencao','interpretacao','tempo') or not isinstance(note,str) or len(note)>5000:
                        raise InvalidRequest('Anotação inválida.')
                    if not db.execute('''SELECT 1 FROM answers a JOIN attempts t ON t.id=a.attempt_id
                        JOIN questions q ON q.id=a.question_id WHERE q.id=? AND t.status='submitted'
                        AND q.cancelled=0 AND a.selected_option<>q.correct_option''',(question_id,)).fetchone():
                        raise InvalidRequest('Esta questão ainda não está no caderno de erros.')
                    db.execute('''INSERT INTO error_notes(question_id,reason,note) VALUES(?,?,?)
                        ON CONFLICT(question_id) DO UPDATE SET reason=excluded.reason,note=excluded.note,
                        updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')''',(question_id,reason,note))
                    db.commit()
                    return self.json_response({'saved': True})
            return self.json_response({'error': 'Operação não encontrada.'},404)
        except (InvalidRequest,ValueError,TypeError) as error:
            self.json_response({'error': str(error)},400)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8126)
    parser.add_argument('--database',type=Path,help='Use another local SQLite database (for backup or testing).')
    args = parser.parse_args()
    if args.database:
        import app.storage
        app.storage.DB_PATH = args.database.resolve()
    initialize()
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'ENEM em Foco: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
