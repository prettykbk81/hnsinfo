"""
AI 요약 프록시 서버 — app.py가 subprocess로 자동 실행
secrets.toml의 API 키를 읽어 Claude API + 상품 검색 + 리뷰 수집을 서버 사이드 호출
"""

import json
import os
import re
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import anthropic
import httpx
import numpy as np
import requests as req_lib

PORT = 8502


def _toml(key, default=""):
    try:
        import tomllib
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, ".streamlit", "secrets.toml"), "rb") as f:
            return tomllib.load(f).get(key, default) or default
    except (ImportError, FileNotFoundError, Exception):
        pass
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, ".streamlit", "secrets.toml"), encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith(key):
                    _, _, val = s.partition("=")
                    return val.strip().strip('"').strip("'") or default
    except FileNotFoundError:
        pass
    return os.environ.get(key, default)


API_KEY = _toml("ANTHROPIC_API_KEY")
MODEL = _toml("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
NAVER_ID = _toml("NAVER_CLIENT_ID")
NAVER_SECRET = _toml("NAVER_CLIENT_SECRET")

_HEADERS_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ───────────────────────────────────────────────────────────
# Lens(사내 생방송 진행 대시보드) 연동 — 이메일 인증코드 로그인 후
# Bearer 토큰으로 API 호출. 개발 서버라 인증코드가 응답에 그대로 내려온다.
# ───────────────────────────────────────────────────────────
LENS_BASE = "http://172.16.209.98:5176"
LENS_EMAIL = "fullmoon@hnsmall.com"
_lens_token = None
_lens_lock = threading.Lock()


def _lens_login() -> str:
    global _lens_token
    r = req_lib.post(
        f"{LENS_BASE}/api/auth/request-code",
        json={"email": LENS_EMAIL, "purpose": "login"}, timeout=10,
    )
    r.raise_for_status()
    dev_code = r.json().get("devCode")
    r2 = req_lib.post(
        f"{LENS_BASE}/api/auth/verify",
        json={"email": LENS_EMAIL, "code": dev_code, "purpose": "login"}, timeout=10,
    )
    r2.raise_for_status()
    _lens_token = r2.json().get("token")
    return _lens_token


def _lens_get(path: str) -> dict:
    """Lens API GET — 토큰이 없거나 만료(401)됐으면 재로그인 후 1회 재시도"""
    global _lens_token
    with _lens_lock:
        if not _lens_token:
            _lens_login()
        headers = {"Authorization": f"Bearer {_lens_token}"}
        r = req_lib.get(f"{LENS_BASE}{path}", headers=headers, timeout=10)
        if r.status_code == 401:
            _lens_login()
            headers = {"Authorization": f"Bearer {_lens_token}"}
            r = req_lib.get(f"{LENS_BASE}{path}", headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()


def _search_hnsmall(keyword: str) -> list[dict]:
    """홈앤쇼핑 사이트에서 상품 검색"""
    try:
        r = req_lib.get(
            "https://www.hnsmall.com/search/search.do",
            params={"query_top": keyword},
            verify=False, timeout=10, headers=_HEADERS_UA,
        )
        r.raise_for_status()
        t = r.text

        products = []
        for m in re.finditer(
            r'goods\.do\?goods_code=(\d+)[^"\']*["\'][^>]*class="img">\s*'
            r'<img\s+src="([^"]+)"',
            t, re.S,
        ):
            code, img = m.group(1), m.group(2)
            if code in [p["code"] for p in products]:
                continue
            name_m = re.search(
                rf'goods\.do\?goods_code={code}[^"\']*["\'][^>]*class="tit">([^<]+)<',
                t,
            )
            price_m = re.search(
                rf'goods_code={code}[\s\S]{{0,800}}?<dd><strong>([\d,]+)</strong>',
                t,
            )
            products.append({
                "code": code,
                "name": name_m.group(1).strip() if name_m else keyword,
                "image": img if img.startswith("http") else "https:" + img,
                "price": price_m.group(1) if price_m else "",
                "url": f"https://www.hnsmall.com/display/goods.do?goods_code={code}",
            })
            if len(products) >= 8:
                break

        return products
    except Exception:
        return []


def _fetch_review_score(goods_code: str) -> dict:
    """홈앤쇼핑 상품 만족도 점수 가져오기"""
    try:
        r = req_lib.get(
            f"https://www.hnsmall.com/display/Igoodscomment.do?goods_code={goods_code}",
            verify=False, timeout=8, headers=_HEADERS_UA,
        )
        score_m = re.search(r'class="fontType1">(\d+)</em>', r.text)
        count_m = re.search(r'상품평\s*(\d[\d,]*)\s*건', r.text)
        level_m = re.search(r'class="fontType2\s*">([^<]+)<', r.text)

        all_reviews = []
        for page in range(1, 6):
            if page == 1:
                page_text = r.text
            else:
                rp = req_lib.post(
                    "https://www.hnsmall.com/display/Igoodscomment.do",
                    data={"goods_code": goods_code, "currentPage": str(page),
                          "rowsPerPage": "10", "order_type": "1", "goto": "Y"},
                    verify=False, timeout=8, headers=_HEADERS_UA,
                )
                page_text = rp.text

            items = re.findall(
                r'<div class="reviewInfo">([\s\S]*?)(?=<div class="reviewInfo">|$)',
                page_text,
            )
            if not items:
                items_alt = page_text.split('<div class="reviewInfo">')
                items = items_alt[1:] if len(items_alt) > 1 else []

            for item in items:
                flag_m = re.search(r'class="flag\s+\w+">([^<]+)<', item)
                if not flag_m:
                    continue
                user_m = re.search(r'class="user">([^<]+)<', item)
                date_m = re.search(r'class="date">\s*([^\n<]+)', item)

                review_text = ""
                rate_m = re.search(r'class="rateBox">([\s\S]*?)</div>', item)
                if rate_m:
                    txt = re.sub(r'<[^>]+>', ' ', rate_m.group(1))
                    txt = re.sub(r'닫기', '', txt)
                    txt = re.sub(r'\s+', ' ', txt).strip()
                    if len(txt) > 3:
                        review_text = txt[:300]
                txt_m = re.search(r'class="txt">([^<]+(?:<BR>[^<]*)*)', item)
                if txt_m and not review_text:
                    review_text = re.sub(r'<BR>', ' ', txt_m.group(1)).strip()[:300]

                images = re.findall(
                    r'src="((?:https?:)?//image\.hnsmall\.com/images/comment/[^"]+)"',
                    item,
                )

                all_reviews.append({
                    "rating": flag_m.group(1).strip(),
                    "user": user_m.group(1).strip() if user_m else "",
                    "date": date_m.group(1).strip() if date_m else "",
                    "text": review_text,
                    "images": images[:3],
                })
            if not items:
                break

        dist = {}
        for rv in all_reviews:
            rt = rv["rating"]
            dist[rt] = dist.get(rt, 0) + 1

        return {
            "score": score_m.group(1) if score_m else "",
            "count": count_m.group(1) if count_m else "0",
            "level": level_m.group(1).strip() if level_m else "",
            "distribution": dist,
            "reviews": all_reviews[:50],
            "review_count": len(all_reviews),
        }
    except Exception:
        return {"score": "", "count": "0", "level": ""}


def _search_naver_news(keyword: str, display: int = 5) -> list:
    """네이버 뉴스 검색"""
    if not NAVER_ID or not NAVER_SECRET:
        return []
    try:
        r = req_lib.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
            params={"query": keyword, "display": display, "sort": "date"},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        results = []
        for item in r.json().get("items", []):
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
            results.append({"title": title, "desc": desc, "link": item.get("link", ""), "date": item.get("pubDate", "")})
        return results
    except Exception:
        return []


def _get_shopping_insight() -> dict:
    """네이버 쇼핑인사이트 - 카테고리별 트렌드 + 인기 키워드"""
    if not NAVER_ID or not NAVER_SECRET:
        return {}
    try:
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        end = datetime.now(KST)
        start = end - timedelta(days=90)
        start4 = end - timedelta(days=4)

        headers = {
            "X-Naver-Client-Id": NAVER_ID,
            "X-Naver-Client-Secret": NAVER_SECRET,
            "Content-Type": "application/json",
        }

        # 1. 카테고리별 클릭 추이 (3개까지)
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
            r = req_lib.post(
                "https://openapi.naver.com/v1/datalab/shopping/categories",
                headers=headers,
                json={
                    "startDate": start.strftime("%Y-%m-%d"),
                    "endDate": end.strftime("%Y-%m-%d"),
                    "timeUnit": "week",
                    "category": cats,
                },
                verify=False, timeout=10,
            )
            if r.ok:
                for result in r.json().get("results", []):
                    all_categories.append({
                        "name": result["title"],
                        "labels": [d["period"] for d in result.get("data", [])],
                        "values": [round(d["ratio"]) for d in result.get("data", [])],
                    })

        # 2. 분야별 인기 키워드 (쇼핑 검색으로 대체)
        popular_keywords = {
            "패션의류": ["원피스", "여름원피스", "블라우스", "티셔츠", "반팔티"],
            "화장품/미용": ["선크림", "쿠션", "토너", "마스크팩", "립스틱"],
            "식품": ["홍삼", "견과류", "닭가슴살", "과일", "냉면"],
            "생활/건강": ["선풍기", "에어컨", "청소기", "비타민", "화장지"],
        }
        result_keywords = {}
        for cat_name, keywords in popular_keywords.items():
            items = []
            for kw in keywords:
                try:
                    r2 = req_lib.get(
                        "https://openapi.naver.com/v1/search/shop.json",
                        headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
                        params={"query": kw, "display": 1, "sort": "sim"},
                        verify=False, timeout=5,
                    )
                    if r2.ok:
                        items.append({"keyword": kw, "total": r2.json().get("total", 0)})
                except Exception:
                    items.append({"keyword": kw, "total": 0})
            items.sort(key=lambda x: -x["total"])
            result_keywords[cat_name] = items

        return {
            "categories": all_categories,
            "popular_keywords": result_keywords,
            "date": end.strftime("%Y.%m.%d"),
        }
    except Exception:
        return {}


def _search_naver_shop(keyword: str, display: int = 100) -> dict:
    """네이버 쇼핑 검색 API"""
    if not NAVER_ID or not NAVER_SECRET:
        return {}
    try:
        r = req_lib.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
            params={"query": keyword, "display": display, "sort": "sim"},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])

        # 추가 키워드로 다양한 카테고리 수집
        extra_queries = ["건강식품", "여름가전", "화장품", "패션", "생활용품"]
        all_items = list(items)
        for eq in extra_queries:
            try:
                r3 = req_lib.get(
                    "https://openapi.naver.com/v1/search/shop.json",
                    headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
                    params={"query": eq, "display": 20, "sort": "sim"},
                    verify=False, timeout=5,
                )
                if r3.ok:
                    all_items.extend(r3.json().get("items", []))
            except Exception:
                pass

        prices = [int(it.get("lprice", 0)) for it in items if it.get("lprice")]
        malls = {}
        cats = {}
        brands = {}
        for it in all_items:
            title = re.sub(r"<[^>]+>", "", it.get("title", ""))
            mall = it.get("mallName", "기타")
            cat = it.get("category2") or it.get("category1") or "기타"
            brand = it.get("brand") or "기타"
            malls[mall] = malls.get(mall, 0) + 1
            cats[cat] = cats.get(cat, 0) + 1
            if brand and brand != "기타":
                brands[brand] = brands.get(brand, 0) + 1

        price_buckets = {"~1만원": 0, "1~3만원": 0, "3~5만원": 0, "5~10만원": 0,
                         "10~30만원": 0, "30~50만원": 0, "50만원~": 0}
        for p in prices:
            if p < 10000: price_buckets["~1만원"] += 1
            elif p < 30000: price_buckets["1~3만원"] += 1
            elif p < 50000: price_buckets["3~5만원"] += 1
            elif p < 100000: price_buckets["5~10만원"] += 1
            elif p < 300000: price_buckets["10~30만원"] += 1
            elif p < 500000: price_buckets["30~50만원"] += 1
            else: price_buckets["50만원~"] += 1

        top_malls = sorted(malls.items(), key=lambda x: -x[1])[:10]
        top_brands = sorted(brands.items(), key=lambda x: -x[1])[:10]

        return {
            "total": data.get("total", 0),
            "avg_price": int(sum(prices) / len(prices)) if prices else 0,
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "brand_count": len(brands),
            "mall_count": len(malls),
            "price_buckets": price_buckets,
            "top_malls": [{"name": k, "count": v} for k, v in top_malls],
            "categories": dict(sorted(cats.items(), key=lambda x: -x[1])),
            "top_brands": [{"name": k, "count": v} for k, v in top_brands],
        }
    except Exception:
        return {}


