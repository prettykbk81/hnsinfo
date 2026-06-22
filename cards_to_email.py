"""
카드뉴스를 이미지로 변환하여 이메일 발송
Playwright로 각 카드를 개별 PNG 캡처 → HTML 이메일에 임베드
"""

import json
import os
import sys
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime


def _env(key: str) -> str:
    val = os.environ.get(key, '')
    if val:
        return val
    try:
        import tomllib
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, '.streamlit', 'secrets.toml'), 'rb') as f:
            return tomllib.load(f).get(key, '')
    except Exception:
        pass
    return ''


CARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#d4d0c8;padding:20px;font-family:'Malgun Gothic','맑은 고딕',sans-serif;}}
.card{{
  width:860px;background:#f0e9d8;padding:36px 44px 28px;
  box-shadow:0 4px 24px rgba(0,0,0,.15);
}}
.c-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px;}}
.c-handle{{font-size:10px;font-weight:700;color:#cc2b2b;letter-spacing:.8px;margin-bottom:2px;}}
.c-category{{font-size:12px;color:#5a4a3a;}}
.c-date{{font-size:10px;color:#9a8a7a;letter-spacing:1px;}}
.c-title{{font-size:36px;font-weight:900;color:#111;line-height:1.1;letter-spacing:-1px;margin-bottom:28px;}}
.c-items{{display:flex;flex-direction:column;gap:4px;}}
.c-item{{display:flex;align-items:center;padding:11px 0 11px 18px;border-left:4px solid #cc2b2b;}}
.i-num{{font-size:22px;font-weight:900;color:#cc2b2b;width:42px;flex-shrink:0;line-height:1;}}
.i-kw{{font-size:14px;font-weight:700;color:#111;width:160px;flex-shrink:0;}}
.i-desc{{font-size:12.5px;color:#666;flex:1;}}
.i-desc b{{color:#cc2b2b;font-weight:700;}}
.c-divider{{border:none;border-top:1px solid #c8bdb0;margin:20px 0 12px;}}
.c-footer{{display:flex;justify-content:space-between;align-items:center;}}
.c-foot-text{{font-size:12px;font-weight:700;color:#222;}}
.c-credit{{font-size:10px;color:#9a8a7a;}}
.c-sources{{margin-top:10px;padding-top:8px;border-top:1px dashed #d0c4b4;}}
.c-sources-label{{font-size:9px;font-weight:700;color:#9a8a7a;letter-spacing:.8px;margin-bottom:3px;}}
.c-sources a{{font-size:10px;color:#cc2b2b;text-decoration:underline;margin-right:10px;}}
.col-header{{
  font-size:11px;font-weight:700;color:#fff;
  background:#cc2b2b;letter-spacing:1.5px;
  padding:6px 14px;display:inline-block;margin-bottom:12px;
}}
</style></head><body>
<div class="col-header">{section_label}</div>
<div class="card">
  <div class="c-top">
    <div><div class="c-handle">@홈앤쇼핑_AI_DAILY_NEWS</div>
    <div class="c-category">{category}</div></div>
    <div class="c-date">{date_en}</div>
  </div>
  <div class="c-title">{title}</div>
  <div class="c-items">{items_html}</div>
  <hr class="c-divider">
  <div class="c-footer">
    <div class="c-foot-text">{footer}</div>
    <div class="c-credit">© 홈앤쇼핑 AI Daily · powered by Claude</div>
  </div>
  {sources_html}
</div>
</body></html>"""


def generate_card_html(card, date_en, section_label):
    items_html = ''
    for i, it in enumerate(card.get('items', [])):
        desc = (it.get('desc', '') or '').replace('<b>', '<b>').replace('</b>', '</b>')
        items_html += (
            f'<div class="c-item">'
            f'<span class="i-num">{i+1}</span>'
            f'<span class="i-kw">{it.get("keyword","")}</span>'
            f'<span class="i-desc">{desc}</span>'
            f'</div>'
        )

    sources_html = ''
    sources = card.get('sources', [])
    if sources:
        links = ''.join(
            f'<a href="{s["url"]}">{s["title"]}</a>'
            for s in sources
        )
        sources_html = f'<div class="c-sources"><div class="c-sources-label">출처 SOURCE</div>{links}</div>'

    title = (card.get('title', '') or '').replace('<br>', '<br>')

    return CARD_HTML_TEMPLATE.format(
        section_label=section_label,
        category=card.get('category', ''),
        date_en=date_en,
        title=title,
        items_html=items_html,
        footer=card.get('footer', ''),
        sources_html=sources_html,
    )


def capture_cards(data):
    """Playwright로 각 카드를 PNG 이미지로 캡처"""
    from playwright.sync_api import sync_playwright

    date_en = data.get('date_en', '')
    images = []

    all_cards = []
    for card in data.get('left', [])[:3]:
        all_cards.append((card, '홈앤쇼핑 자사 뉴스'))
    for card in data.get('right', [])[:3]:
        all_cards.append((card, '홈쇼핑 업계 동향'))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 920, 'height': 800})

        for i, (card, label) in enumerate(all_cards):
            html = generate_card_html(card, date_en, label)
            tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'_tmp_card_{i}.html')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(html)

            page.goto(f'file://{tmp_path}')
            page.wait_for_timeout(500)

            card_el = page.query_selector('.card')
            if card_el:
                img_bytes = page.screenshot(full_page=True, type='png')
            else:
                img_bytes = page.screenshot(full_page=True, type='png')

            images.append({
                'data': img_bytes,
                'label': label,
                'title': (card.get('title', '') or '').replace('<br>', ' '),
                'filename': f'card_{i+1}.png',
            })

            os.remove(tmp_path)

        browser.close()

    return images


def build_email_html(data, images):
    """이미지가 임베드된 HTML 이메일 생성"""
    today = data.get('date', datetime.now().strftime('%Y년 %m월 %d일'))

    html = f"""<html><body style="margin:0;padding:0;background:#f5f5f5;font-family:'Malgun Gothic',sans-serif;">
<div style="max-width:900px;margin:0 auto;padding:20px;">
  <div style="background:#cc2b2b;color:#fff;padding:20px 24px;border-radius:10px 10px 0 0;text-align:center;">
    <div style="font-size:10px;letter-spacing:2px;opacity:.7;">@홈앤쇼핑_AI_DAILY_NEWS</div>
    <h1 style="font-size:22px;margin:6px 0 4px;">홈앤쇼핑 AI Daily News</h1>
    <div style="font-size:12px;opacity:.8;">{today} · 네이버 뉴스 × Claude AI</div>
  </div>
  <div style="background:#fff;padding:20px 24px;border-radius:0 0 10px 10px;">
"""

    for i, img in enumerate(images):
        cid = f'card{i}'
        html += f"""
    <div style="margin-bottom:16px;">
      <img src="cid:{cid}" alt="{img['title']}" style="width:100%;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    </div>
"""

    html += """
    <div style="text-align:center;padding:16px 0 8px;color:#aaa;font-size:11px;">
      © 홈앤쇼핑 AI Daily News · powered by Claude<br>
      <a href="https://prettykbk81.github.io/hnsinfo/cardnews.html" style="color:#cc2b2b;">웹에서 보기</a>
    </div>
  </div>
</div>
</body></html>"""

    return html


def send_email(data, images):
    """이메일 발송"""
    email_user = _env('EMAIL_USERNAME')
    email_pass = _env('EMAIL_PASSWORD')
    email_to = _env('EMAIL_TO') or 'bk.kang@hnsmall.com'

    if not email_user or not email_pass:
        print("[!] EMAIL_USERNAME / EMAIL_PASSWORD 없음 - 이메일 발송 건너뜀")
        return

    today = data.get('date', datetime.now().strftime('%Y년 %m월 %d일'))

    msg = MIMEMultipart('related')
    msg['Subject'] = f'홈앤쇼핑 AI Daily News - {today}'
    msg['From'] = email_user
    msg['To'] = email_to

    html = build_email_html(data, images)
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    for i, img in enumerate(images):
        mime_img = MIMEImage(img['data'], 'png')
        mime_img.add_header('Content-ID', f'<card{i}>')
        mime_img.add_header('Content-Disposition', 'inline', filename=img['filename'])
        msg.attach(mime_img)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(email_user, email_pass)
        server.send_message(msg)

    print(f"이메일 발송 완료 -> {email_to}")


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base, 'daily_news.json')

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    print(f"카드 이미지 생성 중 ({data.get('date', '')})")
    images = capture_cards(data)
    print(f"카드 {len(images)}장 캡처 완료")

    send_email(data, images)
