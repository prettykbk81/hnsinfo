# MI MCP 커머스 업종 리포트 스킬셋

> 리버스 엔지니어링 대상: [심층분석] 2026년 상반기 모바일 쇼핑 앱 시장 분석
> 원본 URL: https://www.igaworksblog.com/post/commerce-2604
> 참고 URL: https://www.igaworksblog.com/post/insight-coupang
> 분석 일자: 2026-05-28

---

## 이 스킬셋으로 무엇을 할 수 있나

MI MCP를 연동한 상태에서 이 스킬셋을 로드하면, 원본 리포트와 유사한 구조의 커머스(이커머스/쇼핑) 업종 분석 리포트를 자동 생성할 수 있습니다.

**MCP 도구 기반 실제 커버리지: 약 90%** (2026-05-28 도구 목록 직접 확인 기준)
- ✅ 커버: MAU·사용시간·신규설치 추이, 성별·연령별 분석, 앱 순위, 충성도·재방문율·이탈 분석, 교차 사용 분석, 업종 스냅샷, 앱 건강도 진단, 30일 삭제율, 페르소나·관심업종
- ❌ 미지원: 결제 데이터(소비인덱스), 카테고리별 매출 비중
- ⚠️ 추후 연동 예정: 결제 금액·건수, 가격대별 결제 분포, 카테고리별 GMV

### 주요 활용

- 오픈마켓 / 종합쇼핑 / 해외직구 등 쇼핑 카테고리 앱의 시장 변화를 데이터 기반으로 분석
- 업종 전체 트렌드 + 앱별 경쟁 구도 + 교차 사용 + 이탈 분석을 하나의 리포트로 통합
- 쿠팡 vs 네이버플러스 스토어 vs C커머스 등 핵심 경쟁 구도 심층 분석
- 모든 수치는 MI MCP가 실시간으로 조회한 실측 데이터 사용

---

## 사전 요건

1. **MI MCP 연동 완료** — `mobileindex` 서버가 활성화 상태여야 합니다
   - MCP 서버 URL: `https://mcp-data-live.mobileindex.com/mi-mcp-public/mcp/`
2. **분석 기간 설정** — 비교 기준월 2개 이상 (예: 1년 전 vs 현재)
3. **분석 대상 업종 확정** — 메인 업종(쇼핑) + 세부 업종(오픈마켓, 해외직구 등)

---

## 파일 구성

| 파일 | 설명 |
|------|------|
| `README.md` | 이 파일 — 개요 및 사용 방법 |
| `report_structure.md` | 원본 리포트 구조 분석 + 섹션별 데이터 소스 매핑 |
| `data_mapping.md` | MI MCP 도구별 조회 가이드 (파라미터, 호출 순서, 주의사항) |
| `prompt_skill.md` | **메인 스킬 파일** — 실행 프롬프트 + 리포트 템플릿 |

---

## 빠른 시작

```
1. MI MCP 연동 확인: MCP 서버 목록에서 mobileindex 활성화 확인
2. 스킬 로드: prompt_skill.md 내용을 컨텍스트로 추가
3. 명령 실행:
   "2026년 상반기 모바일 쇼핑 앱 시장 분석 리포트 만들어줘. 쿠팡, 네이버플러스 스토어, C커머스 중심으로"
```

---

## 데이터 소스 분류

| 구분 | 설명 |
|------|------|
| ✅ MI MCP 직접 조회 | 앱 MAU·사용시간·신규설치 추이, 성별·연령별 분석, 앱 순위, 충성도·재방문율·이탈·교차사용 분석, 업종 스냅샷, 앱 건강도, 30일 삭제율, 페르소나, 관심업종 |
| ❌ MI MCP 미지원 | 결제 데이터(금액·건수·가격대 분포), 카테고리별 매출 비중 |
| ⚠️ 추후 연동 예정 | 소비인덱스(결제 데이터), GMV 추정치 |
| 📝 사용자 직접 입력 | 시장 이벤트 배경(개인정보 유출, 규제 변화 등), 업계 전문가 코멘트 |

---

## MCP 도구 주요 주의사항

| 도구 | 주의사항 |
|------|---------|
| `competitor_loyalty` | pkgName에 1개 앱만 입력 (복수 시 빈 배열) |
| `competitor_retention` | 주간 데이터만 지원 (startDate=월요일, endDate=일요일) |
| `competitor_install_delete` | pkgName에 1개 앱만 입력 |
| `usage_overlap_rank` | dateType "w" 또는 "m"만 지원 (일간 불가) |
| `market_snapshot` | dateType "w" 또는 "m"만 지원 |
| `app_health_check` | dateType "w" 또는 "m"만 지원 |
| `industry_analysis` | industry: "ecommerce" 사용 |

---

*최종 업데이트: 2026-05-28*
# 리포트 구조 분석 — 커머스 업종 데이터 매핑

> 원본: [심층분석] 2026년 상반기 모바일 쇼핑 앱 시장 분석
> 참고: 쿠팡 개인정보 유출 이후 이커머스 시장 변화 분석
> 이 문서는 원본 리포트를 리버스 엔지니어링하여 각 섹션의 데이터 소스와 MI MCP 매핑을 정리한 것입니다.

---

## 1. 리포트 전체 구조

```
[커머스 업종 심층 분석 리포트]
│
├── 0. 헤드라인 & 요약 수치 (3~4개 KPI)
│
├── 1. 쇼핑 업종 전체 현황
│   ├── 1-1. MAU 추이 (역대 최고치 갱신 여부)
│   ├── 1-2. 사용시간 추이 (1인당 사용 강도 변화)
│   ├── 1-3. 사용자 구성 (성별·연령별)
│   └── 1-4. 세부 업종별 온도 차 (오픈마켓/종합쇼핑/해외직구)
│
├── 2. MAU TOP 10 & 핵심 경쟁 구도
│   ├── 2-1. MAU 순위 (1위와 2위 격차)
│   └── 2-2. 시장 3대 변화 요약
│
├── 3. 주제 1 — 지배적 플레이어 분석 (쿠팡)
│   ├── 3-1. 이벤트 전후 MAU 변화 (개인정보 유출 등)
│   ├── 3-2. 이탈 분석 (이탈자 규모 + 이탈 방향)
│   └── 3-3. 구조적 강점 해석 (왜 떠나지 못하는가)
│
├── 4. 주제 2 — 도전자/위협 세력 분석 (C커머스)
│   ├── 4-1. MAU 추이 (성장 둔화)
│   ├── 4-2. 신규 설치 감소 추이
│   ├── 4-3. 이탈 분석 (이탈자 방향)
│   ├── 4-4. 30일 삭제율 비교
│   └── 4-5. 사용자 프로파일 (페르소나)
│
├── 5. 주제 3 — 신흥 강자 분석 (네이버플러스 스토어)
│   ├── 5-1. MAU 급성장 추이
│   ├── 5-2. 업종 내 점유율 변화
│   ├── 5-3. 경쟁앱 대비 격차 축소
│   ├── 5-4. 30일 삭제율 (유입 질)
│   ├── 5-5. 교차 사용 분석 (쿠팡 사용자 중 병행 비율)
│   ├── 5-6. 교차 사용자 사용 강도 (사용일수·시간)
│   ├── 5-7. 페르소나 비교 (쿠팡 vs 네이버플러스 스토어)
│   └── 5-8. 충성도 비교 (단독 사용률, 고착도)
│
├── 6. 앞으로 주목해야 할 지표
│   ├── 단독 사용률 변화
│   ├── 교차 사용자 사용시간 배율
│   └── 교차 사용률 추이
│
└── 7. 핵심 인사이트 & 시사점
    ├── 시장 지배력 구조
    ├── 도전자 둔화 원인
    ├── 신흥 강자의 차별화 포인트
    └── 향후 경쟁 시나리오
```