def _get_datalab_trend(keyword: str) -> dict:
    """네이버 DataLab 검색 트렌드 — 시즌 인기 상품 5개 비교"""
    if not NAVER_ID or not NAVER_SECRET:
        return {}
    try:
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        end = datetime.now(KST)
        start = end - timedelta(days=90)
        month = end.month

        season_keywords = {
            1: ["패딩", "홍삼", "다이어트", "가습기", "설선물"],
            2: ["초콜릿", "봄신상", "졸업선물", "면역력", "트렌치코트"],
            3: ["공기청정기", "봄원피스", "선크림", "미세먼지", "꽃배달"],
            4: ["캠핑", "자외선차단", "봄나들이", "등산화", "로봇청소기"],
            5: ["어버이날선물", "가족여행", "원피스", "안마의자", "어린이날"],
            6: ["에어컨", "선풍기", "선크림", "삼계탕", "제습기"],
            7: ["수영복", "캠핑", "삼계탕", "선풍기", "여름휴가"],
            8: ["가을신상", "추석선물", "학용품", "노트북", "보양식"],
            9: ["추석선물세트", "한우", "가을자켓", "등산", "홍삼"],
            10: ["김장재료", "난방기", "패딩", "할로윈", "캠핑"],
            11: ["블랙프라이데이", "김장", "패딩", "코트", "가습기"],
            12: ["크리스마스선물", "패딩", "와인", "겨울부츠", "연말선물"],
        }
        kws = season_keywords.get(month, ["홈쇼핑", "가전", "패션", "식품", "뷰티"])

        headers = {
            "X-Naver-Client-Id": NAVER_ID,
            "X-Naver-Client-Secret": NAVER_SECRET,
            "Content-Type": "application/json",
        }

        r = req_lib.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers=headers,
            json={
                "startDate": start.strftime("%Y-%m-%d"),
                "endDate": end.strftime("%Y-%m-%d"),
                "timeUnit": "month",
                "keywordGroups": [{"groupName": k, "keywords": [k]} for k in kws],
            },
            verify=False, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])

        datasets = []
        labels = []
        for result in results:
            points = result.get("data", [])
            if not labels and points:
                labels = [p["period"][:7] for p in points]
            datasets.append({
                "keyword": result["title"],
                "values": [round(p["ratio"]) for p in points],
            })

        return {
            "type": "multi",
            "keywords": kws,
            "labels": labels,
            "datasets": datasets,
        }
    except Exception:
        return {}


