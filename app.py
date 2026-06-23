"""
홈쇼핑 AI 카피 메이커 — Streamlit 앱
API 키는 .streamlit/secrets.toml 또는 환경변수에서만 로드.
소스 코드에 키를 절대 저장하지 않습니다.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date

import anthropic
import httpx
import requests
import streamlit as st

PROXY_PORT = 8502
PROXY_URL = f"http://localhost:{PROXY_PORT}"
_PROXY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py")

CAT_VALUE_TO_LABEL = {
    "food": "식품 · 건강",
    "beauty": "뷰티 · 스킨케어",
    "fashion": "패션 · 의류",
    "appliance": "생활가전",
    "home": "홈리빙 · 인테리어",
}


# ───────────────────────────────────────────────────────────
# secrets.toml 직접 읽기 (st.secrets 없이)
# ───────────────────────────────────────────────────────────
def _read_toml(key: str, default: str = "") -> str:
    try:
        import tomllib
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f).get(key, default) or default
    except (ImportError, FileNotFoundError, Exception):
        pass
    try:
        with open(".streamlit/secrets.toml", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith(key):
                    _, _, val = s.partition("=")
                    return val.strip().strip('"').strip("'") or default
    except FileNotFoundError:
        pass
    return os.environ.get(key, default)


# ───────────────────────────────────────────────────────────
# 프록시 서버 — subprocess로 실행 (Streamlit 모듈 로드 즉시)
# ───────────────────────────────────────────────────────────
def _launch_proxy() -> None:
    import socket
    s = socket.socket()
    already_running = (s.connect_ex(("localhost", PROXY_PORT)) == 0)
    s.close()
    if already_running:
        return  # 이미 실행 중

    if os.path.exists(_PROXY_SCRIPT):
        subprocess.Popen(
            [sys.executable, _PROXY_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )


_launch_proxy()  # streamlit run app.py 실행 즉시 프록시 시작


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
# 설정 로드 — st.secrets → 환경변수 순서 (Streamlit UI용)
# ───────────────────────────────────────────────────────────
def _cfg() -> dict:
    def get(key: str, default: str = "") -> str:
        try:
            v = st.secrets.get(key)
            return v if v is not None else os.environ.get(key, default)
        except Exception:
            return os.environ.get(key, default)

    return {
        "api_key":        get("ANTHROPIC_API_KEY"),
        "model":          get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        "n_tok":          get("NOTION_TOKEN"),
        "n_db":           get("NOTION_DATABASE_ID"),
        "naver_id":       get("NAVER_CLIENT_ID"),
        "naver_secret":   get("NAVER_CLIENT_SECRET"),
    }


# ───────────────────────────────────────────────────────────
# Anthropic 클라이언트 캐시
# ───────────────────────────────────────────────────────────
@st.cache_resource
def _make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=api_key,
        http_client=httpx.Client(verify=False),
    )


# ───────────────────────────────────────────────────────────
# 프록시 API 호출 — 편성표 / 상품 검색 / 상세
# ───────────────────────────────────────────────────────────
def _proxy_get(path: str, params: dict | None = None) -> list | dict:
    r = requests.get(f"{PROXY_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _extract_features(api_key: str, model: str, name: str, description: str) -> dict:
    """기술서에서 Claude로 핵심 특징·카테고리 추출"""
    client = _make_client(api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": (
            "아래 홈쇼핑 상품 기술서에서 핵심 특징 2개를 뽑아주세요.\n\n"
            f"상품명: {name}\n기술서: {description}\n\n"
            '반드시 JSON으로만 응답: {"feat1":"특징1 (15자 이내)",'
            '"feat2":"특징2 (15자 이내)",'
            '"category":"food|beauty|fashion|appliance|home 중 택1"}'
        )}],
    )
    text = msg.content[0].text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group())
    return {}


def _select_product(code: str, name: str, price: str,
                    api_key: str, model: str) -> None:
    """상품 선택 시 session_state에 자동 입력 값 저장"""
    st.session_state["sel_product"] = name
    st.session_state["sel_price"] = price or ""
    st.session_state["sel_feat1"] = ""
    st.session_state["sel_feat2"] = ""
    st.session_state["sel_category"] = ""

    if not code:
        return
    try:
        detail = _proxy_get("/api/product-detail", {"code": code})
        if detail.get("price") and not price:
            st.session_state["sel_price"] = detail["price"]
        desc = detail.get("description", "")
        if desc and api_key:
            feat = _extract_features(api_key, model, name, desc)
            st.session_state["sel_feat1"] = feat.get("feat1", "")
            st.session_state["sel_feat2"] = feat.get("feat2", "")
            st.session_state["sel_category"] = feat.get("category", "")
    except Exception:
        pass


# ───────────────────────────────────────────────────────────
# 에러 → 친화적 메시지
# ───────────────────────────────────────────────────────────
def _friendly(e: Exception) -> str:
    msg = str(e).lower()
    if "401" in msg or "authentication" in msg or "invalid" in msg:
        return "🔑 **API 키가 올바르지 않습니다.** `.streamlit/secrets.toml`의 `ANTHROPIC_API_KEY`를 확인하세요."
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
# Notion 저장
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
# 사이드바
# ───────────────────────────────────────────────────────────
def _sidebar(cfg: dict) -> None:
    with st.sidebar:
        st.header("⚙️ 연결 상태")

        model_short = cfg["model"].replace("claude-", "").replace("-20251001", "")
        st.success(f"✅ Claude API 연결됨\n\n모델: `{model_short}`")

        naver_ok = bool(
            cfg["naver_id"]
            and not cfg["naver_id"].startswith("여기에")
            and cfg["naver_secret"]
            and not cfg["naver_secret"].startswith("여기에")
        )
        if naver_ok:
            st.success("✅ 네이버 뉴스 API 연결됨")
        else:
            st.info("ℹ️ 네이버 API 미설정 (선택)")

        st.info("ℹ️ Notion 미설정 (선택)")

        st.divider()
        st.markdown("[← 홈앤쇼핑 포탈](https://prettykbk81.github.io/hnsinfo/)")


# ───────────────────────────────────────────────────────────
# 메인 UI
# ───────────────────────────────────────────────────────────
def main() -> None:
    cfg     = _cfg()
    api_key = cfg["api_key"]
    model   = cfg["model"]

    _sidebar(cfg)

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

    # ── 편성표 / 상품 검색 ──
    with st.container(border=True):
        st.subheader("🔎 편성표 · 상품 검색")
        st.caption("상품을 선택하면 아래 입력란에 자동으로 채워집니다")

        tab_schedule, tab_search = st.tabs(["📺 오늘 방송 편성표", "🔍 상품 검색"])

        with tab_schedule:
            if st.button("편성표 불러오기", key="btn_schedule"):
                with st.spinner("편성표 로딩 중..."):
                    try:
                        st.session_state["schedule"] = _proxy_get("/api/schedule")
                    except Exception:
                        st.error("편성표를 불러올 수 없습니다. proxy 실행 여부를 확인하세요.")
                        st.session_state["schedule"] = []

            for i, item in enumerate(st.session_state.get("schedule", [])):
                label = f"**{item['time_start']} ~ {item['time_end']}**  {item.get('name', '')}"
                if st.button(label, key=f"sch_{i}", use_container_width=True):
                    with st.spinner(f"'{item['name']}' 상품 정보 분석 중..."):
                        _select_product(
                            item.get("code", ""), item.get("name", ""), "",
                            api_key, model,
                        )
                    st.rerun()

        with tab_search:
            sq1, sq2 = st.columns([4, 1])
            with sq1:
                search_q = st.text_input(
                    "검색어", placeholder="홈앤쇼핑 상품명 검색 (예: 홍삼, 선풍기)",
                    label_visibility="collapsed", key="search_q",
                )
            with sq2:
                search_clicked = st.button("검색", key="btn_search", use_container_width=True)

            if search_clicked and search_q:
                with st.spinner("검색 중..."):
                    try:
                        st.session_state["search_results"] = _proxy_get(
                            "/api/search-product", {"q": search_q},
                        )
                    except Exception:
                        st.error("검색 실패. proxy 실행 여부를 확인하세요.")
                        st.session_state["search_results"] = []

            for i, p in enumerate(st.session_state.get("search_results", [])):
                price_txt = f"  ·  **{p['price']}원**" if p.get("price") else ""
                label = f"{p.get('name', '')}{price_txt}"
                if st.button(label, key=f"sr_{i}", use_container_width=True):
                    with st.spinner(f"'{p['name']}' 상품 정보 분석 중..."):
                        _select_product(
                            p.get("code", ""), p.get("name", ""), p.get("price", ""),
                            api_key, model,
                        )
                    st.rerun()

    # ── 선택된 상품 정보로 기본값 세팅 ──
    sel_product = st.session_state.get("sel_product", "")
    sel_price = st.session_state.get("sel_price", "")
    sel_feat1 = st.session_state.get("sel_feat1", "")
    sel_feat2 = st.session_state.get("sel_feat2", "")
    sel_cat_value = st.session_state.get("sel_category", "")
    sel_cat_label = CAT_VALUE_TO_LABEL.get(sel_cat_value, "")
    cat_index = CATEGORIES.index(sel_cat_label) if sel_cat_label in CATEGORIES else 0

    # ── 상품 정보 입력 폼 ──
    with st.container(border=True):
        st.subheader("📦 상품 정보 입력")

        col1, col2 = st.columns(2)
        with col1:
            product = st.text_input(
                "상품명 *", value=sel_product,
                placeholder="예) 제주 한라봉 주스", max_chars=40,
            )
        with col2:
            cat = st.selectbox("카테고리 *", options=CATEGORIES, index=cat_index)

        col3, col4 = st.columns(2)
        with col3:
            price = st.text_input(
                "가격대", value=sel_price,
                placeholder="예) 29,900원 / 3개 세트",
            )
        with col4:
            feat1 = st.text_input(
                "핵심 특징 ①", value=sel_feat1,
                placeholder="예) 무농약 인증",
            )

        feat2 = st.text_input(
            "핵심 특징 ②", value=sel_feat2,
            placeholder="예) 착즙 100% 무첨가",
        )

        clicked = st.button("✨ Claude AI로 카피 생성", type="primary", use_container_width=True)

    if clicked:
        if not product:
            st.error("상품명을 입력해주세요.")
        else:
            with st.spinner("Claude가 카피를 작성 중입니다…"):
                try:
                    results = generate_copy(api_key, model, product, cat, price, feat1, feat2)
                    st.session_state["results"] = results
                    st.session_state["meta"] = {
                        "product": product, "cat": cat,
                        "price": price, "feat1": feat1, "feat2": feat2,
                    }
                except Exception as e:
                    st.error(_friendly(e))

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

    st.divider()
    b1, b2, b3 = st.columns(3)

    with b1:
        notion_ready = bool(cfg["n_tok"] and cfg["n_db"])
        if st.button(
            "📥 Notion에 저장",
            disabled=not notion_ready,
            use_container_width=True,
            help="Notion 연동 완료 ✅" if notion_ready
                 else "secrets.toml에 NOTION_TOKEN과 NOTION_DATABASE_ID를 추가하면 활성화됩니다.",
        ):
            with st.spinner("Notion에 저장 중…"):
                try:
                    save_to_notion(cfg["n_tok"], cfg["n_db"], meta["product"], meta["cat"], r)
                    st.success("Notion에 저장되었습니다! ✓")
                except Exception as e:
                    st.error(_friendly(e))

    with b2:
        titles_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(r.get("titles", [])))
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
