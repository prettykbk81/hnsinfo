"""
생성된 카드뉴스를 Notion 페이지에 업데이트
daily_news.json을 읽어 Notion API로 하위 페이지 생성
"""

import json
import os
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


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


def build_blocks(data: dict) -> list:
    """카드뉴스 데이터를 Notion 블록으로 변환"""
    blocks = []
    today = data.get('date', datetime.now().strftime('%Y년 %m월 %d일'))

    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "📰"},
            "rich_text": [{"type": "text", "text": {"content": f"{today} · 네이버 뉴스 × Claude AI"}}],
            "color": "red_background",
        }
    })

    sections = [
        ("left", "홈앤쇼핑 자사 뉴스"),
        ("right", "홈쇼핑 업계 동향"),
    ]

    for key, label in sections:
        cards = data.get(key, [])
        if not cards:
            continue

        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": label}}],
                "color": "red",
            }
        })

        for card in cards:
            title = (card.get('title', '') or '').replace('<br>', ' ')
            category = card.get('category', '')
            footer = card.get('footer', '')

            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"[{category}] "}, "annotations": {"color": "red"}},
                        {"type": "text", "text": {"content": title}},
                    ]
                }
            })

            for item in card.get('items', []):
                kw = item.get('keyword', '')
                desc = (item.get('desc', '') or '').replace('<b>', '').replace('</b>', '').replace('<em>', '').replace('</em>', '')
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{kw}: "}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": desc}},
                        ]
                    }
                })

            if footer:
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": footer}}],
                        "color": "gray",
                    }
                })

            sources = card.get('sources', [])
            if sources:
                for src in sources:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "출처: "},"annotations": {"color": "gray", "italic": True}},
                                {"type": "text", "text": {"content": src.get('title', ''), "link": {"url": src.get('url', '')}}, "annotations": {"color": "gray"}},
                            ]
                        }
                    })

        blocks.append({"object": "block", "type": "divider", "divider": {}})

    return blocks


def create_notion_page(token: str, parent_page_id: str, data: dict):
    """Notion에 하위 페이지 생성"""
    today = data.get('date', datetime.now().strftime('%Y년 %m월 %d일'))
    title = f"AI Daily News - {today}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    blocks = build_blocks(data)

    # Notion API는 한 번에 최대 100개 블록
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": [{"text": {"content": title}}]
        },
        "children": blocks[:100],
    }

    resp = requests.post(
        f"{NOTION_API}/pages",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if resp.ok:
        page_url = resp.json().get('url', '')
        print(f"Notion 페이지 생성 완료: {page_url}")
    else:
        err = resp.json().get('message', resp.status_code)
        print(f"Notion 오류: {err}")
        resp.raise_for_status()


if __name__ == '__main__':
    token = _env('NOTION_TOKEN')
    page_id = _env('NOTION_PAGE_ID') or '37c3ffb91ddd8038bf96fce111328dbc'

    if not token:
        print("[!] NOTION_TOKEN 없음 - Notion 업데이트 건너뜀")
        exit(0)

    base = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base, 'daily_news.json')

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    print(f"Notion 업데이트 시작 ({data.get('date', '날짜 없음')})")
    create_notion_page(token, page_id, data)
