"""Download the regular blue booklets directly from the Inep yearly index."""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request
import urllib.error
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos/'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href' and value)


def fetch(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        # The official file host sometimes resets TLS while its HTTP endpoint works.
        if not url.startswith('https://download.inep.gov.br/'):
            raise
        response = requests.get(url.replace('https://', 'http://', 1), timeout=120)
        response.raise_for_status()
        return response.content


def download(item):
    target = ROOT / item['local_path']
    if not target.exists():
        content = fetch(item['url'])
        if not content.startswith(b'%PDF-'):
            raise ValueError(f"Not a PDF: {item['url']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    content = target.read_bytes()
    if not content.startswith(b'%PDF-'):
        raise ValueError(f'Invalid cached PDF: {target}')
    return {**item, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}


def main():
    items = []
    for year in (2023, 2024, 2025):
        index = BASE + str(year)
        parser = Links()
        parser.feed(fetch(index).decode('utf-8'))
        # First CD1/CD7 occurrences belong to the regular national application.
        for day, booklet in ((1, 1), (2, 7)):
            for kind, token in (('prova', '_PV_'), ('gabarito', '_GB_')):
                candidates = [u for u in parser.links if 'download.inep.gov.br' in u and token.lower() in u.lower()
                              and f'CD{booklet}.pdf'.lower() in u.lower()]
                if not candidates:
                    raise ValueError(f'Missing official link: {year} {day} {kind}')
                items.append({'year': year, 'day': day, 'booklet': booklet, 'color': 'azul',
                              'application': 'regular', 'kind': kind, 'index_url': index,
                              'url': candidates[0], 'local_path': f'data/official/{year}/dia{day}_{kind}.pdf'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(download, items))
    (ROOT / 'data/sources.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in result:
        print(f"{item['year']} dia {item['day']} {item['kind']}: {item['bytes']} bytes")


if __name__ == '__main__':
    main()
