"""
AI 요약 프록시 서버 — app.py가 subprocess로 자동 실행
secrets.toml의 ANTHROPIC_API_KEY를 읽어 Claude API를 서버 사이드 호출
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import httpx

PORT = 8502


def _read_key() -> tuple[str, str]:
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

    return _toml("ANTHROPIC_API_KEY"), _toml("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


API_KEY, MODEL = _read_key()


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/summarize":
            self.send_error(404)
            return
        n      = int(self.headers.get("Content-Length", 0))
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

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("localhost", PORT), Handler).serve_forever()
