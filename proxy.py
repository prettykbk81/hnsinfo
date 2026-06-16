#!/usr/bin/env python
"""
로컬 Claude API 프록시 서버 (proxy.py)

siljeok.html의 'AI 요약' 버튼이 이 서버를 통해 Claude를 호출합니다.
API 키는 소스 코드가 아닌 .streamlit/secrets.toml에서 읽습니다.

사용법:
  python proxy.py

Streamlit 앱과 별도 터미널에서 실행하세요.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic

PORT = 8502


def _load_key() -> str:
    """secrets.toml → 환경변수 순서로 ANTHROPIC_API_KEY를 로드"""
    # 1. Python 3.11+ 내장 tomllib
    try:
        import tomllib
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f).get("ANTHROPIC_API_KEY", "")
    except (ImportError, FileNotFoundError, Exception):
        pass

    # 2. tomli 패키지 (Python ≤ 3.10)
    try:
        import tomli
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomli.load(f).get("ANTHROPIC_API_KEY", "")
    except (ImportError, FileNotFoundError, Exception):
        pass

    # 3. 직접 파싱 (패키지 없이 key = "value" 형식 읽기)
    try:
        with open(".streamlit/secrets.toml", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("ANTHROPIC_API_KEY"):
                    _, _, val = s.partition("=")
                    return val.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass

    # 4. 환경변수 fallback
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _load_model() -> str:
    try:
        import tomllib
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f).get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    except Exception:
        pass
    try:
        import tomli
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomli.load(f).get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    except Exception:
        pass
    try:
        with open(".streamlit/secrets.toml", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("ANTHROPIC_MODEL"):
                    _, _, val = s.partition("=")
                    return val.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


API_KEY = _load_key()
MODEL   = _load_model()


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/summarize":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        prompt = body.get("prompt", "")

        if not API_KEY:
            self.send_response(500)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "ANTHROPIC_API_KEY가 .streamlit/secrets.toml에 없습니다."
            }).encode())
            return

        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            client = anthropic.Anthropic(api_key=API_KEY)
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    line = f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
        except Exception as e:
            err_line = f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            self.wfile.write(err_line.encode("utf-8"))
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def log_message(self, format, *args):
        pass  # 콘솔 노이즈 억제


if __name__ == "__main__":
    bar = "=" * 54
    print(bar)
    print("  홈앤쇼핑 AI 요약 프록시 서버")
    print(bar)
    if API_KEY:
        masked = API_KEY[:10] + "..." + API_KEY[-4:]
        print(f"  ✅ API 키: {masked}")
        print(f"  ✅ 모델:   {MODEL}")
    else:
        print("  ❌ API 키 없음 — .streamlit/secrets.toml 확인 필요")
        print("     ANTHROPIC_API_KEY = \"sk-ant-...\"")
    print(f"  🚀 주소: http://localhost:{PORT}")
    print("  종료: Ctrl+C")
    print(bar)

    try:
        HTTPServer(("localhost", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  프록시 서버 종료")