---

## 2. 섹션별 데이터 소스 매핑

### 섹션 0: 헤드라인 KPI

원본에서 사용된 수치:
- 쇼핑 업종 MAU 4,278만 (역대 최고)
- 쿠팡 MAU 3,503만 (2위 대비 4.3배)
- 네이버플러스 스토어 YoY +189.9%
- C커머스 성장률 한 자릿수로 둔화

| 데이터 | MI MCP 가능 여부 | 조회 방법 |
|--------|-----------------|-----------|
| 업종 전체 MAU | ✅ | `mcp_mobileindex_usage_trend_traffic` |
| 앱별 MAU | ✅ | `mcp_mobileindex_app_usage` / `mcp_mobileindex_usage_rank` |
| YoY 증감률 | ✅ | 조회 후 직접 계산 |

---

### 섹션 1: 쇼핑 업종 전체 현황

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| 업종 전체 MAU (월별) | ✅ | `mcp_mobileindex_usage_trend_traffic` |
| 업종 사용시간 (월별) | ✅ | `mcp_mobileindex_usage_trend_traffic` |
| 성별·연령별 사용자 구성 | ✅ | `mcp_mobileindex_usage_trend_traffic` (gender/age) |
| 세부 업종별 MAU (오픈마켓/종합쇼핑/해외직구) | ✅ | `mcp_mobileindex_usage_trend_traffic` (appCateSub) |
| 세부 업종별 YoY 증감률 | ✅ | 조회 후 직접 계산 |

---

### 섹션 2: MAU TOP 10 & 경쟁 구도

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| 쇼핑 업종 MAU 순위 TOP 10 | ✅ | `mcp_mobileindex_usage_rank` |
| 앱별 MAU 수치 | ✅ | `mcp_mobileindex_app_usage` |
| 업종 시장 스냅샷 | ✅ | `mcp_mobileindex_market_snapshot` |

---

### 섹션 3: 지배적 플레이어 분석 (쿠팡)

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| 쿠팡 MAU 월별 추이 | ✅ | `mcp_mobileindex_app_usage` |
| 이벤트 전후 MAU 변화 | ✅ | `mcp_mobileindex_app_usage` (기간 지정) |
| 이탈자 규모 | ✅ | `mcp_mobileindex_app_break` |
| 이탈 방향 (업종 이탈 vs 경쟁앱 이동) | ✅ | `mcp_mobileindex_app_break` |
| 개인정보 유출 사건 배경 | 📝 사용자 직접 입력 | 뉴스/보도자료 |
| 결제 데이터 (금액·건수) | ❌ 미지원 | 소비인덱스 (별도 서비스) |

---

### 섹션 4: C커머스 분석 (Temu, 알리익스프레스)

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| Temu/알리 MAU 추이 | ✅ | `mcp_mobileindex_app_usage` |
| 신규 설치 추이 | ✅ | `mcp_mobileindex_app_usage` (uType="install") |
| 이탈 분석 | ✅ | `mcp_mobileindex_app_break` |
| 30일 삭제율 | ✅ | `mcp_mobileindex_competitor_install_delete` |
| 사용자 프로파일 (성별·연령) | ✅ | `mcp_mobileindex_app_demographic` |
| 페르소나 | ✅ | `mcp_mobileindex_app_persona` |
| 규제 환경 변화 배경 | 📝 사용자 직접 입력 | 뉴스/보도자료 |

---

### 섹션 5: 신흥 강자 분석 (네이버플러스 스토어)

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| MAU 급성장 추이 | ✅ | `mcp_mobileindex_app_usage` |
| 업종 내 점유율 변화 | ✅ | `mcp_mobileindex_app_biz_rate` |
| 경쟁앱 대비 격차 (11번가 등) | ✅ | `mcp_mobileindex_app_usage` (비교) |
| 30일 삭제율 | ✅ | `mcp_mobileindex_competitor_install_delete` |
| 교차 사용 분석 | ✅ | `mcp_mobileindex_usage_overlap_rank` |
| 교차 사용자 사용 강도 | ✅ | `mcp_mobileindex_app_concurrent` |
| 페르소나 비교 | ✅ | `mcp_mobileindex_app_persona` |
| 관심 업종 비교 | ✅ | `mcp_mobileindex_app_interest` |
| 충성도 (단독 사용률, 고착도) | ✅ | `mcp_mobileindex_competitor_loyalty` |
| 신규 설치 추이 | ✅ | `mcp_mobileindex_app_usage` (uType="install") |

---

### 섹션 6: 주목 지표

| 데이터 | MI MCP 가능 여부 | 사용할 도구 |
|--------|-----------------|------------|
| 단독 사용률 추이 | ✅ | `mcp_mobileindex_competitor_loyalty` (기간별) |
| 교차 사용률 추이 | ✅ | `mcp_mobileindex_usage_overlap_rank` (기간별) |
| 사용시간 배율 변화 | ✅ | `mcp_mobileindex_app_usage` (두 앱 비교) |

---

## 3. 인사이트 구조 패턴

원본 리포트의 인사이트를 패턴으로 분류:

| # | 인사이트 유형 | 패턴 | 필요 데이터 |
|---|-------------|------|------------|
| 1 | 시장 지배력 구조 | "이벤트에도 불구하고 X앱이 흔들리지 않는 이유" | MAU 추이 + 이탈 분석 |
| 2 | 이탈 방향 해석 | "이탈자 N만 중 X%가 업종 이탈, Y%만 경쟁앱 이동" | 이탈 분석 |
| 3 | 성장 둔화 진단 | "두 자릿수 성장 → 한 자릿수 둔화, 삭제율 높아 순증 감소" | MAU + 설치 + 삭제율 |
| 4 | 교차 사용 균열 | "1위 앱 사용자 중 X%가 신흥 앱 병행 → 대체가 아닌 보완" | 교차 사용 분석 |
| 5 | 포지셔닝 차별화 | "A앱은 필수소비, B앱은 탐색형 소비 — 페르소나로 증명" | 페르소나 + 관심업종 |
| 6 | 유입 질 비교 | "삭제율 X% vs Y% — 붙잡는 앱 vs 흘리는 앱" | 30일 삭제율 비교 |

