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
        ratings = re.findall(r'class="flag\s+(?:red|blue|green|gray)">([^<]+)<', r.text)
        dist = {}
        for rt in ratings:
            rt = rt.strip()
            dist[rt] = dist.get(rt, 0) + 1
        return {
            "score": score_m.group(1) if score_m else "",
            "count": count_m.group(1) if count_m else "0",
            "level": level_m.group(1).strip() if level_m else "",
            "distribution": dist,
        }
    except Exception:
        return {"score": "", "count": "0", "level": ""}


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
