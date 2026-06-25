"""
AI 요약 프록시 서버 — app.py가 subprocess로 자동 실행
secrets.toml의 API 키를 읽어 Claude API + 상품 검색 + 리뷰 수집을 서버 사이드 호출
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import anthropic
import httpx
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
        name_m = re.search(r'class="tit"[^>]*>([^<]+)<', t[40000:50000])
        if name_m:
            result["name"] = name_m.group(1).strip()
        cat_m = re.search(r'asideOption[\s\S]{0,200}?<p\s+class="tit">([^<]+)<', t)
        if cat_m:
            nm = cat_m.group(1).strip()
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
    """홈앤쇼핑 TV 편성표 가져오기"""
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
        for m in re.finditer(
            r'<li\s+class="item">([\s\S]*?)</li>', t
        ):
            block = m.group(1)
            time_m = re.search(r'<b>(\d{1,2}:\d{2})</b>\s*~\s*(\d{1,2}:\d{2})', block)
            name_m = re.search(r'<b>[\d:]+</b>\s*~\s*[\d:]+</span>([^<]+)<', block)
            code_m = re.search(r"goGoods\('(\d+)'", block)
            img_m = re.search(r'<img\s+src="(//image[^"]+)"', block)
            if not time_m:
                continue
            items.append({
                "time_start": time_m.group(1),
                "time_end": time_m.group(2),
                "name": name_m.group(1).strip() if name_m else "",
                "code": code_m.group(1) if code_m else "",
                "image": ("https:" + img_m.group(1)) if img_m else "",
            })
        return items
    except Exception:
        return []


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
    HTTPServer(("localhost", PORT), Handler).serve_forever()