---

## 4. 리포트 작성 공식

### 데이터 훅 공식
```
[임팩트 수치] + [시간 프레임] + [의미 해석]
예: "쇼핑 업종 MAU가 4,278만으로 역대 최고치를 경신했습니다"
```

### 경쟁 구도 공식
```
[1위 앱 수치] + [2위 앱 수치] + [배율/격차] = [지배력 해석]
예: "쿠팡 3,503만 vs 11번가 815만 = 4.3배 격차, 독주 지속"
```

### 이탈 분석 공식
```
[이탈자 규모] + [이탈 방향 비율] + [의미 해석]
예: "이탈자 236만 중 90.3% 업종 이탈 → 경쟁앱이 아닌 쇼핑 자체를 안 함"
```

### 교차 사용 공식
```
[교차 사용률 변화] + [사용 강도 변화] + [대체 vs 보완 판단]
예: "교차 사용률 7.0% → 18.7% (+11.7%p), 사용시간 배율 ×3.5 유지 → 보완 관계"
```

### 성장 둔화 공식
```
[과거 성장률] + [현재 성장률] + [삭제율/이탈률] = [구조적 한계 해석]
예: "두 자릿수 → 한 자릿수, 삭제율 75.1% → 순증 사용자 감소 구조"
```

---

## 5. 톤앤매너 특징

| 요소 | 특징 |
|------|------|
| 문체 | 짧은 문장, 한 문장에 하나의 정보. 구어체 섞어 읽기 쉽게 |
| 수치 표현 | 구체적 (약 X만 → X만Y천), 배율·비율 적극 활용 |
| 비교 | "X vs Y" 프레임, 배율(4.3배), 비율(%) 병행 |
| 해석 | 데이터 나열 후 "~라는 뜻입니다", "~인 셈입니다"로 의미 부여 |
| 스토리텔링 | 주제별로 "흔들렸지만 돌아왔다", "기세가 꺾였다", "균열을 내다" 등 서사 구조 |
| 시각 자료 | 각 데이터 포인트마다 차트/그래프 이미지 삽입 |
| 전환 | 섹션 간 "이 이야기는 세 번째 주제에서 이어가겠습니다" 식 연결 |

---

## 6. 리포트 분량 기준

| 항목 | 기준 |
|------|------|
| 전체 분량 | 4,000~6,000자 |
| 대주제 수 | 3~4개 (시장 전체 + 주요 플레이어별) |
| 데이터 포인트 | 주제당 4~6개 |
| 차트/이미지 | 주제당 2~3개 |
| 외부 맥락 | 1~2개 (시장 이벤트, 규제 변화) |

---

## 7. 추후 연동 예정 데이터 목록

| 데이터 | 필요 이유 | 가능한 소스 |
|--------|---------|------------|
| 결제 데이터 (금액·건수) | 실제 거래 규모 파악 | 모바일인덱스 소비인덱스 |
| 가격대별 결제 분포 | 플랫폼별 소비 구조 비교 | 모바일인덱스 소비인덱스 |
| 카테고리별 매출 비중 | 플랫폼 강점 카테고리 분석 | 모바일인덱스 소비인덱스 |
| 배송 만족도/리뷰 데이터 | 서비스 품질 비교 | 외부 리뷰 크롤링 |
| 규제 환경 변화 | C커머스 둔화 배경 설명 | 뉴스 크롤링 |
# MI MCP 데이터 조회 가이드 & 커머스 리포트 데이터 매핑

> 이 문서는 커머스 업종 리포트를 생성하기 위해 MI MCP의 **실제 도구명과 파라미터**를 기준으로 어떤 데이터를 어떻게 조회해야 하는지 정리한 가이드입니다.
> MCP 도구 목록 확인 기준: 2026-05-28 (총 32개 도구 / 서버: mcp-data-live.mobileindex.com)

---

## 조회 순서 개요

```
STEP 0: 사전 준비 — 업종 코드 & 앱 패키지명 확인
STEP 1: 쇼핑 업종 전체 트렌드 조회
STEP 2: 세부 업종별 트렌드 (오픈마켓/종합쇼핑/해외직구)
STEP 3: MAU TOP 10 & 앱별 경쟁 구도
STEP 4: 핵심 플레이어 심화 분석 (쿠팡/네이버플러스 스토어/C커머스)
STEP 5: 교차 사용 & 이탈 분석
STEP 6: 데이터 가공 및 인사이트 생성
```

---

## STEP 0: 사전 준비 — 업종 코드 & 앱 패키지명 확인

### 사용 도구

```
mcp_mobileindex_get_categories_main   → 업종 대분류 코드 목록 조회
mcp_mobileindex_get_categories_sub    → 업종 소분류 코드 목록 조회
  필수 파라미터: appCateMain (대분류 코드)

mcp_mobileindex_search_app            → 앱 패키지명 조회 (앱명으로 검색)
  필수 파라미터: keyword (앱명 또는 패키지명, 2글자 이상)
```

### 예시

```
1. mcp_mobileindex_get_categories_main → "쇼핑" 대분류 코드 확인
2. mcp_mobileindex_get_categories_sub(appCateMain="쇼핑코드") → "오픈마켓", "종합쇼핑/홈쇼핑", "해외직구" 소분류 코드 확인
3. mcp_mobileindex_search_app(keyword="쿠팡") → 패키지명 확인
```

### 리포트에 등장하는 앱 검색 (pkgName 확보)

```
mcp_mobileindex_search_app(keyword="쿠팡")           → 쿠팡
mcp_mobileindex_search_app(keyword="11번가")          → 11번가
mcp_mobileindex_search_app(keyword="네이버플러스")     → 네이버플러스 스토어
mcp_mobileindex_search_app(keyword="알리익스프레스")   → 알리익스프레스
mcp_mobileindex_search_app(keyword="Temu")           → Temu (테무)
mcp_mobileindex_search_app(keyword="다이소")          → 다이소몰
mcp_mobileindex_search_app(keyword="SSG")            → SSG.COM
mcp_mobileindex_search_app(keyword="올리브영")        → 올리브영
mcp_mobileindex_search_app(keyword="무신사")          → 무신사
mcp_mobileindex_search_app(keyword="컬리")           → 마켓컬리
```

---

## STEP 1: 쇼핑 업종 전체 트렌드 조회

### 목적
쇼핑 업종 전체 MAU, 사용시간 월별 추이 파악 (역대 최고치 갱신 여부)

