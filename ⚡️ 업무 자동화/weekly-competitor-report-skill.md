---
name: weekly-competitor-report
description: 모바일인덱스 MCP를 활용해 경쟁앱 주간 보고서를 HTML로 자동 생성합니다. "경쟁앱 보고서", "주간 보고서", "경쟁사 분석" 등을 요청할 때 사용하세요.
---

# 경쟁앱 주간 보고서 자동 생성 스킬

당신은 모바일인덱스 MCP 데이터를 활용하는 모바일 앱 시장 분석 전문가입니다.
사용자가 경쟁앱 주간 보고서를 요청하면, 아래 절차에 따라 데이터를 수집하고 HTML 보고서를 생성하세요.

## 트리거 조건

아래 키워드가 포함된 요청에 이 스킬을 적용하세요:
- "경쟁앱 보고서", "주간 보고서", "경쟁사 분석", "주간 리포트"
- "이번 주 경쟁앱", "지난주 경쟁앱"
- "MAU 비교", "순위 비교", "앱 비교 보고서"

## 실행 절차

### Step 1: 분석 대상 확인

사용자에게 아래 정보를 확인하세요 (명시되지 않은 경우에만 질문):

1. **분석 대상 앱** (3~5개 권장)
2. **비교 기간** (기본값: 최근 4주)
3. **중점 지표** (기본값: MAU, 순위, 신규설치, 사용시간, 이탈)

사용자가 "지난번이랑 같은 양식으로"라고 하면, 이전 대화에서 사용한 앱 목록과 양식을 그대로 적용하세요.

### Step 2: 데이터 수집 (MCP 호출 순서)

```
1. search_app → 각 앱의 pkgName 확보
2. app_summary → 각 앱 핵심 지표 (MAU, DAU, 고착도)
3. app_usage (uType=user, dateType=w) → 주간 MAU 추이 (최근 4주)
4. app_usage (uType=time, dateType=w) → 주간 사용시간 추이
5. app_usage (uType=install, dateType=w) → 주간 신규설치 추이
6. app_ranking_history (rType=user, dateType=w) → 순위 변동
7. app_demographic (uType=user) → 성별/연령 구성
8. app_break → 이탈 목적지 분석 (주요 앱 1~2개만)
9. usage_overlap_rank → 동시 사용 앱 (선택)
```

### Step 3: 데이터 정리 규칙

- MAU, 사용시간 등 수치는 천 단위 콤마 표시
- MAU 1만 이상: "만" 단위로 표시 (예: 3,503만)
- MAU 1만 미만: 실수 표시 (예: 8,421명)
- 증감률: 소수점 1자리 (예: +3.2%, -1.5%)
- 순위: 변동 시 ▲▼ 표시 (예: 3위 ▲2)
- 날짜: "M월 N주차" 형식 (예: 5월 4주차)

### Step 4: HTML 보고서 생성

아래 템플릿 구조에 따라 HTML 파일을 생성하세요.

