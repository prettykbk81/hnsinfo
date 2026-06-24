"""
네이버 쇼핑인사이트 데이터 생성 → shopping_insight.json
"""

import json
import os
import requests
import urllib3
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
KST = timezone(timedelta(hours=9))


def _env(key):
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


def generate_shopping_insight(base_dir=None):
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    naver_id = _env('NAVER_CLIENT_ID')
    naver_secret = _env('NAVER_CLIENT_SECRET')
    if not naver_id or not naver_secret:
        print("[!] NAVER API 키 없음 - 쇼핑인사이트 건너뜀")
        return

    headers = {
        "X-Naver-Client-Id": naver_id,
        "X-Naver-Client-Secret": naver_secret,
        "Content-Type": "application/json",
    }
    shop_headers = {
        "X-Naver-Client-Id": naver_id,
        "X-Naver-Client-Secret": naver_secret,
    }

    end = datetime.now(KST)
    start = end - timedelta(days=90)

    # 1. 카테고리별 클릭 추이
    cat_groups = [
        [
            {"name": "패션의류", "param": ["50000000"]},
            {"name": "화장품/미용", "param": ["50000002"]},
            {"name": "생활/건강", "param": ["50000008"]},
        ],
        [
            {"name": "식품", "param": ["50000006"]},
            {"name": "디지털/가전", "param": ["50000003"]},
            {"name": "가구/인테리어", "param": ["50000004"]},
        ],
    ]

    all_categories = []
    for cats in cat_groups:
        try:
            r = requests.post(
                "https://openapi.naver.com/v1/datalab/shopping/categories",
                headers=headers,
                json={
                    "startDate": start.strftime("%Y-%m-%d"),
                    "endDate": end.strftime("%Y-%m-%d"),
                    "timeUnit": "week",
                    "category": cats,
                },
                timeout=10,
            )
            if r.ok:
                for result in r.json().get("results", []):
                    all_categories.append({
                        "name": result["title"],
                        "labels": [d["period"] for d in result.get("data", [])],
                        "values": [round(d["ratio"]) for d in result.get("data", [])],
                    })
                print(f"  카테고리 {len(all_categories)}개 수집")
        except Exception as e:
            print(f"  카테고리 오류: {e}")

    # 2. 분야별 인기 키워드
    keyword_lists = {
        "패션의류": ["원피스", "여름원피스", "블라우스", "티셔츠", "반팔티"],
        "화장품/미용": ["선크림", "쿠션", "토너", "마스크팩", "립스틱"],
        "식품": ["홍삼", "견과류", "닭가슴살", "과일", "냉면"],
        "생활/건강": ["선풍기", "에어컨", "청소기", "비타민", "화장지"],
    }
    result_keywords = {}
    for cat_name, keywords in keyword_lists.items():
        items = []
        for kw in keywords:
            try:
                r2 = requests.get(
                    "https://openapi.naver.com/v1/search/shop.json",
                    headers=shop_headers,
                    params={"query": kw, "display": 1, "sort": "sim"},
                    timeout=5,
                )
                if r2.ok:
                    items.append({"keyword": kw, "total": r2.json().get("total", 0)})
            except Exception:
                items.append({"keyword": kw, "total": 0})
        items.sort(key=lambda x: -x["total"])
        result_keywords[cat_name] = items
        print(f"  {cat_name}: {[k['keyword'] for k in items[:3]]}")

    data = {
        "categories": all_categories,
        "popular_keywords": result_keywords,
        "date": end.strftime("%Y.%m.%d"),
    }

    out_path = os.path.join(base_dir, 'shopping_insight.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장 완료 -> {out_path}")


if __name__ == '__main__':
    generate_shopping_insight()