### 사용 도구: `mcp_mobileindex_usage_trend_traffic`

```
필수 파라미터:
  tType:     "user" | "time" | "install"
  dateType:  "m"
  startDate: "20250301"
  endDate:   "20260331"

선택 파라미터:
  appCateSub: [소분류 코드]    ← 미입력 시 쇼핑 전체
  os:         "total"
```

### 조회 목록

| 호출 | tType | appCateSub | 목적 |
|------|-------|----------|------|
| 1 | user | 쇼핑 전체 | 쇼핑 업종 MAU 추이 |
| 2 | time | 쇼핑 전체 | 쇼핑 업종 사용시간 추이 |
| 3 | install | 쇼핑 전체 | 쇼핑 업종 신규 설치 추이 |

### 기대 출력 형태
```
| 연월    | 쇼핑 MAU   | 사용시간      | 신규설치 |
|---------|-----------|-------------|---------|
| 2025-03 | 4,007만   | 1.83억시간   | —       |
| ...     | ...       | ...         | ...     |
| 2026-03 | 4,278만   | 1.95억시간   | —       |
```

---

## STEP 2: 세부 업종별 트렌드

### 목적
오픈마켓 / 종합쇼핑·홈쇼핑 / 해외직구 각각의 성장률 비교

### 사용 도구: `mcp_mobileindex_usage_trend_traffic`

### 조회 목록

| 호출 | tType | appCateSub | 목적 |
|------|-------|----------|------|
| 4 | user | 오픈마켓 코드 | 오픈마켓 MAU 추이 |
| 5 | user | 종합쇼핑/홈쇼핑 코드 | 종합쇼핑 MAU 추이 |
| 6 | user | 해외직구 코드 | 해외직구 MAU 추이 |

> 각 세부 업종의 YoY 증감률을 계산하여 "온도 차" 분석

---

## STEP 3: MAU TOP 10 & 앱별 경쟁 구도

### 3-A. 업종 내 앱 MAU 순위

**사용 도구**: `mcp_mobileindex_usage_rank`

```
필수 파라미터:
  uType:    "user"
  dateType: "m"
  date:     "20260301"
  appCateMain: [쇼핑 대분류 코드]

선택:
  startRank: "1"
  endRank: "10"
```

### 3-B. 업종 시장 스냅샷 (권장 — 호출 수 절감)

**사용 도구**: `mcp_mobileindex_market_snapshot`

```
mcp_mobileindex_market_snapshot(appCateMain=[쇼핑코드], dateType="m", date="20260301")
  → Top 10 앱(사용자 수+사용시간) + 트래픽 트렌드 + 급상승 앱 한 번에 반환
```

### 3-C. 개별 앱 MAU 추이 (주요 앱)

**사용 도구**: `mcp_mobileindex_app_usage`

```
mcp_mobileindex_app_usage(uType="user", pkgName=[패키지명], dateType="m", startDate="20250301", endDate="20260331")
```

주요 조회 대상:
- 쿠팡, 11번가, 네이버플러스 스토어, 알리익스프레스, Temu, 다이소몰

### 기대 출력 형태
```
| 순위 | 앱명              | MAU (3월)  | YoY 증감  |
|------|------------------|-----------|----------|
| 1    | 쿠팡              | 3,503만   | +X%      |
| 2    | 11번가            | 815만     | +X%      |
| 3    | 네이버플러스 스토어  | 777만     | +189.9%  |
| ...  | ...              | ...       | ...      |
```

---

## STEP 4: 핵심 플레이어 심화 분석

### 4-A. 쿠팡 심화

**사용 도구 조합:**

```
[MAU 추이] mcp_mobileindex_app_usage(uType="user", pkgName="쿠팡패키지", dateType="m", ...)
[사용시간] mcp_mobileindex_app_usage(uType="time", pkgName="쿠팡패키지", dateType="m", ...)
[이탈 분석] mcp_mobileindex_app_break(pkgName="쿠팡패키지", dateType="m", date="20260301")
[인구통계] mcp_mobileindex_app_demographic(pkgName="쿠팡패키지", dateType="m", ..., uType="user")
[건강도] mcp_mobileindex_app_health_check(pkgName="쿠팡패키지", dateType="m", ...)
```

### 4-B. C커머스 심화 (Temu + 알리익스프레스)

**사용 도구 조합 (앱별 각각 호출):**

```
[MAU 추이] mcp_mobileindex_app_usage(uType="user", pkgName="테무패키지", ...)
[신규설치] mcp_mobileindex_app_usage(uType="install", pkgName="테무패키지", ...)
[이탈 분석] mcp_mobileindex_app_break(pkgName="테무패키지", dateType="m", date="20260301")
[삭제율] mcp_mobileindex_competitor_install_delete(pkgName="테무패키지", startDate="20260301", endDate="20260331")
  ⚠️ pkgName에 1개 앱만 입력!
[인구통계] mcp_mobileindex_app_demographic(pkgName="테무패키지", ...)
[페르소나] mcp_mobileindex_app_persona(pkgName="테무패키지", date="20260301")
```

### 4-C. 네이버플러스 스토어 심화

**사용 도구 조합:**

```
[MAU 추이] mcp_mobileindex_app_usage(uType="user", pkgName="네이버플러스패키지", ...)
[신규설치] mcp_mobileindex_app_usage(uType="install", pkgName="네이버플러스패키지", ...)
[점유율] mcp_mobileindex_app_biz_rate(pkgName="네이버플러스패키지", dateType="m", ..., bizCateType="sub", rType="user")
[삭제율] mcp_mobileindex_competitor_install_delete(pkgName="네이버플러스패키지", ...)
[충성도] mcp_mobileindex_competitor_loyalty(pkgName="네이버플러스패키지", date="20260301")
  ⚠️ pkgName에 1개 앱만 입력!
[페르소나] mcp_mobileindex_app_persona(pkgName="네이버플러스패키지", date="20260301")
[관심업종] mcp_mobileindex_app_interest(pkgName="네이버플러스패키지", date="20260301")
```

---

## STEP 5: 교차 사용 & 이탈 분석

### 5-A. 교차 사용 분석

**사용 도구**: `mcp_mobileindex_usage_overlap_rank`

```
mcp_mobileindex_usage_overlap_rank(dateType="m", date="20260301", pkgName="쿠팡패키지")
  ⚠️ dateType: "w" | "m" 만 지원 (일간 불가)
  → 쿠팡 사용자가 동시에 사용하는 앱 순위
  → 네이버플러스 스토어의 교차 사용률 확인
```

**1년 전 비교 조회:**
```
mcp_mobileindex_usage_overlap_rank(dateType="m", date="20250301", pkgName="쿠팡패키지")
  → 1년 전 교차 사용률과 비교하여 변화폭 산출
```

### 5-B. 이탈 분석

**사용 도구**: `mcp_mobileindex_app_break`

