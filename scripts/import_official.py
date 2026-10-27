"""Validate official keys and index original pages without losing figures or formulas."""
import hashlib
import json
from pathlib import Path
import re
import sys

import pdfplumber
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import connect, initialize


def read_key(path, day):
    with pdfplumber.open(path) as document:
        lines = '\n'.join(page.extract_text() or '' for page in document.pages).splitlines()
    keys = {}
    for line in lines:
        tokens = line.split()
        if not tokens or not tokens[0].isdigit():
            continue
        if day == 1 and len(tokens) == 5:
            number, english, spanish, human_number, human_key = tokens
            keys[(int(number), 'ingles')] = english
            keys[(int(number), 'espanhol')] = spanish
            keys[(int(human_number), 'comum')] = human_key
        elif len(tokens) == 4:
            number, answer, other_number, other_answer = tokens
            if not other_number.isdigit():
                continue
            keys[(int(number), 'comum')] = answer
            keys[(int(other_number), 'comum')] = other_answer
    expected = ({(n, lang) for n in range(1, 6) for lang in ('ingles', 'espanhol')}
                | {(n, 'comum') for n in range(6, 91)}) if day == 1 else {(n, 'comum') for n in range(91, 181)}
    if set(keys) != expected or any(a not in ('A', 'B', 'C', 'D', 'E', 'Anulado') for a in keys.values()):
        raise ValueError(f'Incomplete or invalid answer key: {path}; missing={expected - set(keys)}')
    return keys


def index_pages(path, day):
    pages, occurrences = {}, {}
    with pdfplumber.open(path) as document:
        count = len(document.pages)
        for page_number, page in enumerate(document.pages, 1):
            text = page.extract_text() or ''
            for match in re.finditer(r'\bQUEST.O\s+(\d{1,3})\b', text, re.IGNORECASE):
                number = int(match.group(1))
                language = 'comum'
                if day == 1 and number <= 5:
                    seen = occurrences.get(number, 0)
                    if seen > 1:
                        raise ValueError(f'Ambiguous language variant for {path}: {number}')
                    language = ('ingles', 'espanhol')[seen]
                    occurrences[number] = seen + 1
                key = (number, language)
                if key in pages:
                    raise ValueError(f'Duplicate question heading: {path}: {key}')
                pages[key] = page_number
    return pages, count


def render_pages(path, exam_id):
    target = ROOT / 'data/pages' / str(exam_id)
    target.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(path)
    for i in range(len(document)):
        output = target / f'{i + 1}.webp'
        if not output.exists():
            page = document[i]
            image = page.render(scale=1.75).to_pil()
            image.save(output, format='WEBP', quality=90)
            page.close()
    document.close()


def main():
    sources = json.loads((ROOT / 'data/sources.json').read_text(encoding='utf-8'))
    initialize()
    report = []
    with connect() as db:
        for year in (2023, 2024, 2025):
            for day in (1, 2):
                paper = next(s for s in sources if (s['year'], s['day'], s['kind']) == (year, day, 'prova'))
                key = next(s for s in sources if (s['year'], s['day'], s['kind']) == (year, day, 'gabarito'))
                for item in (paper, key):
                    if hashlib.sha256((ROOT / item['local_path']).read_bytes()).hexdigest() != item['sha256']:
                        raise ValueError('Source file hash mismatch')
                keys = read_key(ROOT / key['local_path'], day)
                pages, page_count = index_pages(ROOT / paper['local_path'], day)
                if set(keys) != set(pages):
                    raise ValueError(f'Question index mismatch: {year}/{day}; missing={set(keys)-set(pages)}, extra={set(pages)-set(keys)}')
                exam_id = year * 10 + day
                db.execute('''INSERT INTO exams(id,year,day,booklet,page_count,source_page,paper_url,key_url,paper_path,key_path,paper_sha256,key_sha256)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    page_count=excluded.page_count,paper_url=excluded.paper_url,key_url=excluded.key_url,
                    paper_sha256=excluded.paper_sha256,key_sha256=excluded.key_sha256''',
                    (exam_id,year,day,paper['booklet'],page_count,paper['index_url'],paper['url'],key['url'],
                     paper['local_path'],key['local_path'],paper['sha256'],key['sha256']))
                for (number, language), answer in sorted(keys.items()):
                    area = ('linguagens' if number <= 45 else 'humanas' if number <= 90 else
                            'natureza' if number <= 135 else 'matematica')
                    db.execute('''INSERT INTO questions(exam_id,number,language,area,correct_option,cancelled,page)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(exam_id,number,language) DO UPDATE SET
                        area=excluded.area,correct_option=excluded.correct_option,cancelled=excluded.cancelled,page=excluded.page''',
                        (exam_id,number,language,area,None if answer == 'Anulado' else answer,
                         int(answer == 'Anulado'),pages[(number,language)]))
                report.append({'year': year,'day': day,'questions': len(keys),'pages': page_count,
                               'cancelled': [n for (n,l),a in keys.items() if a == 'Anulado']})
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    (ROOT / 'data/import-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for item in report:
        print(item, flush=True)
    if '--render' in sys.argv:
        for year in (2023,2024,2025):
            for day in (1,2):
                render_pages(ROOT / f'data/official/{year}/dia{day}_prova.pdf',year * 10 + day)
                print(f'Rendered {year}/{day}',flush=True)


if __name__ == '__main__':
    main()
