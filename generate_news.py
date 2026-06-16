#!/usr/bin/env python
"""
홈앤쇼핑 AI Daily News 생성기
- 왼쪽 3장: '홈앤쇼핑' 자사 뉴스
- 오른쪽 3장: '홈쇼핑 / 라이브커머스' 업계 뉴스
daily_news.html + daily_news.json 저장

필요한 환경변수 (GitHub Secrets 또는 secrets.toml):
  ANTHROPIC_API_KEY
  NAVER_CLIENT_ID
  NAVER_CLIENT_SECRET
"""

import anthropic
import httpx
import json
import os
import re
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NAVER_API_URL = 'https://openapi.naver.com/v1/search/news.json'


def _env(key: str) -> str:
    """환경변수 → secrets.toml 순서로 값을 읽는다"""
    val = os.environ.get(key, '')
    if val:
        return val
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        toml_path = os.path.join(base, '.streamlit', 'secrets.toml')
        import tomllib
        with open(toml_path, 'rb') as f:
            return tomllib.load(f).get(key, '')
    except (ImportError, FileNotFoundError, Exception):
        pass
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        toml_path = os.path.join(base, '.streamlit', 'secrets.toml')
        with open(toml_path, encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if s.startswith(key):
                    _, _, v = s.partition('=')
                    return v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ''


def fetch_naver_news(queries: list[str], max_articles: int = 10) -> list[dict]:
    """지정 쿼리로 네이버 뉴스 수집"""
    client_id     = _env('NAVER_CLIENT_ID')
    client_secret = _env('NAVER_CLIENT_SECRET')

    placeholder = lambda v: not v or v.startswith('여기에')
    if placeholder(client_id) or placeholder(client_secret):
        return []

    headers = {
        'X-Naver-Client-Id':     client_id,
        'X-Naver-Client-Secret': client_secret,
    }

    articles = []
    seen_titles = set()

    for query in queries:
        try:
            resp = requests.get(
                NAVER_API_URL,
                headers=headers,
                params={'query': query, 'display': 10, 'sort': 'date'},
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            items = resp.json().get('items', [])

            for item in items:
                title   = re.sub(r'<[^>]+>', '', item.get('title', '')).strip()
                summary = re.sub(r'<[^>]+>', '', item.get('description', '')).strip()
                link    = item.get('originallink', item.get('link', ''))

                if title and title not in seen_titles:
                    seen_titles.add(title)
                    articles.append({
                        'title':   title,
                        'summary': summary[:400],
                        'link':    link,
                    })

            print(f"  [{query}] {len(items)}건 수집")
        except Exception as e:
            print(f"  [{query}] 오류: {e}")

    print(f"  소계 {len(articles)}건")
    return articles[:max_articles]


def generate_cards(articles: list[dict], topic: str) -> list[dict]:
    """Claude로 카드뉴스 3장 생성"""
    api_key = _env('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 가 없습니다. secrets.toml 또는 환경변수를 확인하세요.")

    if articles:
        news_text = "\n\n".join(
            f"[뉴스{i+1}] {a['title']}\n{a['summary']}\nURL: {a['link']}"
            for i, a in enumerate(articles[:7])
        )
        context = f"아래 오늘의 {topic} 실제 뉴스를 참고하세요:\n\n{news_text}"
    else:
        context = f"오늘의 {topic} 트렌드를 일반 지식으로 작성하세요."

    prompt = f"""{context}

위 내용을 바탕으로 홈앤쇼핑 임직원이 30초 안에 파악할 수 있는 카드뉴스 3장을 만들어주세요.
주제: {topic}
각 카드는 서로 다른 주제이며, 경영진도 볼 수 있도록 수치와 인사이트를 포함하세요.
각 카드마다 내용의 근거가 된 뉴스 URL을 1~2개 sources에 포함하세요.

JSON 배열로만 응답하세요 (다른 텍스트 없이):
[
  {{
    "category": "카테고리 (10자 내외: 실적·성장 / 트렌드 / 정책·규제 / 경쟁사 동향 등)",
    "title": "카드 제목 (15자 내외, 임팩트 있게, 필요시 <br>으로 줄바꿈)",
    "items": [
      {{"keyword": "키워드 (8자 내외)", "desc": "설명 (35자 내외, 수치 포함, <b>강조</b> 가능)"}},
      {{"keyword": "키워드",            "desc": "설명"}},
      {{"keyword": "키워드",            "desc": "설명"}}
    ],
    "footer": "한 줄 인사이트 (35자 내외)",
    "sources": [
      {{"title": "기사 제목 (20자 내외로 축약)", "url": "https://원문URL"}}
    ]
  }},
  {{...}},
  {{...}}
]"""

    client = anthropic.Anthropic(api_key=api_key, http_client=httpx.Client(verify=False))

    for attempt in range(3):
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\[[\s\S]*\]', text)
        if not m:
            print(f"  [시도 {attempt+1}] JSON 배열 없음, 재시도...")
            continue
        try:
            return json.loads(m.group())
        except json.JSONDecodeError as e:
            print(f"  [시도 {attempt+1}] JSON 파싱 오류: {e}, 재시도...")

    raise ValueError("AI 응답 파싱 3회 실패 - 나중에 다시 시도하세요.")


def _card_html(card: dict, date: str) -> str:
    """카드 1장 HTML 조각 생성"""
    items_html = ''.join(
        f'<div class="c-item">'
        f'<span class="i-num">{i+1}</span>'
        f'<span class="i-kw">{it.get("keyword","")}</span>'
        f'<span class="i-desc">{it.get("desc","")}</span>'
        f'</div>'
        for i, it in enumerate(card.get('items', []))
    )

    sources = card.get('sources', [])
    sources_html = ''
    if sources:
        links = ''.join(
            f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["title"]}</a>'
            for s in sources
        )
        sources_html = (
            '<div class="c-sources">'
            '<div class="c-sources-label">출처 SOURCE</div>'
            f'{links}</div>'
        )

    return (
        f'<div class="card">'
        f'<div class="c-top">'
        f'<div><div class="c-handle">@홈앤쇼핑_AI_DAILY_NEWS</div>'
        f'<div class="c-category">{card.get("category","")}</div></div>'
        f'<div class="c-date">{date}</div>'
        f'</div>'
        f'<div class="c-title">{card.get("title","")}</div>'
        f'<div class="c-items">{items_html}</div>'
        f'<hr class="c-divider">'
        f'<div class="c-footer">'
        f'<div class="c-foot-text">{card.get("footer","")}</div>'
        f'<div class="c-credit">© 홈앤쇼핑 AI Daily · powered by Claude</div>'
        f'</div>'
        f'{sources_html}'
        f'</div>'
    )


def build_html(left_cards: list[dict], right_cards: list[dict]) -> str:
    today    = datetime.now().strftime('%B %d, %Y').upper()
    today_kr = datetime.now().strftime('%Y년 %m월 %d일')

    left_html  = '\n'.join(_card_html(c, today) for c in left_cards[:3])
    right_html = '\n'.join(_card_html(c, today) for c in right_cards[:3])

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>홈앤쇼핑 AI DAILY NEWS · {today_kr}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background:#d4d0c8;
  min-height:100vh;
  display:flex; flex-direction:column; align-items:center;
  padding:32px 20px 48px;
  font-family:'Malgun Gothic','맑은 고딕','Apple SD Gothic Neo',sans-serif;
}}
.page-label {{ font-size:12px; font-weight:700; color:#cc2b2b; letter-spacing:2.5px; margin-bottom:4px; text-align:center; }}
.page-date  {{ font-size:11px; color:#777; letter-spacing:1px; margin-bottom:30px; text-align:center; }}

/* ── 2열 그리드 ── */
.grid-wrap {{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:28px;
  width:100%; max-width:1860px;
}}
.col {{ display:flex; flex-direction:column; gap:20px; }}
.col-header {{
  font-size:11px; font-weight:700; color:#fff;
  background:#cc2b2b; letter-spacing:1.5px;
  padding:6px 14px; align-self:flex-start;
}}

/* ── 카드 ── */
.card {{
  background:#f0e9d8; padding:36px 44px 28px;
  display:flex; flex-direction:column;
  box-shadow:0 4px 24px rgba(0,0,0,.15);
}}
.c-top      {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:18px; }}
.c-handle   {{ font-size:10px; font-weight:700; color:#cc2b2b; letter-spacing:.8px; margin-bottom:2px; }}
.c-category {{ font-size:12px; color:#5a4a3a; }}
.c-date     {{ font-size:10px; color:#9a8a7a; letter-spacing:1px; }}
.c-title    {{ font-size:36px; font-weight:900; color:#111; line-height:1.1; letter-spacing:-1px; margin-bottom:28px; }}
.c-title .hl {{ color:#cc2b2b; }}
.c-items    {{ display:flex; flex-direction:column; gap:4px; }}
.c-item     {{ display:flex; align-items:center; padding:11px 0 11px 18px; border-left:4px solid #cc2b2b; }}
.i-num      {{ font-size:22px; font-weight:900; color:#cc2b2b; width:42px; flex-shrink:0; line-height:1; }}
.i-kw       {{ font-size:14px; font-weight:700; color:#111; width:160px; flex-shrink:0; }}
.i-desc     {{ font-size:12.5px; color:#666; flex:1; }}
.i-desc b   {{ color:#cc2b2b; font-weight:700; }}
.i-desc em  {{ color:#111; font-style:normal; font-weight:700; }}
.c-divider  {{ border:none; border-top:1px solid #c8bdb0; margin:20px 0 12px; }}
.c-footer   {{ display:flex; justify-content:space-between; align-items:center; }}
.c-foot-text {{ font-size:12px; font-weight:700; color:#222; }}
.c-credit    {{ font-size:10px; color:#9a8a7a; }}
.c-sources   {{ margin-top:10px; padding-top:8px; border-top:1px dashed #d0c4b4; }}
.c-sources-label {{ font-size:9px; font-weight:700; color:#9a8a7a; letter-spacing:.8px; margin-bottom:3px; }}
.c-sources a {{
  display:inline-block; font-size:10px; color:#7a6a5a;
  text-decoration:none; margin-right:10px; line-height:1.8;
}}
.c-sources a:hover {{ color:#cc2b2b; text-decoration:underline; }}

/* ── 컨트롤 ── */
.ctrl {{
  margin-top:24px; display:flex; gap:10px;
  align-items:center; flex-wrap:wrap; justify-content:center;
}}
.btn-home, .btn-print {{
  padding:8px 20px; border:none; border-radius:5px;
  font-size:13px; font-family:inherit; cursor:pointer;
}}
.btn-home {{
  background:#e8192c; color:#fff;
  display:inline-flex; align-items:center; gap:6px; text-decoration:none;
}}
.btn-home:hover  {{ background:#c8001f; }}
.btn-print       {{ background:#333; color:#fff; }}
.btn-print:hover {{ background:#111; }}

@media (max-width:900px) {{
  .grid-wrap {{ grid-template-columns:1fr; }}
}}
@media print {{
  body {{ background:none; padding:0; }}
  .ctrl, .page-label, .page-date {{ display:none; }}
  .card {{ box-shadow:none; page-break-after:always; }}
}}
</style>
</head>
<body>

<div class="page-label">@홈앤쇼핑_AI_DAILY_NEWS</div>
<div class="page-date">{today_kr} · 네이버 뉴스 × Claude AI</div>

<div class="grid-wrap">
  <div class="col">
    <div class="col-header">홈앤쇼핑 자사 뉴스</div>
    {left_html}
  </div>
  <div class="col">
    <div class="col-header">홈쇼핑 업계 동향</div>
    {right_html}
  </div>
</div>

<div class="ctrl">
  <a class="btn-home" href="https://prettykbk81.github.io/hnsinfo/">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
      <polyline points="9,22 9,12 15,12 15,22"/>
    </svg>
    홈으로
  </a>
  <button class="btn-print" onclick="window.print()">🖨️ 인쇄 / PDF</button>
</div>

</body>
</html>"""


if __name__ == '__main__':
    print("── 홈앤쇼핑 AI Daily News 생성 시작 ──")

    naver_id     = _env('NAVER_CLIENT_ID')
    naver_secret = _env('NAVER_CLIENT_SECRET')
    claude_key   = _env('ANTHROPIC_API_KEY')

    print(f"  Claude API  : {'OK' if claude_key else '[!] 없음 - secrets.toml 확인'}")
    print(f"  Naver ID    : {'OK' if naver_id and not naver_id.startswith('여기에') else '[!] 없음 - secrets.toml 확인'}")
    print(f"  Naver Secret: {'OK' if naver_secret and not naver_secret.startswith('여기에') else '[!] 없음 - secrets.toml 확인'}")
    print()

    print("[왼쪽] 홈앤쇼핑 자사 뉴스 수집...")
    left_articles = fetch_naver_news(['홈앤쇼핑'])

    print("[오른쪽] 홈쇼핑 업계 뉴스 수집...")
    right_articles = fetch_naver_news(['홈쇼핑', '라이브커머스'])

    print("\nClaude로 카드뉴스 생성 중...")
    print("  [왼쪽] 홈앤쇼핑 자사 카드 생성...")
    left_cards  = generate_cards(left_articles,  topic='홈앤쇼핑 자사')
    print("  [오른쪽] 홈쇼핑 업계 카드 생성...")
    right_cards = generate_cards(right_articles, topic='홈쇼핑 업계 동향')
    print(f"카드 총 {len(left_cards) + len(right_cards)}장 생성 완료")

    base = os.path.dirname(os.path.abspath(__file__))

    html = build_html(left_cards, right_cards)
    out_html = os.path.join(base, 'daily_news.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"저장 완료 → {out_html}")

    out_json = os.path.join(base, 'daily_news.json')
    payload = {
        'date':    datetime.now().strftime('%Y년 %m월 %d일'),
        'date_en': datetime.now().strftime('%B %d, %Y').upper(),
        'left':    left_cards[:3],
        'right':   right_cards[:3],
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"저장 완료 → {out_json}")