```
mcp_mobileindex_app_break(pkgName="쿠팡패키지", dateType="m", date="20260301")
  → 쿠팡 이탈자 규모 + 이탈 방향 (업종 이탈 vs 경쟁앱 이동)

mcp_mobileindex_app_break(pkgName="테무패키지", dateType="m", date="20260301")
  → Temu 이탈자 규모 + 이탈 방향
```

### 5-C. 경쟁앱 종합 비교

**사용 도구**: `mcp_mobileindex_compare_competitors`

```
mcp_mobileindex_compare_competitors(
  pkgNames="쿠팡패키지,네이버플러스패키지,11번가패키지,테무패키지,알리패키지",
  date="202603",
  startDate="20260224",
  endDate="20260302"
)
  → 충성도·리텐션·삭제율 비교표 한 번에 반환
  ⚠️ 2~5개 앱만 가능
```

### 5-D. 페르소나 비교 (쿠팡 vs 네이버플러스 스토어)

**사용 도구**: `mcp_mobileindex_app_persona` + `mcp_mobileindex_app_interest`

```
mcp_mobileindex_app_persona(pkgName="쿠팡패키지", date="20260301")
mcp_mobileindex_app_persona(pkgName="네이버플러스패키지", date="20260301")
  → 두 앱 사용자 페르소나 비교 (쇼퍼홀릭, 패셔니스타 등)

mcp_mobileindex_app_interest(pkgName="쿠팡패키지", date="20260301")
mcp_mobileindex_app_interest(pkgName="네이버플러스패키지", date="20260301")
  → 관심 업종 비교 (식음료, 패션/의류, 미용 등)
```

### 기대 출력 형태 (교차 사용 섹션)
```
| 지표                    | 2025-03 | 2026-03 | 변화     |
|------------------------|---------|---------|---------|
| 쿠팡→네이버플러스 교차율  | 7.0%    | 18.7%   | +11.7%p |
| 교차 사용자 수           | 230만   | 657만   | ×2.9    |
| 교차 사용자 사용일수      | 4.4일   | 8.9일   | ×2.0    |
| 교차 사용자 사용시간      | 0.65h   | 0.94h   | +45%    |
```

---

## STEP 6: 데이터 가공 (에이전트 직접 계산)

| 계산 지표 | 공식 | 사용 위치 |
|---------|------|---------|
| YoY 증감률 | (현재 - 1년전) / 1년전 × 100 | 헤드라인 KPI, 업종별 성장률 |
| MoM 증감 | 현재 - 전월 | 이벤트 전후 분석 |
| 배율 격차 | 1위 수치 / 2위 수치 | 경쟁 구도 (4.3배 등) |
| 교차 사용률 변화 | 현재 비율 - 1년전 비율 | 교차 사용 분석 |
| 삭제율 비교 | 앱별 30일 삭제율 나열 | 유입 질 비교 |
| 이탈 방향 비율 | 업종이탈 / 전체이탈 × 100 | 이탈 분석 |
| 1인당 사용시간 | 총 사용시간 / MAU | 사용 강도 변화 |

---

## 데이터 미확보 시 처리

```
[처리 원칙]
1. "⚠️ 직접 조회 불가" 표기 후 대체 지표 제시
   예: "결제 데이터" → "사용시간·사용일수로 활동 강도 대체"
2. 외부 데이터(규제 변화, 사건 배경)는 "📝 사용자 입력 또는 웹 검색" 표기
3. 사용자에게 수동 입력 요청:
   "쿠팡 개인정보 유출 시점(날짜)을 알려주시면 해당 시점의 앱 데이터와 연결하겠습니다"
```

---

## MCP 도구별 호출 요약

| MCP 도구 | 호출 횟수 | 용도 |
|----------|:---------:|------|
| `mcp_mobileindex_search_app` | 8~10회 | 앱 pkgName 조회 |
| `mcp_mobileindex_usage_trend_traffic` | 6회 | 업종 전체 + 세부 업종 MAU/사용시간/설치 추이 |
| `mcp_mobileindex_app_usage` | 12~15회 | 개별 앱 MAU/사용시간/설치 추이 |
| `mcp_mobileindex_usage_rank` | 2~3회 | 업종 내 순위 |
| `mcp_mobileindex_market_snapshot` | 1회 | 업종 시장 스냅샷 |
| `mcp_mobileindex_app_break` | 3~4회 | 이탈 분석 (쿠팡, Temu, 알리 등) |
| `mcp_mobileindex_competitor_install_delete` | 4~5회 | 30일 삭제율 (앱별 각각) |
| `mcp_mobileindex_competitor_loyalty` | 3~4회 | 충성도 (앱별 각각) |
| `mcp_mobileindex_compare_competitors` | 1~2회 | 경쟁앱 종합 비교 |
| `mcp_mobileindex_usage_overlap_rank` | 2~3회 | 교차 사용 분석 |
| `mcp_mobileindex_app_persona` | 3~4회 | 페르소나 분석 |
| `mcp_mobileindex_app_interest` | 2~3회 | 관심 업종 분석 |
| `mcp_mobileindex_app_demographic` | 3~4회 | 인구통계 분석 |
| `mcp_mobileindex_app_biz_rate` | 2~3회 | 업종 내 점유율 |
| `mcp_mobileindex_app_health_check` | 2~3회 | 앱 건강도 진단 |
| `mcp_mobileindex_industry_analysis` | 1회 | 이커머스 업종 심화 분석 |

---

## 데이터 커버리지

```
전체 데이터 포인트: 22개
├── ✅ MCP로 자동 조회 가능: 20개 (91%)
└── ⚠️ 추후 연동 예정/외부 데이터: 2개 (9%)
    ├── 결제 데이터 (소비인덱스)
    └── 카테고리별 매출 비중

* 시장 이벤트 배경(개인정보 유출, 규제 변화)은 웹 검색 도구로 보완 가능
```

---

## 데이터 조회 순서 (권장)

리포트 생성 시 아래 순서로 MCP를 호출하면 효율적:

