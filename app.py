"""
홈쇼핑 AI 카피 메이커 — Streamlit 앱
API 키는 .streamlit/secrets.toml 또는 환경변수에서만 로드.
소스 코드에 키를 절대 저장하지 않습니다.
"""

import json
import os
import re
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import requests
import streamlit as st

PROXY_PORT = 8502

# ───────────────────────────────────────────────────────────
# 페이지 설정
# ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 카피 메이커 · 홈앤쇼핑",
    page_icon="🛍️",
    layout="wide",
)

CATEGORIES = [
    "식품 · 건강",
    "뷰티 · 스킨케어",
    "패션 · 의류",
    "생활가전",
    "홈리빙 · 인테리어",
]


# ───────────────────────────────────────────────────────────
# 설정 로드 — secrets.toml → 환경변수 순서
# 이 함수만이 키에 접근한다. 소스 어디에도 키 값을 쓰지 않는다.
# ───────────────────────────────────────────────────────────
def _cfg() -> dict:
    def get(key: str, default: str = "") -> str:
        try:
            v = st.secrets.get(key)          # secrets.toml 우선
            return v if v is not None else os.environ.get(key, default)
        except Exception:
            return os.environ.get(key, default)  # toml 없으면 환경변수

    return {
        "api_key": get("ANTHROPIC_API_KEY"),
        "model":   get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        "n_tok":   get("NOTION_TOKEN"),
        "n_db":    get("NOTION_DATABASE_ID"),
    }


