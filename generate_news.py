#!/usr/bin/env python
"""
홈앤쇼핑 AI Daily News 생성기
네이버 뉴스 API로 홈쇼핑 뉴스를 수집해 Claude가 카드뉴스 3장을 만들고
daily_news.html 에 저장합니다.

필요한 환경변수 (GitHub Secrets):
  ANTHROPIC_API_KEY    — Claude API 키
  NAVER_CLIENT_ID      — 네이버 개발자센터 Client ID
  NAVER_CLIENT_SECRET  — 네이버 개발자센터 Client Secret
"""

import anthropic
import json
import os
import re
import requests
from datetime import datetime

# ── 네이버 뉴스 검색 키워드 ───────────────────────────────
SEARCH_QUERIES = ['홈쇼핑', '라이브커머스', '홈앤쇼핑']
NAVER_API_URL  = 'https://openapi.naver.com/v1/search/news.json'


def fetch_naver_news() -> list[dict]:
    """네이버 뉴스 API로 홈쇼핑 관련 최신 뉴스 수집"""
    client_id     = os.environ.get('NAVER_CLIENT_ID', '')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        print("⚠️  NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음 → 네이버 뉴스 건너뜀")
        return []

    headers = {
        'X-Naver-Client-Id':     client_id,
        'X-Naver-Client-Secret': client_secret,
    }

    articles = []
    seen_titles = set()

    for query in SEARCH_QUERIES:
        try:
            resp = requests.get(
                NAVER_API_URL,
                headers=headers,
                params={'query': query, 'display': 10, 'sort': 'date'},
                timeout=10,
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
            continue

    print(f"네이버 뉴스 총 {len(articles)}건 수집")
    return articles[:10]


def generate_cards(articles: list[dict]) -> list[dict]:
    """Claude로 카드뉴스 3장 생성"""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 없습니다.")

    if articles:
        news_text = "\n\n".join(
            f"[뉴스{i+1}] {a['title']}\n{a['summary']}"
            for i, a in enumerate(articles[:7])
        )
        context = f"아래 오늘의 홈쇼핑 실제 뉴스를 참고하세요:\n\n{news_text}"
    else:
        context = "오늘의 홈쇼핑·이커머스 산업 트렌드를 일반 지식으로 작성하세요."

    prompt = f"""{context}

위 내용을 바탕으로 홈앤쇼핑 임직원이 30초 안에 파악할 수 있는 카드뉴스 3장을 만들어주세요.
각 카드는 서로 다른 주제이며, 경영진도 볼 수 있도록 수치와 인사이트를 포함하세요.

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
    "footer": "한 줄 인사이트 (35자 내외)"
  }},
  {{...}},
  {{...}}
]"""

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    text = msg.content[0].text.strip()
    m = re.search(r'\[[\s\S]*\]', text)
    if not m:
        raise ValueError("AI 응답 파싱 실패")
    return json.loads(m.group())


def build_html(cards: list[dict]) -> str:
    today    = datetime.now().strftime('%B %d, %Y').upper()
    today_kr = datetime.now().strftime('%Y년 %m월 %d일')
    cards_json = json.dumps(cards[:3], ensure_ascii=False)

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
  display:flex;
  flex-direction:column;
  align-items:center;
  padding:32px 20px 48px;
  font-family:'Malgun Gothic','맑은 고딕','Apple SD Gothic Neo',sans-serif;
}}
.page-label {{
  font-size:12px; font-weight:700; color:#cc2b2b;
  letter-spacing:2.5px; margin-bottom:4px; text-align:center;
}}
.page-date {{
  font-size:11px; color:#777; letter-spacing:1px;
  margin-bottom:30px; text-align:center;
}}
.cards-wrap {{ display:flex; flex-direction:column; gap:24px; width:100%; max-width:900px; }}

/* ── 카드 (cardnews.html 동일 디자인) ── */
.card {{
  width:100%; background:#f0e9d8; padding:44px 56px 36px;
  display:flex; flex-direction:column;
  box-shadow:0 4px 24px rgba(0,0,0,.15);
}}
.c-top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:22px; }}
.c-handle   {{ font-size:11px; font-weight:700; color:#cc2b2b; letter-spacing:.8px; margin-bottom:3px; }}
.c-category {{ font-size:13px; color:#5a4a3a; }}
.c-date     {{ font-size:11px; color:#9a8a7a; letter-spacing:1px; }}
.c-title    {{ font-size:48px; font-weight:900; color:#111; line-height:1.08; letter-spacing:-1.5px; margin-bottom:38px; }}
.c-title .hl {{ color:#cc2b2b; }}
.c-items    {{ display:flex; flex-direction:column; gap:6px; }}
.c-item     {{ display:flex; align-items:center; padding:15px 0 15px 22px; border-left:4px solid #cc2b2b; }}
.i-num      {{ font-size:28px; font-weight:900; color:#cc2b2b; width:52px; flex-shrink:0; line-height:1; }}
.i-kw       {{ font-size:17px; font-weight:700; color:#111; width:220px; flex-shrink:0; }}
.i-desc     {{ font-size:14.5px; color:#666; flex:1; }}
.i-desc b   {{ color:#cc2b2b; font-weight:700; }}
.i-desc em  {{ color:#111; font-style:normal; font-weight:700; }}
.c-divider  {{ border:none; border-top:1px solid #c8bdb0; margin:28px 0 16px; }}
.c-footer   {{ display:flex; justify-content:space-between; align-items:center; }}
.c-foot-text {{ font-size:13px; font-weight:700; color:#222; }}
.c-credit    {{ font-size:11px; color:#9a8a7a; }}

/* ── 컨트롤 ── */
.ctrl {{
  margin-top:20px; display:flex; gap:10px;
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
.hint {{ font-size:11px; color:#888; }}

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

<div class="cards-wrap" id="wrap"></div>

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
  <span class="hint">※ PDF 저장 시 '배경 그래픽' 체크</span>
</div>

<script>
var CARDS = {cards_json};
var DATE  = '{today}';

CARDS.forEach(function(card) {{
  var items = (card.items || []).map(function(it, i) {{
    return '<div class="c-item">'
      + '<span class="i-num">'  + (i + 1) + '</span>'
      + '<span class="i-kw">'   + (it.keyword || '') + '</span>'
      + '<span class="i-desc">' + (it.desc    || '') + '</span>'
      + '</div>';
  }}).join('');

  var el = document.createElement('div');
  el.className = 'card';
  el.innerHTML =
    '<div class="c-top">'
      + '<div>'
        + '<div class="c-handle">@홈앤쇼핑_AI_DAILY_NEWS</div>'
        + '<div class="c-category">' + (card.category || '') + '</div>'
      + '</div>'
      + '<div class="c-date">' + DATE + '</div>'
    + '</div>'
    + '<div class="c-title">'  + (card.title  || '') + '</div>'
    + '<div class="c-items">'  + items + '</div>'
    + '<hr class="c-divider">'
    + '<div class="c-footer">'
      + '<div class="c-foot-text">' + (card.footer || '') + '</div>'
      + '<div class="c-credit">© 홈앤쇼핑 AI Daily · powered by Claude</div>'
    + '</div>';

  document.getElementById('wrap').appendChild(el);
}});
</script>
</body>
</html>"""


if __name__ == '__main__':
    print("── 홈앤쇼핑 AI Daily News 생성 시작 ──")

    articles = fetch_naver_news()

    print("Claude로 카드뉴스 생성 중...")
    cards = generate_cards(articles)
    print(f"카드 {len(cards)}장 생성 완료")

    html = build_html(cards)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daily_news.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"저장 완료 → {out}")