```
Step 0: 앱 검색 (pkgName 확보)
  → mcp_mobileindex_search_app × 8~10
  → mcp_mobileindex_get_categories_main × 1
  → mcp_mobileindex_get_categories_sub × 1

Step 1: 업종 전체 + 세부 업종 트렌드 (매크로)
  → mcp_mobileindex_usage_trend_traffic × 6
    (쇼핑 전체: user, time, install / 세부: 오픈마켓, 종합쇼핑, 해외직구 user)

Step 2: MAU TOP 10 + 시장 스냅샷
  → mcp_mobileindex_market_snapshot × 1
  → mcp_mobileindex_usage_rank × 1

Step 3: 핵심 앱별 추이
  → mcp_mobileindex_app_usage × 12~15
    (쿠팡, 11번가, 네이버플러스, Temu, 알리, 다이소 등 × user/time/install)

Step 4: 이탈 + 삭제율 + 충성도
  → mcp_mobileindex_app_break × 3~4
  → mcp_mobileindex_competitor_install_delete × 4~5
  → mcp_mobileindex_competitor_loyalty × 3~4
  → mcp_mobileindex_compare_competitors × 1~2

Step 5: 교차 사용 + 페르소나
  → mcp_mobileindex_usage_overlap_rank × 2~3
  → mcp_mobileindex_app_persona × 3~4
  → mcp_mobileindex_app_interest × 2~3

Step 6 (선택): 심화 분석
  → mcp_mobileindex_app_biz_rate × 2~3 (점유율)
  → mcp_mobileindex_app_health_check × 2~3 (건강도)
  → mcp_mobileindex_industry_analysis × 1 (ecommerce)
  → mcp_mobileindex_app_demographic × 3~4 (인구통계)

총 MCP 호출: 약 50~65회
예상 크레딧 소모: 50~65 크레딧 (BASIC 일일 300 기준 충분)
```

---

## 추후 연동 예정 데이터 상세

| 데이터 | 현재 대안 | 연동 시 기대 효과 |
|--------|-----------|------------------|
| 결제 데이터 (금액·건수) | 사용시간·사용일수로 활동 강도 대체 | 실제 거래 규모 기반 분석 |
| 가격대별 결제 분포 | 페르소나 데이터로 소비 성향 간접 추정 | 플랫폼별 소비 구조 직접 비교 |
| 카테고리별 매출 비중 | 관심 업종 데이터로 간접 추정 | 플랫폼 강점 카테고리 정량 분석 |
| 배송 만족도 | 재방문율·충성도로 간접 추정 | 서비스 품질 직접 비교 |
# 커머스 업종 시장 분석 리포트 스킬

> 이 파일을 에이전트 컨텍스트에 로드하고 MI MCP가 연결된 상태에서 실행하면,
> 커머스/쇼핑 업종의 다양한 분석 리포트를 자동 생성할 수 있습니다.
>
> **설계 원칙: 모듈형 분석**
> - 이 스킬셋은 "고정 템플릿"이 아니라 "분석 모듈 라이브러리"입니다
> - 사용자의 질문에 따라 관련 모듈을 선택·조합하여 리포트를 구성합니다
> - 어떤 앱이든, 어떤 분석 관점이든 동일한 품질로 대응 가능합니다
>
> **MCP 도구 기반 커버리지: 약 90%**
> - ✅ 커버: MAU·사용시간·신규설치, 성별·연령별, 순위, 충성도·이탈·교차사용·페르소나
> - ❌ 미지원: 결제 데이터(소비인덱스) — 사용시간·충성도로 대체
> - ⚠️ 외부: 시장 이벤트 배경(개인정보 유출, 규제 변화 등)

---

## 스킬 정의

**스킬명**: `commerce-market-report`
**사용 조건**: MI MCP(`mobileindex`) 연결 필수
**대상 사용자**: 이커머스 업종 종사자 (플랫폼사, 브랜드, 대행사 등)

---

## 에이전트 시스템 프롬프트

아래 내용을 에이전트의 시스템 프롬프트 또는 컨텍스트로 로드하세요.

---

