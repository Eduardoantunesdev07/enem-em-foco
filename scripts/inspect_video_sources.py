"""Read publisher embeds and YouTube metadata for manual catalogue curation."""
import concurrent.futures
import html
import json
import re
import requests

PAGES = [
    'https://vestibulares.estrategia.com/portal/enem-e-vestibulares/enem/gabarito-enem-2023-correcao-1-dia/',
    'https://vestibulares.estrategia.com/portal/enem-e-vestibulares/enem/gabarito-enem-2023-correcao-2-dia/',
    'https://vestibulares.estrategia.com/portal/noticias/gabarito-enem-2024-correcao-do-1o-dia-de-prova/',
    'https://vestibulares.estrategia.com/portal/enem-e-vestibulares/enem/gabarito-enem-2024-correcao-2-dia/',
]


def inspect_page(url):
    r = requests.get(url,timeout=40)
    r.raise_for_status()
    embeds = re.findall(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=|live/)|youtu\.be/)([\w-]{11})',html.unescape(r.text))
    return {'source':url,'ids':list(dict.fromkeys(embeds))}


def inspect_video(video_id):
    r = requests.get('https://www.youtube.com/oembed', params={'url':f'https://www.youtube.com/watch?v={video_id}','format':'json'},timeout=30)
    if r.status_code != 200:
        return {'id':video_id,'status':r.status_code}
    d=r.json()
    return {'id':video_id,'status':r.status_code,'title':d['title'],'channel':d['author_name'],'channel_url':d['author_url']}


if __name__=='__main__':
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    verify_catalog='--catalog' in sys.argv
    if verify_catalog:
        catalog=json.loads((root/'data/videos.json').read_text(encoding='utf-8'))
        ids=[v['youtube_id'] for v in catalog['videos']]
    else:
        ids=sys.argv[1:]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(inspect_video,ids)) if ids else list(pool.map(inspect_page,PAGES))
    if verify_catalog:
        for expected,actual in zip(catalog['videos'],result):
            if actual['status']!=200 or actual['channel'].strip()!=expected['channel'].strip():
                raise ValueError(f"Video or channel mismatch: {expected['id']}")
        from datetime import datetime,timezone
        report={'checked_at':datetime.now(timezone.utc).isoformat(),'method':'YouTube oEmbed title and channel; publisher pages used for coverage','videos':result}
        (root/'data/video-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
