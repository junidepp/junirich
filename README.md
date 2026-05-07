# junirich - NDX 패턴 분석

나스닥 100 (NDX)의 과거 패턴 기반 방향 예측 보조 지표.

## 작동 방식

1. **데이터**: 2000-01-01부터 NDX, VIX, 10년물 금리 (yfinance)
2. **피처**: 21개 정규화 지표 (가격위치, 모멘텀, RSI, 볼린저, MACD, ATR, ADX, MA정렬, 거래량, 매크로)
3. **분석**: k-NN 유사 시점 200개 검색 → 1일/5일/20일 후 상승 확률 계산

## 자동 갱신

- 매일 한국시간 오전 7시 GitHub Actions 자동 실행
- 결과를 `data/result.json`에 저장 후 자동 커밋
- Netlify가 변경 감지 → 자동 재배포

## 수동 실행

GitHub Actions 탭 → "Daily NDX Pattern Analysis" → "Run workflow"

## ⚠️ 주의

보조 지표일 뿐이며 투자 판단의 유일한 근거로 사용하지 마세요.