```
[커머스 업종 시장 분석 — 모듈형 리포트 생성 스킬]

당신은 모바일인덱스 MCP 데이터를 활용하여 커머스/쇼핑 업종 분석 리포트를 생성하는 전문 에이전트입니다.

## 핵심 원칙

1. 모든 수치는 MI MCP에서 실시간 조회한 실측 데이터를 사용한다
2. 수치를 제시할 때는 반드시 기준 연월을 명시한다
3. 인사이트는 데이터에서 직접 도출하고, 추측은 명확히 구분한다
4. MI MCP에 없는 데이터는 "⚠️ 추후 연동 예정"으로 표기한다
5. **사용자의 질문 의도에 맞는 모듈을 선택·조합하여 리포트를 구성한다**
6. 고정된 섹션 순서를 따르지 않는다 — 분석 목적에 맞게 구조를 설계한다

---

## 분석 모듈 라이브러리

사용자의 질문에 따라 아래 모듈 중 3~6개를 선택하고, 분석 목적에 맞는 순서로 배치한다.

---

### 모듈 A: 업종 트렌드 분석
**언제 사용**: 시장 전체 흐름을 파악할 때, 업종 성장/둔화를 확인할 때
**조회 도구**:
- `mcp_mobileindex_usage_trend_traffic`(tType="user"/"time"/"install", dateType="m", appCateSub=[업종코드])
- `mcp_mobileindex_industry_analysis`(industry="ecommerce", dateType="m"/"w")

**출력 형태**:
- 월별 MAU / 사용시간 / 신규설치 추이 표
- YoY 증감률, 계절성 패턴 해석
- 1인당 사용 강도 변화 (총 사용시간 ÷ MAU)

**업종 세분화 가능**: 오픈마켓, 종합쇼핑/홈쇼핑, 해외직구, 소셜커머스 등 소분류별 조회

---

### 모듈 B: 앱 성장 추이 분석
**언제 사용**: 특정 앱의 성장/하락을 추적할 때
**조회 도구**:
- `mcp_mobileindex_app_usage`(uType="user"/"time"/"install", pkgName, dateType="m")
- `mcp_mobileindex_app_summary`(pkgName)

**출력 형태**:
- 앱별 MAU / 사용시간 / 신규설치 월별 추이
- YoY·MoM 증감률
- 성장 구간 / 정체 구간 / 하락 구간 식별
- 이벤트 전후 변화 포착 (특정 시점 전후 비교)

---

### 모듈 C: 경쟁 구도 분석
**언제 사용**: 앱 간 순위·격차를 비교할 때, 시장 지배력을 파악할 때
**조회 도구**:
- `mcp_mobileindex_usage_rank`(uType="user"/"time", dateType="m", appCateMain/Sub)
- `mcp_mobileindex_compare_competitors`(pkgNames="앱A,앱B,앱C", date) ← 2~5개
- `mcp_mobileindex_market_snapshot`(appCateMain, dateType="m"/"w")

**출력 형태**:
- MAU 순위 TOP N 표
- 1위 vs 2위 배율 격차
- 충성도·리텐션·삭제율 비교표
- MAU 순위 vs 사용시간 순위 차이 해석

**주의**: `compare_competitors`는 2~5개 앱만 가능

---

### 모듈 D: 교차 사용 분석
**언제 사용**: 앱 간 사용자 겹침/병행 패턴을 볼 때, 대체 vs 보완 관계를 판단할 때
**조회 도구**:
- `mcp_mobileindex_usage_overlap_rank`(pkgName, dateType="m"/"w", date)
- `mcp_mobileindex_app_concurrent`(pkgName, date)

**출력 형태**:
- 대상 앱 사용자가 함께 쓰는 앱 TOP 5~10
- 교차 사용률 (현재 vs 1년 전 비교 시 변화폭)
- 교차 사용자 사용 강도 (사용일수, 사용시간)
- "대체 vs 보완" 판단 기준: 사용시간 배율

**주의**: dateType "w" 또는 "m"만 지원 (일간 불가)

---

### 모듈 E: 이탈 & 삭제율 분석
**언제 사용**: 사용자 유출 패턴을 볼 때, 유입 질을 비교할 때
**조회 도구**:
- `mcp_mobileindex_app_break`(pkgName, dateType="m", date)
- `mcp_mobileindex_competitor_install_delete`(pkgName, startDate, endDate)
  ⚠️ pkgName에 1개 앱만 입력! 복수 앱은 각각 호출

**출력 형태**:
- 이탈자 규모 (N만 명)
- 이탈 방향 비율: 업종 이탈 X% vs 경쟁앱 이동 Y%
- 30일 삭제율 앱별 비교
- "왜 떠나는가" 해석 (경쟁앱이 좋아서 vs 니즈 소멸)

---

### 모듈 F: 사용자 프로파일 & 페르소나 분석
**언제 사용**: 앱 사용자가 누구인지 파악할 때, 앱 간 사용자 성격 차이를 볼 때
**조회 도구**:
- `mcp_mobileindex_app_demographic`(pkgName, dateType="m", uType="user"/"time")
- `mcp_mobileindex_app_persona`(pkgName, date)
- `mcp_mobileindex_app_interest`(pkgName, date)

**출력 형태**:
- 성별·연령별 사용자 구성 비율
- 페르소나 키워드 (쇼퍼홀릭, 패셔니스타, 건강관리 등)
- 관심 업종 분포 (식음료, 패션, 미용 등)
- 앱 간 페르소나 비교 시: 배율로 차이 표현

---

### 모듈 G: 세그먼트 변화 분석
**언제 사용**: 어떤 사용자층이 가장 크게 변했는지 볼 때
**조회 도구**:
- `mcp_mobileindex_usage_trend_traffic`(gender/age 파라미터 활용)
- `mcp_mobileindex_app_demographic`(pkgName, dateType="m", 기간 비교)

**출력 형태**:
- 성별×연령별 증감 표 (절대량 + 증감률)
- 증가/감소 Top 3 세그먼트 식별
- 세그먼트 변화의 의미 해석

**조회 팁**: 먼저 gender="total"로 연령대별 조회(6회) → 주요 연령대만 성별 분리(2~4회)

---

### 모듈 H: 앱 건강도 종합 진단
**언제 사용**: 특정 앱의 전반적 상태를 빠르게 파악할 때
**조회 도구**:
- `mcp_mobileindex_app_health_check`(pkgName, dateType="m"/"w", startDate, endDate)

**출력 형태**:
- 사용자 수 추이 + 사용시간 + 인구통계 + 이탈률 + 동시사용 앱 수
- 종합 건강도 판단 (성장/안정/하락)

---

### 모듈 I: 업종 내 점유율 분석
**언제 사용**: 특정 앱의 시장 점유율 변화를 추적할 때
**조회 도구**:
- `mcp_mobileindex_app_biz_rate`(pkgName, dateType="m", bizCateType="sub", rType="user"/"time")
- `mcp_mobileindex_app_ranking_history`(pkgName, dateType="m", rType="user"/"time")

**출력 형태**:
- 점유율 추이 (월별 %)
- 순위 변동 히스토리
- 점유율 상승/하락 구간과 원인 연결

---

### 모듈 J: 충성도 & 리텐션 분석
**언제 사용**: 사용자 고착도, 재방문 패턴을 볼 때
**조회 도구**:
- `mcp_mobileindex_competitor_loyalty`(pkgName, date)
  ⚠️ pkgName에 1개 앱만 입력!
- `mcp_mobileindex_competitor_retention`(pkgName, startDate, endDate)
  ⚠️ 주간 데이터만 지원 (startDate=월요일, endDate=일요일)

**출력 형태**:
- 충성도 지수, 단독 사용률, 고착도(DAU/MAU)
- 재방문율 (주간 기준)
- 앱 간 비교 시: "단독 사용률 X% vs Y%" 프레임

---

## 모듈 조합 규칙

### 1. 사용자 질문 분석 → 모듈 선택

| 질문 유형 | 권장 모듈 조합 | 예시 |
|----------|--------------|------|
| "업종 전체 트렌드" | A + C + G | "쇼핑 업종 최근 1년 변화 분석해줘" |
| "특정 앱 분석" | B + H + F + J | "쿠팡 건강도 체크해줘" |
| "앱 간 비교" | C + D + F + J | "쿠팡 vs 네이버플러스 비교해줘" |
| "성장/둔화 원인" | B + E + G + F | "Temu 성장이 꺾인 이유 분석해줘" |
| "교차 사용 패턴" | D + F + J | "쿠팡 사용자가 함께 쓰는 앱 분석" |
| "이탈 분석" | E + D + B | "쿠팡 이탈자가 어디로 가는지" |
| "시장 점유율 변화" | I + B + C | "네이버플러스 스토어 점유율 변화" |
| "업종 심층 리포트" | A + C + B + E + D + F | "2026년 상반기 쇼핑 시장 심층 분석" |

### 2. 리포트 구성 원칙

- **도입**: 핵심 KPI 3~4개로 요약 (항상 포함)
- **본문**: 선택된 모듈을 "큰 그림 → 세부" 순서로 배치
- **마무리**: 데이터 기반 인사이트 + 주목 지표 제시 (항상 포함)

### 3. 인사이트 도출 패턴

데이터를 조합하여 아래 패턴 중 해당되는 것을 자동 도출:

| 패턴 | 공식 | 예시 |
|------|------|------|
| 지배력 구조 | 이벤트 충격 + 빠른 회복 = 구조적 강점 | "개인정보 유출에도 2개월 만에 반등" |
| 성장 둔화 | 과거 성장률 > 현재 + 높은 삭제율 = 순증 감소 | "두 자릿수→한 자릿수, 삭제율 75%" |
| 교차 균열 | 교차율 상승 + 사용강도 유지 = 보완 관계 | "교차율 7%→18.7%, 배율 ×3.5 유지" |
| 포지셔닝 차별화 | 페르소나 A ≠ 페르소나 B = 다른 역할 | "필수소비 vs 탐색형 소비" |
| 이탈 방향 | 업종이탈 >> 경쟁이동 = 니즈 소멸 | "이탈자 90%가 업종 자체를 떠남" |
| 활동 강도 변화 | MAU 증감률 ≠ 사용시간 증감률 = 행동 변화 | "MAU +7% vs 사용시간 +15% = 몰입 증가" |

---

## 사전 준비 (모든 분석 공통)

### STEP 0: 업종 코드 & 앱 패키지명 확보

```
mcp_mobileindex_get_categories_main → 쇼핑 대분류 코드
mcp_mobileindex_get_categories_sub(appCateMain=[코드]) → 소분류 코드
mcp_mobileindex_search_app(keyword=[앱명]) → pkgName 확보
```

### 주요 커머스 앱 검색 키워드

| 앱명 | 검색 키워드 |
|------|-----------|
| 쿠팡 | "쿠팡" |
| 11번가 | "11번가" |
| 네이버플러스 스토어 | "네이버플러스" |
| 알리익스프레스 | "알리익스프레스" |
| Temu | "Temu" |
| 다이소몰 | "다이소" |
| SSG.COM | "SSG" |
| 올리브영 | "올리브영" |
| 무신사 | "무신사" |
| 컬리 | "컬리" |
| 오늘의집 | "오늘의집" |
| 에이블리 | "에이블리" |
| 지그재그 | "지그재그" |
| 당근마켓 | "당근" |

---

## MCP 도구 주의사항 (필독)

| 도구 | 주의사항 |
|------|---------|
| `competitor_loyalty` | pkgName에 1개 앱만 입력 (복수 시 빈 배열) |
| `competitor_retention` | 주간 데이터만 지원 (startDate=월요일, endDate=일요일) |
| `competitor_install_delete` | pkgName에 1개 앱만 입력 |
| `usage_overlap_rank` | dateType "w" 또는 "m"만 지원 (일간 불가) |
| `market_snapshot` | dateType "w" 또는 "m"만 지원 |
| `app_health_check` | dateType "w" 또는 "m"만 지원 |
| `industry_analysis` | industry="ecommerce" 사용 |
| `compare_competitors` | 2~5개 앱만 가능 |

---

## 톤앤매너

- 짧은 문장, 한 문장에 하나의 정보
- 수치는 구체적으로 (약 X만 → X만Y천)
- 배율·비율 적극 활용 ("4.3배 격차", "+11.7%p")
- 데이터 나열 후 반드시 해석 ("~라는 뜻입니다", "~인 셈입니다")
- 모든 수치에 기준 연월 명시
- MI MCP 데이터는 4,500만 DMP 기반 추정치임을 리포트 말미에 명시

---

## 데이터 출처 (리포트 말미에 항상 포함)

| 항목 | 출처 | 비고 |
|------|------|------|
| 앱 MAU, 사용시간, 신규 설치 | 모바일인덱스 INSIGHT | MI MCP 실시간 조회 |
| 성별·연령별, 페르소나, 관심업종 | 모바일인덱스 INSIGHT | MI MCP 실시간 조회 |
| 이탈, 교차사용, 충성도, 삭제율 | 모바일인덱스 INSIGHT | MI MCP 실시간 조회 |
| 결제 데이터 | ⚠️ 추후 연동 예정 | 소비인덱스 (별도) |
| 시장 이벤트 배경 | 📝 사용자 입력 또는 웹 검색 | — |
```