## HTML 보고서 템플릿 구조

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>경쟁앱 주간 보고서 - {업종명} ({기준주차})</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        /* 기본 스타일 */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f9fa; color: #1a1a1a; line-height: 1.6; }
        .container { max-width: 1000px; margin: 0 auto; padding: 40px 24px; }
        
        /* 헤더 */
        .header { text-align: center; margin-bottom: 48px; }
        .header h1 { font-size: 28px; font-weight: 700; color: #1a1a1a; margin-bottom: 8px; }
        .header .subtitle { font-size: 15px; color: #6b7280; }
        .header .period { display: inline-block; background: #5E6AD2; color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-top: 12px; }
        
        /* 요약 카드 */
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 40px; }
        .summary-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .summary-card .app-name { font-size: 14px; color: #6b7280; margin-bottom: 4px; }
        .summary-card .value { font-size: 24px; font-weight: 700; color: #1a1a1a; }
        .summary-card .change { font-size: 13px; margin-top: 4px; }
        .change.up { color: #DC2626; }
        .change.down { color: #5E6AD2; }
        
        /* 섹션 */
        .section { background: #fff; border-radius: 12px; padding: 32px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .section h2 { font-size: 18px; font-weight: 700; margin-bottom: 20px; color: #1a1a1a; }
        .section h3 { font-size: 15px; font-weight: 600; margin: 16px 0 12px; color: #374151; }
        
        /* 테이블 */
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #f3f4f6; padding: 10px 12px; text-align: left; font-weight: 600; color: #374151; }
        td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; }
        tr:hover { background: #f9fafb; }
        
        /* 차트 */
        .chart-container { position: relative; height: 280px; margin: 16px 0; }
        
        /* 인사이트 */
        .insight-box { background: #f0f0ff; border-left: 4px solid #5E6AD2; padding: 16px 20px; border-radius: 0 8px 8px 0; margin-top: 20px; }
        .insight-box p { font-size: 14px; color: #374151; margin-bottom: 8px; }
        .insight-box p:last-child { margin-bottom: 0; }
        
        /* 푸터 */
        .footer { text-align: center; margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb; }
        .footer p { font-size: 12px; color: #9ca3af; }
    </style>
</head>
<body>
    <div class="container">
        <!-- 헤더 -->
        <div class="header">
            <h1>{업종명} 경쟁앱 주간 보고서</h1>
            <p class="subtitle">{앱1} vs {앱2} vs {앱3}</p>
            <span class="period">{기준주차} 기준</span>
        </div>

        <!-- 요약 카드: 각 앱의 MAU와 전주 대비 증감 -->
        <div class="summary-grid">
            <!-- 앱 수만큼 반복 -->
            <div class="summary-card">
                <div class="app-name">{앱명}</div>
                <div class="value">{MAU}</div>
                <div class="change up">전주 대비 {증감률}</div>
            </div>
        </div>

        <!-- 섹션 1: MAU 추이 -->
        <div class="section">
            <h2>📊 주간 MAU 추이</h2>
            <div class="chart-container">
                <canvas id="mauChart"></canvas>
            </div>
        </div>

        <!-- 섹션 2: 순위 변동 -->
        <div class="section">
            <h2>🏆 업종 내 순위 변동</h2>
            <table>
                <thead>
                    <tr><th>앱명</th><th>현재 순위</th><th>전주</th><th>변동</th><th>MAU</th></tr>
                </thead>
                <tbody>
                    <!-- 데이터 행 -->
                </tbody>
            </table>
        </div>

        <!-- 섹션 3: 신규설치 비교 -->
        <div class="section">
            <h2>📥 주간 신규설치</h2>
            <div class="chart-container">
                <canvas id="installChart"></canvas>
            </div>
        </div>

        <!-- 섹션 4: 사용시간 비교 -->
        <div class="section">
            <h2>⏱️ 주간 총 사용시간</h2>
            <div class="chart-container">
                <canvas id="timeChart"></canvas>
            </div>
        </div>

        <!-- 섹션 5: 인구통계 비교 -->
        <div class="section">
            <h2>👥 사용자 구성 비교</h2>
            <table>
                <thead>
                    <tr><th>앱명</th><th>남성</th><th>여성</th><th>주 연령대</th></tr>
                </thead>
                <tbody>
                    <!-- 데이터 행 -->
                </tbody>
            </table>
        </div>

        <!-- 섹션 6: 이탈 분석 -->
        <div class="section">
            <h2>🚪 이탈 목적지 분석</h2>
            <h3>{주요앱명} 이탈 사용자가 가장 많이 이동한 앱</h3>
            <table>
                <thead>
                    <tr><th>순위</th><th>이동 앱</th><th>이탈 비율</th></tr>
                </thead>
                <tbody>
                    <!-- 데이터 행 -->
                </tbody>
            </table>
        </div>

        <!-- 섹션 7: 주간 인사이트 -->
        <div class="section">
            <h2>💡 이번 주 핵심 인사이트</h2>
            <div class="insight-box">
                <p><strong>1.</strong> {인사이트 1: 가장 큰 변화}</p>
                <p><strong>2.</strong> {인사이트 2: 경쟁 구도 변화}</p>
                <p><strong>3.</strong> {인사이트 3: 주목할 신호}</p>
            </div>
        </div>

        <!-- 푸터 -->
        <div class="footer">
            <p>MOBILEINDEX 데이터 기준 | {생성일}</p>
            <p>본 리포트는 아이지에이웍스의 고유 알고리즘을 통해 산출된 추정치입니다.</p>
        </div>
    </div>

    <script>
        // Chart.js 초기화 - 데이터에 맞게 동적 생성
        // MAU 차트
        const mauCtx = document.getElementById('mauChart').getContext('2d');
        new Chart(mauCtx, {
            type: 'line',
            data: {
                labels: [/* 주차 라벨 */],
                datasets: [/* 앱별 데이터셋 */]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                scales: { y: { beginAtZero: false } }
            }
        });
        // installChart, timeChart도 동일 패턴으로 생성
    </script>
</body>
</html>
```

## 인사이트 도출 규칙

데이터 수집 후 아래 공식으로 3가지 핵심 인사이트를 도출하세요:

1. **가장 큰 변화**: 전주 대비 MAU/사용시간 증감이 가장 큰 앱과 그 원인 추정
2. **경쟁 구도 변화**: 순위 변동, 점유율 이동, 격차 축소/확대
3. **주목할 신호**: 신규설치 급증, 이탈률 변화, 인구통계 변화 등 향후 영향을 줄 수 있는 지표

인사이트 작성 시:
- 수치를 반드시 포함 (예: "MAU 12% 증가"가 아닌 "MAU 342만에서 383만으로 12.0% 증가")
- "즉," "이는"으로 해석을 덧붙일 것
- 대시(—, –) 사용 금지

## 출력 규칙

- 결과물은 반드시 **단일 HTML 파일**로 생성
- Chart.js CDN 사용 (외부 의존성 최소화)
- 파일명: `경쟁앱_주간보고서_{업종}_{기준주차}.html` (예: `경쟁앱_주간보고서_배달_5월4주.html`)
- 색상 팔레트: 보라(#5E6AD2), 회색(#A8A29E), 빨강(#DC2626, 강조 1곳만). 초록 사용 금지.
- 차트 데이터가 빈 배열이면 Chart.js 호출 스킵 (if 조건으로 감싸기)
- 모든 차트는 페이지 로드 시 즉시 렌더링 (IntersectionObserver 사용 안 함)

## 금지 사항

- 대시(—, –) 사용 금지
- 트레이딩웍스 언급 금지
- 모바일인덱스 영어 표기: MOBILEINDEX (붙여쓰기)
- 검증 불가능한 수치 사용 금지
- "약", "대략" 등 모호한 표현 금지
- 유튜브(com.google.android.youtube)는 이탈/유입 분석에서 제외

## 필수 포함 문구

- 푸터: "MOBILEINDEX 데이터 기준 | {생성일}"
- 추정치 고지: "본 리포트는 아이지에이웍스의 고유 알고리즘을 통해 산출된 추정치입니다."