# ───────────────────────────────────────────────────────────
# siljeok.html AI 요약용 프록시 — Streamlit 시작 시 자동 실행
# ───────────────────────────────────────────────────────────
@st.cache_resource
def _start_proxy(api_key: str, model: str) -> None:
    """localhost:8502에서 SSE 프록시를 백그라운드 스레드로 시작 (한 번만)"""
    _key, _mdl = api_key, model

    class _Handler(BaseHTTPRequestHandler):
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
                client = anthropic.Anthropic(api_key=_key)
                with client.messages.stream(
                    model=_mdl,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for chunk in stream.text_stream:
                        self.wfile.write(
                            f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n".encode()
                        )
                        self.wfile.flush()
            except Exception as e:
                self.wfile.write(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode()
                )
                self.wfile.flush()

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

        def log_message(self, *args):
            pass

    def _run():
        try:
            HTTPServer(("localhost", PROXY_PORT), _Handler).serve_forever()
        except OSError:
            pass  # 이미 같은 포트에서 실행 중이면 무시

    threading.Thread(target=_run, daemon=True).start()


# ───────────────────────────────────────────────────────────
# Anthropic 클라이언트 — api_key 값 기준으로 캐시
# ───────────────────────────────────────────────────────────
@st.cache_resource
def _make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


# ───────────────────────────────────────────────────────────
# 에러 → 사용자 친화적 메시지 변환
# ───────────────────────────────────────────────────────────
def _friendly(e: Exception) -> str:
    msg = str(e).lower()
    if "401" in msg or "authentication" in msg or "invalid" in msg:
        return (
            "🔑 **API 키가 올바르지 않습니다.**\n\n"
            "`.streamlit/secrets.toml`의 `ANTHROPIC_API_KEY` 값을 확인하세요.\n"
            "앱을 재시작하면 새 키가 적용됩니다."
        )
    if "429" in msg or "rate_limit" in msg:
        return "⏱️ **요청 한도 초과입니다.** 잠시 후 다시 시도해주세요."
    if "overload" in msg:
        return "🌐 **Claude 서버가 일시적으로 혼잡합니다.** 30초 후 다시 시도해주세요."
    if "timeout" in msg or "connection" in msg:
        return "📡 **네트워크 오류입니다.** 연결 상태를 확인하고 다시 시도해주세요."
    return f"오류가 발생했습니다: {e}"


# ───────────────────────────────────────────────────────────
# Claude API — 카피 생성
# ───────────────────────────────────────────────────────────
def generate_copy(api_key: str, model: str,
                  product: str, cat: str,
                  price: str, feat1: str, feat2: str) -> dict:
    prompt = f"""당신은 한국 홈쇼핑 전문 카피라이터입니다. 아래 상품 정보로 마케팅 카피를 작성하세요.

상품명: {product}
카테고리: {cat}
가격: {price or '미정'}
핵심 특징1: {feat1 or '-'}
핵심 특징2: {feat2 or '-'}

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "titles": ["카드뉴스 제목1 (임팩트 있게)", "카드뉴스 제목2 (가격·혜택 강조)", "카드뉴스 제목3 (감성·스토리)"],
  "caption": "인스타그램 캡션 (이모지 포함, 줄바꿈 사용, 5-7줄, 홈앤쇼핑 구매 안내 포함)",
  "hashtags": "#홈앤쇼핑 #관련태그1 #관련태그2 (총 18개)",
  "opening": "TV홈쇼핑 방송 오프닝 멘트 (2-3문장, 친근하고 활기찬 어조)"
}}"""

    client = _make_client(api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = msg.content[0].text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("AI 응답 형식을 파싱할 수 없습니다. 다시 시도해주세요.")
    return json.loads(m.group())


# ───────────────────────────────────────────────────────────
# Notion 저장 — 서버 사이드이므로 CORS 불필요
# ───────────────────────────────────────────────────────────
def save_to_notion(n_tok: str, n_db: str,
                   product: str, cat: str, data: dict) -> None:
    def txt(s: str) -> list:
        return [{"text": {"content": s[:2000]}}]

    titles = data.get("titles", ["", "", ""])
    payload = {
        "parent": {"database_id": n_db},
        "properties": {
            "상품명":   {"title": txt(product)},
            "카테고리": {"select": {"name": cat}},
            "제목1":    {"rich_text": txt(titles[0] if len(titles) > 0 else "")},
            "제목2":    {"rich_text": txt(titles[1] if len(titles) > 1 else "")},
            "제목3":    {"rich_text": txt(titles[2] if len(titles) > 2 else "")},
            "캡션":     {"rich_text": txt(data.get("caption", ""))},
            "해시태그":  {"rich_text": txt(data.get("hashtags", ""))},
            "오프닝":   {"rich_text": txt(data.get("opening", ""))},
            "생성일":   {"date": {"start": date.today().isoformat()}},
        },
    }
    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {n_tok}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        json=payload,
        timeout=15,
    )
    if not r.ok:
        raise RuntimeError(f"Notion 저장 실패: {r.json().get('message', r.status_code)}")


# ───────────────────────────────────────────────────────────
# 사이드바 — 상태 표시 + 설정 가이드
# ───────────────────────────────────────────────────────────
def _sidebar(cfg: dict) -> None:
    with st.sidebar:
        st.header("⚙️ 연결 상태")

        if cfg["api_key"]:
            model_short = cfg["model"].replace("claude-", "").replace("-20251001", "")
            st.success(f"✅ Claude API 연결됨\n\n모델: `{model_short}`")
        else:
            st.error("❌ Claude API 키 없음")

        if cfg["n_tok"] and cfg["n_db"]:
            st.success("✅ Notion 연동 완료")
        else:
            st.info("ℹ️ Notion 미설정 (선택)")

        st.divider()
        st.markdown("[← 홈앤쇼핑 포탈](https://prettykbk81.github.io/hnsinfo/)")


# ───────────────────────────────────────────────────────────
# 메인 UI
# ───────────────────────────────────────────────────────────
def main() -> None:
    cfg = _cfg()
    api_key = cfg["api_key"]
    model   = cfg["model"]

    if api_key:
        _start_proxy(api_key, model)  # siljeok.html AI 요약 프록시 자동 시작

    _sidebar(cfg)

    # ── 헤더 ──────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#1a0533,#2d1b69,#0c3547);
                    padding:32px 24px 28px;border-radius:14px;color:#fff;
                    text-align:center;margin-bottom:20px;">
          <p style="font-size:11px;font-weight:700;color:#c4b5fd;
                    letter-spacing:.1em;margin-bottom:6px;">
            CLAUDE'S VIBE CODING · 2026.06
          </p>
          <h1 style="font-size:34px;font-weight:900;margin:0 0 10px;">
            🛍️ 홈쇼핑 AI 카피 메이커
          </h1>
          <p style="font-size:14px;color:rgba(255,255,255,.65);margin:0;">
            상품 정보만 입력하면 카드뉴스 제목·캡션·해시태그·방송 오프닝을 Claude AI가 즉시 작성합니다
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 입력 폼 ───────────────────────────────────────────
    with st.container(border=True):
        st.subheader("📦 상품 정보 입력")

        col1, col2 = st.columns(2)
        with col1:
            product = st.text_input("상품명 *", placeholder="예) 제주 한라봉 주스", max_chars=40)
        with col2:
            cat = st.selectbox("카테고리 *", options=CATEGORIES)

        col3, col4 = st.columns(2)
        with col3:
            price = st.text_input("가격대", placeholder="예) 29,900원 / 3개 세트")
        with col4:
            feat1 = st.text_input("핵심 특징 ①", placeholder="예) 무농약 인증")

        feat2 = st.text_input("핵심 특징 ②", placeholder="예) 착즙 100% 무첨가")

        clicked = st.button(
            "✨ Claude AI로 카피 생성",
            type="primary",
            use_container_width=True,
        )

    if clicked:
        if not product:
            st.error("상품명을 입력해주세요.")
        else:
            with st.spinner("Claude가 카피를 작성 중입니다…"):
                try:
                    results = generate_copy(api_key, model, product, cat, price, feat1, feat2)
                    st.session_state["results"] = results
                    st.session_state["meta"] = {
                        "product": product,
                        "cat": cat,
                        "price": price,
                        "feat1": feat1,
                        "feat2": feat2,
                    }
                except Exception as e:
                    st.error(_friendly(e))   # 친절한 에러 메시지

    # ── 결과 ─────────────────────────────────────────────
    if "results" not in st.session_state:
        return

    r    = st.session_state["results"]
    meta = st.session_state.get("meta", {})

    st.divider()
    st.subheader("📋 생성된 카피")

    with st.expander("📌 카드뉴스 제목 3종", expanded=True):
        for i, title in enumerate(r.get("titles", []), 1):
            st.code(f"{i}. {title}", language=None)

    with st.expander("📸 인스타그램 캡션", expanded=True):
        st.code(r.get("caption", ""), language=None)

    with st.expander("#️⃣ 해시태그 세트", expanded=True):
        st.code(r.get("hashtags", ""), language=None)

    with st.expander("🎙️ 방송 오프닝 멘트", expanded=True):
        st.code(r.get("opening", ""), language=None)

    # ── 액션 버튼 ─────────────────────────────────────────
    st.divider()
    b1, b2, b3 = st.columns(3)

    with b1:
        notion_ready = bool(cfg["n_tok"] and cfg["n_db"])
        if st.button(
            "📥 Notion에 저장",
            disabled=not notion_ready,
            use_container_width=True,
            help=(
                "Notion 연동 완료 ✅" if notion_ready
                else "secrets.toml에 NOTION_TOKEN과 NOTION_DATABASE_ID를 추가하면 활성화됩니다."
            ),
        ):
            with st.spinner("Notion에 저장 중…"):
                try:
                    save_to_notion(cfg["n_tok"], cfg["n_db"],
                                   meta["product"], meta["cat"], r)
                    st.success("Notion에 저장되었습니다! ✓")
                except Exception as e:
                    st.error(_friendly(e))

    with b2:
        titles_text = "\n".join(
            f"{i + 1}. {t}" for i, t in enumerate(r.get("titles", []))
        )
        full_text = (
            f"===== 홈쇼핑 AI 카피 메이커 =====\n"
            f"상품명: {meta.get('product','')}  |  카테고리: {meta.get('cat','')}  |  가격: {meta.get('price','')}\n"
            f"생성일: {date.today().isoformat()}\n\n"
            f"[카드뉴스 제목]\n{titles_text}\n\n"
            f"[인스타그램 캡션]\n{r.get('caption', '')}\n\n"
            f"[해시태그]\n{r.get('hashtags', '')}\n\n"
            f"[방송 오프닝 멘트]\n{r.get('opening', '')}\n"
        )
        st.download_button(
            "⬇️ 텍스트 다운로드",
            data=full_text.encode("utf-8"),
            file_name=f"카피_{meta.get('product', '결과')}_{date.today().isoformat()}.txt",
            mime="text/plain;charset=utf-8",
            use_container_width=True,
        )

    with b3:
        if st.button("🔄 다시 생성", use_container_width=True):
            m = st.session_state.get("meta", {})
            with st.spinner("Claude가 카피를 다시 작성 중입니다…"):
                try:
                    results = generate_copy(
                        api_key, model,
                        m.get("product", ""), m.get("cat", ""),
                        m.get("price", ""), m.get("feat1", ""), m.get("feat2", ""),
                    )
                    st.session_state["results"] = results
                    st.rerun()
                except Exception as e:
                    st.error(_friendly(e))


if __name__ == "__main__":
    main()