---

## 예시 조합 레시피

### 레시피 1: 업종 심층 리포트 (원본 리포트 스타일)
```
사용자: "2026년 상반기 모바일 쇼핑 앱 시장 분석 리포트 만들어줘"

모듈 조합: A → C → B+E (쿠팡) → B+E (C커머스) → B+D+F (네이버플러스) → 인사이트
구조:
  1. 쇼핑 업종 전체 현황 [모듈 A]
  2. MAU TOP 10 & 경쟁 구도 [모듈 C]
  3. 쿠팡 — 흔들렸지만 돌아왔다 [모듈 B + E]
  4. C커머스 — 기세가 꺾였다 [모듈 B + E]
  5. 네이버플러스 스토어 — 균열을 내다 [모듈 B + D + F]
  6. 앞으로 주목할 지표 + 인사이트
```

### 레시피 2: 단일 앱 건강도 체크
```
사용자: "무신사 앱 현재 상태 분석해줘"

모듈 조합: H → B → F → I
구조:
  1. 무신사 건강도 종합 [모듈 H]
  2. MAU·사용시간 추이 [모듈 B]
  3. 사용자 프로파일 [모듈 F]
  4. 업종 내 점유율 [모듈 I]
```

### 레시피 3: 앱 간 비교 분석
```
사용자: "쿠팡 vs 네이버플러스 스토어 비교해줘"

모듈 조합: C → D → F → J
구조:
  1. MAU·사용시간 비교 [모듈 C]
  2. 교차 사용 패턴 [모듈 D]
  3. 페르소나 차이 [모듈 F]
  4. 충성도 비교 [모듈 J]
```

### 레시피 4: 성장 둔화 원인 분석
```
사용자: "Temu 성장이 꺾인 이유를 데이터로 분석해줘"

모듈 조합: B → E → G → F
구조:
  1. MAU·신규설치 추이 — 둔화 확인 [모듈 B]
  2. 이탈 방향 + 삭제율 [모듈 E]
  3. 핵심 세그먼트 변화 [모듈 G]
  4. 사용자 프로파일 특성 [모듈 F]
```

### 레시피 5: 이벤트 임팩트 분석
```
사용자: "쿠팡 개인정보 유출 이후 시장 변화 분석해줘"

모듈 조합: B → E → D → C
구조:
  1. 쿠팡 MAU 이벤트 전후 변화 [모듈 B]
  2. 이탈 규모 + 방향 [모듈 E]
  3. 경쟁앱 교차 사용 변화 [모듈 D]
  4. 경쟁 구도 변화 [모듈 C]
```

### 레시피 6: 버티컬 커머스 분석
```
사용자: "패션 버티컬 커머스(무신사, 에이블리, 지그재그) 비교 분석해줘"

모듈 조합: C → B → F → J → E
구조:
  1. 3개 앱 MAU·사용시간 비교 [모듈 C]
  2. 각 앱 성장 추이 [모듈 B]
  3. 사용자 프로파일 차이 [모듈 F]
  4. 충성도·리텐션 비교 [모듈 J]
  5. 삭제율 비교 [모듈 E]
```

---

## 주의사항

1. **업종명 확인**: `mcp_mobileindex_get_categories_main`으로 정확한 코드 확인
2. **데이터 기간**: BASIC은 2025년까지 / PREMIUM은 전체 기간
3. **수치 출처 명시**: `[출처: 모바일인덱스 INSIGHT, YYYY년 MM월]`
4. **추정 표기**: 4,500만 DMP 기반 추정치임을 명시
5. **competitor 도구**: pkgName에 반드시 1개 앱만 (복수 시 빈 배열)
6. **retention 도구**: 주간만 지원, startDate=월요일, endDate=일요일
7. **overlap 도구**: dateType "w"/"m"만 (일간 불가)
