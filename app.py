"""
홈쇼핑 AI 카피 메이커 — Streamlit 앱
API 키는 .streamlit/secrets.toml 또는 환경변수에서만 로드.
소스 코드에 절대 저장하지 않습니다.
"""

import json
import os
import re
from datetime import date

import anthropic
import requests
import streamlit as st

# ───────────────────────────────────────────────────────────
# 페이지 설정
# ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 카피 메이커 · 홈앤쇼핑",
    page_icon="🛍️",
    layout="wide",
)

# ───────────────────────────────────────────────────────────
# 설정 로드 — secrets.toml → 환경변수 순서
# 키를 소스에 직접 쓰지 않기 위해 이 함수만 사용한다.
# ───────────────────────────────────────────────────────────
def _get(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)


ANTHROPIC_API_KEY  = _get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL    = _get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
NOTION_TOKEN       = _get("NOTION_TOKEN")
NOTION_DATABASE_ID = _get("NOTION_DATABASE_ID")

CATEGORIES = [
    "식품 · 건강",
    "뷰티 · 스킨케어",
    "패션 · 의류",
    "생활가전",
    "홈리빙 · 인테리어",
]

# ───────────────────────────────────────────────────────────
# Claude API (서버 사이드)
# ───────────────────────────────────────────────────────────
def generate_copy(product: str, cat: str, price: str, feat1: str, feat2: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
            ".streamlit/secrets.toml 에 키를 추가하세요."
        )

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
  "opening": "TV홈쇼핑 방송 오프닝 멘트 (2-3문장, 친근하고 활기찬 어조, 시청자에게 직접 말하는 형식)"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = msg.content[0].text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("AI 응답 형식 오류입니다. 다시 시도해주세요.")
    return json.loads(m.group())


# ───────────────────────────────────────────────────────────
# Notion 저장 (서버 사이드 — CORS 문제 없음)
# ───────────────────────────────────────────────────────────
def save_to_notion(product: str, cat: str, data: dict) -> None:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        raise EnvironmentError(
            "NOTION_TOKEN 또는 NOTION_DATABASE_ID가 설정되지 않았습니다."
        )

    titles = data.get("titles", ["", "", ""])

    def txt(s: str) -> list:
        return [{"text": {"content": s[:2000]}}]

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
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
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        json=payload,
        timeout=15,
    )
    if not r.ok:
        raise RuntimeError(f"Notion 저장 실패: {r.json().get('message', r.status_code)}")


# ───────────────────────────────────────────────────────────
# 메인 UI
# ───────────────────────────────────────────────────────────
def main() -> None:

    # ── 헤더 ──────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#1a0533,#2d1b69,#0c3547);
                    padding:32px 24px 28px;border-radius:14px;color:#fff;
                    text-align:center;margin-bottom:20px;">
          <p style="font-size:11px;font-weight:700;color:#c4b5fd;letter-spacing:.1em;margin-bottom:6px;">
            CLAUDE'S VIBE CODING · 2026.06
          </p>
          <h1 style="font-size:34px;font-weight:900;margin:0 0 10px;">🛍️ 홈쇼핑 AI 카피 메이커</h1>
          <p style="font-size:14px;color:rgba(255,255,255,.65);margin:0;">
            상품 정보만 입력하면 카드뉴스 제목·캡션·해시태그·방송 오프닝을 Claude AI가 즉시 작성합니다
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── API 상태 표시 ──────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        if ANTHROPIC_API_KEY:
            st.success(f"✅ Claude API 연결됨")
        else:
            st.error("❌ Claude API 키 미설정")
    with c2:
        if NOTION_TOKEN and NOTION_DATABASE_ID:
            st.success("✅ Notion 연동 완료")
        else:
            st.warning("⚠️ Notion 미설정 (선택사항)")
    with c3:
        model_short = ANTHROPIC_MODEL.replace("claude-", "").replace("-20251001", "")
        st.info(f"🤖 모델: {model_short}")

    st.divider()

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

        if st.button("✨ Claude AI로 카피 생성", type="primary", use_container_width=True):
            if not product:
                st.error("상품명을 입력해주세요.")
            else:
                with st.spinner("Claude가 카피를 작성 중입니다…"):
                    try:
                        results = generate_copy(product, cat, price, feat1, feat2)
                        st.session_state["results"] = results
                        st.session_state["meta"] = {
                            "product": product,
                            "cat": cat,
                            "price": price,
                            "feat1": feat1,
                            "feat2": feat2,
                        }
                    except Exception as e:
                        st.error(str(e))

    # ── 결과 ─────────────────────────────────────────────
    if "results" not in st.session_state:
        return

    r = st.session_state["results"]
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
        notion_ready = bool(NOTION_TOKEN and NOTION_DATABASE_ID)
        if st.button(
            "📥 Notion에 저장",
            disabled=not notion_ready,
            use_container_width=True,
            help="secrets.toml에 NOTION_TOKEN과 NOTION_DATABASE_ID가 있어야 활성화됩니다.",
        ):
            with st.spinner("Notion에 저장 중…"):
                try:
                    save_to_notion(meta["product"], meta["cat"], r)
                    st.success("Notion에 저장되었습니다! ✓")
                except Exception as e:
                    st.error(str(e))

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
                        m.get("product", ""),
                        m.get("cat", ""),
                        m.get("price", ""),
                        m.get("feat1", ""),
                        m.get("feat2", ""),
                    )
                    st.session_state["results"] = results
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # ── 사이드바 ──────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ 설정 가이드")
        st.markdown(
            """
**1. secrets.toml 생성**

프로젝트 루트에서:
```
.streamlit/
  secrets.toml   ← 여기에 키 입력
```

**2. 내용 예시**
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"

# Notion (선택)
NOTION_TOKEN        = "secret_..."
NOTION_DATABASE_ID  = "32자리 ID"
```

**3. 보안**

`secrets.toml`은 `.gitignore`에 등록되어
GitHub에 올라가지 않습니다.

---

**로컬 실행**
```bash
pip install -r requirements.txt
streamlit run app.py
```

**Streamlit Cloud 배포**

Repository → Deploy → Advanced →
Secrets 탭에 동일 내용 붙여넣기
            """
        )
        st.divider()
        st.markdown("[← 홈앤쇼핑 포탈](https://prettykbk81.github.io/hnsinfo/)")


if __name__ == "__main__":
    main()
