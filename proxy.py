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
        return {
            "score": score_m.group(1) if score_m else "",
            "count": count_m.group(1) if count_m else "0",
            "level": level_m.group(1).strip() if level_m else "",
        }
    except Exception:
        return {"score": "", "count": "0", "level": ""}


def _search_naver_blog(keyword: str, display: int = 10) -> list[dict]:
    """네이버 블로그에서 상품 후기 검색"""
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
            results.append({
                "title": title,
                "desc": desc,
                "link": item.get("link", ""),
                "date": item.get("postdate", ""),
                "blogger": item.get("bloggername", ""),
            })
        return results
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

        elif parsed.path == "/api/search-reviews":
            q = params.get("q", [""])[0]
            n = int(params.get("n", ["10"])[0])
            reviews = _search_naver_blog(q, n) if q else []
            self._json_response(reviews)

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
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
                max_tokens=1024,
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