def _fetch_blog_body(url: str) -> str:
    """블로그 본문 텍스트 추출 (최대 800자)"""
    try:
        r = req_lib.get(url, verify=False, timeout=8, headers=_HEADERS_UA)
        t = r.text
        iframe_m = re.search(r'src="(https?://blog\.naver\.com/PostView[^"]+)"', t)
        if iframe_m:
            r2 = req_lib.get(iframe_m.group(1), verify=False, timeout=8, headers=_HEADERS_UA)
            t = r2.text
        for cls in ['se-main-container', 'post-view', 'post_ct', 'se_textView']:
            idx = t.find(cls)
            if idx > 0:
                chunk = t[idx:idx+8000]
                text = re.sub(r'<[^>]+>', ' ', chunk)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 50:
                    return text[:800]
        text = re.sub(r'<script[\s\S]*?</script>', '', t)
        text = re.sub(r'<style[\s\S]*?</style>', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:800] if len(text) > 50 else ""
    except Exception:
        return ""


def _search_naver_blog(keyword: str, display: int = 10) -> list[dict]:
    """네이버 블로그에서 상품 후기 검색 + 본문 추출"""
    if not NAVER_ID or not NAVER_SECRET:
        return []
    try:
        r = req_lib.get(
            "https://openapi.naver.com/v1/search/blog.json",
            headers={
                "X-Naver-Client-Id": NAVER_ID,
                "X-Naver-Client-Secret": NAVER_SECRET,
            },
            params={"query": keyword, "display": display, "sort": "sim"},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        results = []
        for item in r.json().get("items", []):
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
            link = item.get("link", "")
            body = _fetch_blog_body(link)
            results.append({
                "title": title,
                "desc": body if body else desc,
                "link": link,
                "date": item.get("postdate", ""),
                "blogger": item.get("bloggername", ""),
            })
        return results
    except Exception:
        return []


def _clean_title_for_search(title: str) -> str:
    """상품명의 홍보문구 괄호((할인 안내) 등)는 제거하고 브랜드 대괄호([엘렌느] 등)는 내용만 남겨 검색어로 정제"""
    cleaned = re.sub(r'\([^)]*\)', '', title)
    cleaned = re.sub(r'[\[\]]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or title


def _lookup_category_naver(keyword: str) -> str:
    """hnsmall 상품 페이지엔 카테고리가 정적으로 노출되지 않아, 네이버 쇼핑 검색 1건으로 카테고리를 추정하는 보조 수단"""
    if not NAVER_ID or not NAVER_SECRET or not keyword:
        return ""
    keyword = _clean_title_for_search(keyword)
    try:
        r = req_lib.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
            params={"query": keyword, "display": 1, "sort": "sim"},
            verify=False, timeout=8,
        )
        if r.ok:
            items = r.json().get("items", [])
            if items:
                return items[0].get("category2") or items[0].get("category1") or ""
    except Exception:
        pass
    return ""


def _get_product_price_compare(keyword: str, display: int = 30) -> dict:
    """네이버 쇼핑에서 상품명으로 검색해 가격비교 통계(최저가순 최대 30건 기준)"""
    if not NAVER_ID or not NAVER_SECRET or not keyword:
        return {}
    try:
        r = req_lib.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
            params={"query": keyword, "display": display, "sort": "asc"},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        prices = [int(it.get("lprice", 0)) for it in items if it.get("lprice")]
        malls = {}
        for it in items:
            mall = it.get("mallName", "기타")
            malls[mall] = malls.get(mall, 0) + 1
        top_malls = sorted(malls.items(), key=lambda x: -x[1])[:5]

        return {
            "total": data.get("total", 0),
            "avg_price": int(sum(prices) / len(prices)) if prices else 0,
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "mall_count": len(malls),
            "top_malls": [{"name": k, "count": v} for k, v in top_malls],
            "items": [
                {
                    "title": re.sub(r"<[^>]+>", "", it.get("title", "")),
                    "price": it.get("lprice", ""),
                    "mall": it.get("mallName", ""),
                    "link": it.get("link", ""),
                }
                for it in items[:5]
            ],
        }
    except Exception:
        return {}


def _get_datalab_trend_single(keyword: str) -> dict:
    """단일 상품 키워드의 최근 90일 네이버 검색 트렌드(주간)"""
    if not NAVER_ID or not NAVER_SECRET or not keyword:
        return {}
    try:
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        end = datetime.now(KST)
        start = end - timedelta(days=90)

        r = req_lib.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers={
                "X-Naver-Client-Id": NAVER_ID,
                "X-Naver-Client-Secret": NAVER_SECRET,
                "Content-Type": "application/json",
            },
            json={
                "startDate": start.strftime("%Y-%m-%d"),
                "endDate": end.strftime("%Y-%m-%d"),
                "timeUnit": "week",
                "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
            },
            verify=False, timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return {}
        points = results[0].get("data", [])
        return {
            "keyword": keyword,
            "labels": [p["period"] for p in points],
            "values": [round(p["ratio"]) for p in points],
        }
    except Exception:
        return {}


def _get_product_web_info(raw_name: str) -> dict:
    """방송 상품명 기준으로 네이버 가격비교 + 검색 트렌드를 한번에 조회"""
    keyword = _clean_title_for_search(raw_name)
    return {
        "keyword": keyword,
        "shop": _get_product_price_compare(keyword),
        "trend": _get_datalab_trend_single(keyword),
    }


def _fetch_product_detail(goods_code: str) -> dict:
    """상품 상세 정보(가격, 카테고리, 기술서 특징) 가져오기"""
    result = {"price": "", "category": "", "feat1": "", "feat2": ""}
    try:
        r = req_lib.get(
            f"https://www.hnsmall.com/display/goods.do?goods_code={goods_code}",
            verify=False, timeout=10, headers=_HEADERS_UA,
        )
        t = r.text
        price_m = re.search(r'<strong>(\d[\d,]+)</strong>\s*<span\s+class="won">', t)
        if price_m:
            result["price"] = price_m.group(1) + "원"
        name_m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', t)
        if name_m:
            result["name"] = name_m.group(1).strip()
            result["category"] = _lookup_category_naver(result["name"])
    except Exception:
        pass

    try:
        desc_url = f"https://image.hnsmall.com/images/itemdesc/pc/goods/describePage/{goods_code}"
        r2 = req_lib.get(desc_url, verify=False, timeout=8, headers=_HEADERS_UA)
        text = re.sub(r'<script[\s\S]*?</script>', '', r2.text)
        text = re.sub(r'<style[\s\S]*?</style>', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 20:
            result["description"] = text[:600]
    except Exception:
        pass

    return result


def _fetch_schedule(date_str: str = "") -> list[dict]:
    """홈앤쇼핑 TV 편성표 가져오기 (현재 생방송중 항목도 live=True로 포함)"""
    import datetime
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y%m%d")
    try:
        r = req_lib.get(
            "https://www.hnsmall.com/display/tvschedule-list",
            params={"broadDay": date_str},
            verify=False, timeout=10, headers=_HEADERS_UA,
        )
        r.raise_for_status()
        t = r.text
        items = []
        prev_end = ""
        for m in re.finditer(
            r'<li\s+class="item(?:\s+active)?">([\s\S]*?)</li>', t
        ):
            block = m.group(1)
            time_m = re.search(r'<b>(\d{1,2}:\d{2})</b>\s*~\s*(\d{1,2}:\d{2})', block)
            live_m = re.search(r'bdEtimeSecond="[\d-]+\s(\d{1,2}:\d{2}):\d{2}"', block)
            if not time_m and not live_m:
                continue

            name_m = re.search(r'class="time">\s*<span>[\s\S]*?</span>([^<]*)</p>', block)
            code_m = re.search(r"goGoods\('(\d+)'", block)
            img_m = re.search(r'<img\s+src="(//image[^"]+)"', block)
            price_m = re.search(r'<strong>([\d,]+)</strong>', block)

            if time_m:
                time_start, time_end, live = time_m.group(1), time_m.group(2), False
            else:
                time_start, time_end, live = prev_end, live_m.group(1), True

            items.append({
                "time_start": time_start,
                "time_end": time_end,
                "live": live,
                "name": name_m.group(1).strip() if name_m else "",
                "code": code_m.group(1) if code_m else "",
                "image": ("https:" + img_m.group(1)) if img_m else "",
                "price": price_m.group(1) if price_m else "",
            })
            prev_end = time_end
        return items
    except Exception:
        return []


def _get_live_broadcast_info() -> dict:
    """현재 생방송중인 상품의 방송정보(시간/카테고리 등) + 상품상세(가격/설명) 통합"""
    items = _fetch_schedule("")
    live_item = next((it for it in items if it.get("live")), None)
    if not live_item or not live_item.get("code"):
        return {"error": "현재 방송 중인 상품 정보를 편성표에서 찾지 못했습니다."}

    detail = _fetch_product_detail(live_item["code"])
    price = detail.get("price") or (f"{live_item['price']}원" if live_item.get("price") else "")

    return {
        "code": live_item["code"],
        "name": detail.get("name") or live_item.get("name") or "",
        "item": live_item.get("name", ""),
        "price": price,
        "category": detail.get("category", ""),
        "image": live_item.get("image", ""),
        "time_start": live_item.get("time_start", ""),
        "time_end": live_item.get("time_end", ""),
        "stream_url": "https://livevod.hnsmall.com:2935/live/mp4:a.stream/playlist.m3u8",
    }


def _fetch_gsshop_live() -> dict:
    """GS샵 메인페이지에 서버사이드로 렌더링된 현재 생방송(main-onair) 정보"""
    try:
        r = req_lib.get("https://www.gsshop.com/", verify=False, timeout=10, headers=_HEADERS_UA)
        r.raise_for_status()
        t = r.text
        m = re.search(r'<article id="main-onair">([\s\S]*?)</article>', t)
        if not m:
            return {"error": "GS샵 방송 정보를 찾지 못했습니다."}
        block = m.group(1)

        name_m = re.search(
            r'tvProductMain\.gs[^"]*">\s*(?:<span[^>]*>\[TV상품\]</span>\s*)?([^<]+)</a>', block,
        )
        price_m = re.search(r'<strong>([\d,]+)</strong>\s*원', block)
        img_m = re.search(r'<img class="view1" src="([^"]+)"', block)

        return {
            "name": name_m.group(1).strip() if name_m else "",
            "item": "",
            "price": (price_m.group(1) + "원") if price_m else "",
            "category": "",
            "image": img_m.group(1) if img_m else "",
            "time_start": "",
            "time_end": "",
            "stream_url": "https://gstv-gsshop.gsshop.com/gsshop_hd/_definst_/gsshop_hd.stream/playlist.m3u8",
        }
    except Exception as e:
        return {"error": str(e)}


# 홈쇼핑/T커머스 채널 목록 — 각 사별 실시간 편성 스크레이퍼는 순차적으로 추가 예정.
# "ready"인 채널만 실제 데이터를 가져오고, 나머지는 준비중으로 표시한다.
_LIVE_CHANNELS = [
    {"company": "홈앤쇼핑", "status": "ready"},
    {"company": "GS샵", "status": "ready"},
    {"company": "CJ온스타일", "status": "pending"},
    {"company": "롯데홈쇼핑", "status": "pending"},
    {"company": "현대홈쇼핑", "status": "pending"},
    {"company": "NS홈쇼핑", "status": "pending"},
    {"company": "공영쇼핑", "status": "pending"},
    {"company": "신세계라이브쇼핑", "status": "pending"},
]

_LIVE_FETCHERS = {
    "홈앤쇼핑": _get_live_broadcast_info,
    "GS샵": _fetch_gsshop_live,
}


def _get_all_live_broadcasts(target_name: str = "") -> list[dict]:
    """등록된 홈쇼핑/T커머스 채널별 현재 생방송 정보를 모아서 반환.
    target_name이 주어지면(현재 분석 중인 방송 상품명) 핵심 단어가 과반 이상 겹치는
    동일 상품일 때만 포함하고, 관련 없는 상품(예: 다른 채널이 김치를 팔고 있는 경우)은 뺀다."""
    target_tokens = set(_keyword_tokens(target_name)) if target_name else set()
    need = max(1, (len(target_tokens) + 1) // 2) if target_tokens else 0

    results = []
    for ch in _LIVE_CHANNELS:
        fetcher = _LIVE_FETCHERS.get(ch["company"])
        if ch["status"] != "ready" or fetcher is None:
            results.append({"company": ch["company"], "status": "pending"})
            continue

        info = fetcher()
        if info.get("error"):
            results.append({"company": ch["company"], "status": "error", "error": info["error"]})
            continue

        if target_tokens:
            item_tokens = set(_keyword_tokens(info.get("name", "")))
            if len(target_tokens & item_tokens) < need:
                continue

        results.append({"company": ch["company"], "status": "ok", **info})

    return results


def _keyword_tokens(text: str) -> list[str]:
    return [w for w in _clean_title_for_search(text).split(" ") if len(w) >= 2]


# 경쟁사 방송 이력은 각 사 사이트를 직접 스크레이핑하지 않고, 여러 홈쇼핑사를 한번에 모아
# 보여주는 홈쇼핑모아(hsmoa.com) 검색 결과를 이용한다 — 채널 코드는 hsmoa 기준.
_HSMOA_COMPETITOR_CHANNELS = {
    "cjmall": "CJ온스타일",
    "lotteimall": "롯데홈쇼핑",
    "hmall": "현대홈쇼핑",
    "nsmall": "NS홈쇼핑",
}


def _fetch_hsmoa_aggregated(keyword: str) -> dict:
    """홈쇼핑모아 검색 결과 페이지에 내장된 __NEXT_DATA__에서 채널별 상품/방송 데이터를 꺼내온다."""
    try:
        r = req_lib.get(
            "https://hsmoa.com/search", params={"query": keyword},
            verify=False, timeout=10, headers=_HEADERS_UA,
        )
        r.raise_for_status()
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.S)
        if not m:
            return {}
        data = json.loads(m.group(1))
        return data.get("props", {}).get("pageProps", {}).get("aggregatedData", {}) or {}
    except Exception:
        return {}


def _check_competitor_history(product_name: str, months: int = 1) -> dict:
    """홈쇼핑모아(hsmoa.com) 검색 결과에서 CJ온스타일/롯데홈쇼핑/현대홈쇼핑/NS홈쇼핑의
    최근 N개월 내 동일(유사) 상품 방송 이력을 찾는다. 상품 구성(수량 등)은 달라도
    핵심 단어가 과반 이상 겹치면 같은 방송으로 간주하고, 실제 방송 일시가 확인되는 것만 결과에 포함한다."""
    from datetime import datetime, timedelta, timezone

    target_tokens = set(_keyword_tokens(product_name))
    if not target_tokens:
        return {"results": []}
    need = max(1, (len(target_tokens) + 1) // 2)  # 과반 이상 겹치면 같은 상품으로 간주

    keyword = _clean_title_for_search(product_name)
    aggregated = _fetch_hsmoa_aggregated(keyword)

    KST = timezone(timedelta(hours=9))
    cutoff = datetime.now(KST) - timedelta(days=months * 30)

    best_by_company = {}
    for bucket in ("past", "future", "best", "ep0", "ep1", "ep2", "ep3"):
        for it in aggregated.get(bucket) or []:
            channel = it.get("tv_channel") or it.get("site")
            company = _HSMOA_COMPETITOR_CHANNELS.get(channel)
            if not company:
                continue
            start = it.get("start_datetime")
            if not start:
                continue
            item_tokens = set(_keyword_tokens(it.get("name", "")))
            if len(target_tokens & item_tokens) < need:
                continue
            try:
                start_dt = datetime.fromisoformat(start)
            except ValueError:
                continue
            if start_dt < cutoff:
                continue
            prev = best_by_company.get(company)
            if prev and prev["_start_dt"] >= start_dt:
                continue
            end = it.get("end_datetime") or ""
            best_by_company[company] = {
                "company": company, "found": True,
                "date": start_dt.strftime("%Y-%m-%d"),
                "time_start": start_dt.strftime("%H:%M"),
                "time_end": (datetime.fromisoformat(end).strftime("%H:%M") if end else ""),
                "price": it.get("sale_price") or it.get("price") or 0,
                "name": it.get("name", ""),
                "_start_dt": start_dt,
            }

    results = []
    for company in _HSMOA_COMPETITOR_CHANNELS.values():
        match = best_by_company.get(company)
        if match:
            match.pop("_start_dt", None)
            results.append(match)
        else:
            results.append({"company": company, "found": False})

    return {"results": results}


def _check_broadcast_history(goods_code: str, months: int = 6) -> dict:
    """최근 N개월 편성표를 뒤져서 동일 상품(goods_code)이 방송된 적 있는지 확인.
    일별로 순차 스캔하면 느려서(최대 180요청) 배치 단위 병렬 요청으로 처리하고,
    방송 이력을 찾으면 그 즉시 반환(전체를 다 뒤지지 않음)."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta, timezone

    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).date()
    total_days = months * 30
    dates = [today - timedelta(days=i) for i in range(1, total_days + 1)]

    def _check_day(d):
        try:
            for it in _fetch_schedule(d.strftime("%Y%m%d")):
                if it.get("code") == goods_code:
                    return {
                        "date": d.strftime("%Y-%m-%d"),
                        "time_start": it.get("time_start", ""),
                        "time_end": it.get("time_end", ""),
                    }
        except Exception:
            pass
        return None

    batch_size = 20
    checked = 0
    with ThreadPoolExecutor(max_workers=batch_size) as ex:
        for i in range(0, len(dates), batch_size):
            batch = dates[i:i + batch_size]
            results = list(ex.map(_check_day, batch))
            checked += len(batch)
            found = next((res for res in results if res), None)
            if found:
                return {
                    "found": True,
                    "last_date": found["date"],
                    "last_time_start": found["time_start"],
                    "last_time_end": found["time_end"],
                    "checked_days": checked,
                    "is_new": False,
                }

    return {"found": False, "last_date": None, "checked_days": checked, "is_new": True}


def _fetch_video_source(url: str) -> dict:
    """직접 파일 링크(mp4 등 녹화 영상)를 로컬에 다운로드 (STT 전 단계)"""
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_cache")
    os.makedirs(cache_dir, exist_ok=True)

    try:
        filename = os.path.basename(urlparse(url).path) or "video.mp4"
        if "." not in filename:
            filename += ".mp4"
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
        local_path = os.path.join(cache_dir, filename)

        with req_lib.get(url, stream=True, verify=False, timeout=30, headers=_HEADERS_UA) as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "")
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)

        return {
            "title": filename,
            "file": local_path,
            "content_type": content_type,
            "size": os.path.getsize(local_path),
        }
    except Exception as e:
        return {"error": str(e)}


_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper_model():
    """faster-whisper 모델을 지연 로딩 + 공유 (최초 1회만 로딩/다운로드)"""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                import huggingface_hub
                huggingface_hub.set_client_factory(
                    lambda: httpx.Client(verify=False, follow_redirects=True, timeout=None)
                )
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


_voice_encoder = None
_voice_encoder_lock = threading.Lock()
_normalize_volume = None


def _get_voice_encoder():
    """화자 구분용 목소리 임베딩 모델(resemblyzer)을 지연 로딩.
    resemblyzer는 webrtcvad를 임포트만 하고(무음 트리밍용) 실제로는 쓰지 않는 경로라
    Windows에 빌드 도구 없이 설치 가능하도록 더미 모듈로 스텁 처리한다."""
    global _voice_encoder, _normalize_volume
    if _voice_encoder is None:
        with _voice_encoder_lock:
            if _voice_encoder is None:
                import sys
                import types
                if "webrtcvad" not in sys.modules:
                    stub = types.ModuleType("webrtcvad")

                    class _StubVad:
                        def __init__(self, *a, **k):
                            pass

                        def is_speech(self, *a, **k):
                            return True

                    stub.Vad = _StubVad
                    sys.modules["webrtcvad"] = stub

                from resemblyzer import VoiceEncoder, normalize_volume
                _voice_encoder = VoiceEncoder(device="cpu")
                _normalize_volume = normalize_volume
    return _voice_encoder, _normalize_volume


_MAX_SPEAKERS = 3
_SPEAKER_SIM_THRESHOLD = 0.80
_MIN_NEW_SPEAKER_SECONDS = 1.2


def _assign_speaker(sess, embedding, duration: float = 999.0) -> int:
    """임베딩을 기존 화자 클러스터에 배정(코사인 유사도 기반 증분 클러스터링). 최대 3명, 유사도가 낮으면 새 화자 생성.
    단, 발화가 너무 짧으면(<1.2초) 임베딩이 불안정해서 새 화자를 만들지 않고 가장 가까운 기존 화자에 붙인다
    (짧은 맞장구 한마디 때문에 엉뚱한 화자가 새로 생기는 것을 방지)."""
    centroids = sess.setdefault("speaker_centroids", [])
    counts = sess.setdefault("speaker_counts", [])
    if not centroids:
        centroids.append(embedding.copy())
        counts.append(1)
        return 0

    sims = [
        float(np.dot(embedding, c) / (np.linalg.norm(embedding) * np.linalg.norm(c) + 1e-8))
        for c in centroids
    ]
    best = int(np.argmax(sims))
    can_spawn = duration >= _MIN_NEW_SPEAKER_SECONDS and len(centroids) < _MAX_SPEAKERS
    if sims[best] >= _SPEAKER_SIM_THRESHOLD or not can_spawn:
        n = counts[best]
        centroids[best] = (centroids[best] * n + embedding) / (n + 1)
        counts[best] = n + 1
        return best

    centroids.append(embedding.copy())
    counts.append(1)
    return len(centroids) - 1


_live_sessions: dict = {}
_LIVE_CHUNK_SECONDS = 5


def _live_worker(session_id: str, url: str):
    """HLS 라이브 URL → FFmpeg로 PCM 오디오 추출 → 청크 단위 faster-whisper STT"""
    sess = _live_sessions[session_id]
    cmd = [
        "ffmpeg", "-loglevel", "error",
        "-allowed_extensions", "ALL", "-allowed_segment_extensions", "ALL", "-extension_picky", "0",
        "-i", url,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        with sess["lock"]:
            sess["transcript"].append({
                "start": 0,
                "text": "[오류] ffmpeg를 찾을 수 없습니다. 설치 후 터미널을 새로 열어 proxy.py를 다시 실행해주세요.",
            })
        sess["stop"].set()
        return

    sess["proc"] = proc
    chunk_bytes = _LIVE_CHUNK_SECONDS * 16000 * 2
    elapsed = 0.0

    try:
        model = _get_whisper_model()
    except Exception as e:
        with sess["lock"]:
            sess["transcript"].append({"start": 0, "text": f"[오류] 음성 인식 모델 로딩 실패: {e}"})
        sess["stop"].set()
        proc.terminate()
        return

    try:
        encoder, normalize_volume = _get_voice_encoder()
    except Exception:
        encoder, normalize_volume = None, None

    # 홈쇼핑 도메인 용어 힌트 — STT가 자주 헷갈리는 방송 심의/판매 용어를 미리 알려줘서 인식률을 높인다.
    domain_prompt = (
        "홈쇼핑 방송 쇼호스트의 발화입니다. "
        "완판임박, 매진임박, 무이자, 적립금, 사은품, 구성 추가, 단독 혜택, 정기배송, "
        "직후방송 절대불가, 이 조건 불가, 방송 종료 즉시 마감 같은 표현이 자주 나옵니다."
    )
    prev_tail = ""

    while not sess["stop"].is_set():
        buf = b""
        while len(buf) < chunk_bytes:
            data = proc.stdout.read(chunk_bytes - len(buf))
            if not data:
                break
            buf += data
        if not buf:
            break

        audio = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        chunk_start = elapsed
        elapsed += len(buf) / (16000 * 2)

        try:
            prompt = domain_prompt + (" " + prev_tail if prev_tail else "")
            segments, _ = model.transcribe(
                audio, language="ko", vad_filter=True, initial_prompt=prompt,
            )
            segments = list(segments)
            if segments:
                prev_tail = "".join(s.text for s in segments).strip()[-200:]
        except Exception:
            segments = []

        # 화자 구분은 5초 청크 전체가 아니라 whisper가 나눈 발화 단위(segment)별로 수행한다.
        # 청크 전체로 하나의 임베딩을 뽑으면 두 사람이 한 청크 안에서 번갈아 말할 때
        # 섞인 목소리 임베딩이 되어 화자가 잘 안 갈리는 문제가 있었음.
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue

            speaker = ""
            if encoder is not None:
                try:
                    s_idx = max(0, int(seg.start * 16000))
                    e_idx = min(len(audio), int(seg.end * 16000))
                    seg_audio = audio[s_idx:e_idx]
                    if len(seg_audio) >= 8000:  # 최소 0.5초 이상일 때만 임베딩 계산
                        wav = normalize_volume(seg_audio, -30, increase_only=True)
                        seg_duration = len(seg_audio) / 16000
                        spk_idx = _assign_speaker(sess, encoder.embed_utterance(wav), seg_duration)
                        speaker = f"쇼호스트{spk_idx + 1}"
                except Exception:
                    speaker = ""

            with sess["lock"]:
                sess["transcript"].append({
                    "start": round(chunk_start + seg.start, 1),
                    "text": text,
                    "speaker": speaker,
                })

    proc.terminate()


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/search-product":
            q = params.get("q", [""])[0]
            products = _search_hnsmall(q) if q else []
            self._json_response(products)

        elif parsed.path == "/api/product-score":
            code = params.get("code", [""])[0]
            score = _fetch_review_score(code) if code else {}
            self._json_response(score)

        elif parsed.path == "/api/schedule":
            date = params.get("date", [""])[0]
            items = _fetch_schedule(date)
            self._json_response(items)

        elif parsed.path == "/api/generate-news":
            self._json_response({"status": "started"})
            import subprocess, sys
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_news.py")
            subprocess.Popen([sys.executable, script], creationflags=0x08000000 if os.name == 'nt' else 0)

        elif parsed.path == "/api/news-date":
            try:
                base = os.path.dirname(os.path.abspath(__file__))
                with open(os.path.join(base, "daily_news.json"), encoding="utf-8") as f:
                    import json as _json
                    data = _json.load(f)
                    self._json_response({"date": data.get("date", "")})
            except Exception:
                self._json_response({"date": ""})

        elif parsed.path == "/api/product-detail":
            code = params.get("code", [""])[0]
            detail = _fetch_product_detail(code) if code else {}
            self._json_response(detail)

        elif parsed.path == "/api/shopping-insight":
            self._json_response(_get_shopping_insight())

        elif parsed.path == "/api/news-search":
            q = params.get("q", [""])[0]
            n = int(params.get("n", ["5"])[0])
            self._json_response(_search_naver_news(q, n) if q else [])

        elif parsed.path == "/api/shop-search":
            q = params.get("q", [""])[0]
            n = int(params.get("n", ["100"])[0])
            self._json_response(_search_naver_shop(q, min(n, 100)) if q else {})

        elif parsed.path == "/api/datalab-trend":
            q = params.get("q", [""])[0]
            self._json_response(_get_datalab_trend(q) if q else {})

        elif parsed.path == "/api/search-reviews":
            q = params.get("q", [""])[0]
            n = int(params.get("n", ["10"])[0])
            reviews = _search_naver_blog(q, n) if q else []
            self._json_response(reviews)

        elif parsed.path == "/api/live-transcript":
            sid = params.get("id", [""])[0]
            since = int(params.get("since", ["0"])[0])
            sess = _live_sessions.get(sid)
            if not sess:
                self._json_response({"segments": [], "total": 0})
            else:
                with sess["lock"]:
                    segs = sess["transcript"][since:]
                    total = len(sess["transcript"])
                self._json_response({"segments": segs, "total": total})

        elif parsed.path == "/api/live-broadcast-info":
            self._json_response(_get_live_broadcast_info())

        elif parsed.path == "/api/live-all-channels":
            name = params.get("name", [""])[0]
            self._json_response(_get_all_live_broadcasts(name))

        elif parsed.path == "/api/product-web-info":
            name = params.get("name", [""])[0]
            self._json_response(_get_product_web_info(name) if name else {"error": "name이 없습니다"})

        elif parsed.path == "/api/broadcast-history":
            code = params.get("code", [""])[0]
            self._json_response(_check_broadcast_history(code) if code else {"error": "code가 없습니다"})

        elif parsed.path == "/api/competitor-history":
            name = params.get("name", [""])[0]
            self._json_response(_check_competitor_history(name) if name else {"error": "name이 없습니다"})

        elif parsed.path == "/api/lens/broadcast-monitor":
            self._lens_proxy("/api/live/broadcast-monitor")

        elif parsed.path == "/api/lens/broadcast-status":
            self._lens_proxy("/api/live/broadcast-status")

        elif parsed.path == "/api/lens/inflow-outflow":
            self._lens_proxy("/api/live/inflow-outflow")

        elif parsed.path == "/api/lens/competitor-schedule":
            self._lens_proxy("/api/live/competitor-schedule")

        elif parsed.path == "/api/lens/collection-status":
            self._lens_proxy("/api/settings/collection-status")

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/whisper":
            self._handle_whisper()
            return

        if parsed.path == "/api/vision":
            self._handle_vision()
            return

        if parsed.path == "/api/live-start":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            url = body.get("url", "").strip()
            if not url:
                self._json_response({"error": "URL이 없습니다"})
                return
            session_id = uuid.uuid4().hex[:8]
            _live_sessions[session_id] = {
                "stop": threading.Event(), "transcript": [], "lock": threading.Lock(), "proc": None,
            }
            threading.Thread(target=_live_worker, args=(session_id, url), daemon=True).start()
            self._json_response({"id": session_id})
            return

        if parsed.path == "/api/live-stop":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            sess = _live_sessions.get(body.get("id", ""))
            if sess:
                sess["stop"].set()
                if sess.get("proc"):
                    try:
                        sess["proc"].terminate()
                    except Exception:
                        pass
            self._json_response({"status": "stopped"})
            return

        if parsed.path == "/api/video-info":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            url = body.get("url", "").strip()
            if not url:
                self._json_response({"error": "URL이 없습니다"})
                return
            self._json_response(_fetch_video_source(url))
            return

        if parsed.path != "/api/summarize":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        prompt = json.loads(self.rfile.read(n) or b"{}").get("prompt", "")

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            client = anthropic.Anthropic(
                api_key=API_KEY,
                http_client=httpx.Client(verify=False),
            )
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    self.wfile.write(
                        f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n".encode()
                    )
                    self.wfile.flush()
        except Exception as e:
            self.wfile.write(f"data: {json.dumps({'error': str(e)})}\n\n".encode())
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _handle_vision(self):
        """Claude Vision API - 이미지 분석"""
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        images = body.get("images", [])
        prompt_text = body.get("prompt", "이 이미지의 내용을 설명해주세요.")

        content = []
        for img_data in images[:5]:
            if img_data.startswith("data:"):
                media_type = img_data.split(";")[0].split(":")[1]
                base64_data = img_data.split(",")[1]
            else:
                media_type = "image/png"
                base64_data = img_data
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": base64_data},
            })
        content.append({"type": "text", "text": prompt_text})

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            client = anthropic.Anthropic(
                api_key=API_KEY,
                http_client=httpx.Client(verify=False),
            )
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            ) as stream:
                for chunk in stream.text_stream:
                    self.wfile.write(
                        f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n".encode()
                    )
                    self.wfile.flush()
        except Exception as e:
            self.wfile.write(f"data: {json.dumps({'error': str(e)})}\n\n".encode())
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _handle_whisper(self):
        """로컬 Whisper STT 처리"""
        import tempfile
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        boundary = content_type.split("boundary=")[-1].encode()
        parts = body.split(b"--" + boundary)

        audio_data = None
        for part in parts:
            if b"filename=" in part:
                header_end = part.find(b"\r\n\r\n")
                if header_end > 0:
                    audio_data = part[header_end + 4:].rstrip(b"\r\n--")
                    break

        if not audio_data:
            self._json_response({"error": "음성 파일이 없습니다"})
            return

        try:
            import whisper
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                tmp_path = f.name

            model = whisper.load_model("base")
            result = model.transcribe(tmp_path, language="ko")
            os.unlink(tmp_path)

            self._json_response({"text": result.get("text", "")})
        except ImportError:
            self._json_response({"error": "whisper 미설치. pip install openai-whisper 실행 필요"})
        except Exception as e:
            self._json_response({"error": str(e)})

    def _lens_proxy(self, lens_path):
        try:
            self._json_response(_lens_get(lens_path))
        except Exception as e:
            self._json_response({"error": f"Lens 연동 실패: {e}"})

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ThreadingHTTPServer(("localhost", PORT), Handler).serve_forever()
