"""
NDX 패턴 분석 - GitHub Actions 일일 실행
- yfinance에서 NDX, VIX, 10Y 금리 다운로드 (2000-01-01 ~ 현재)
- 21개 정규화 피처 생성
- 현재 시점과 가장 유사한 200개 과거 시점 검색 (k-NN)
- 1일/5일/20일 후 상승 확률 계산
- 결과를 data/result.json으로 저장
"""
import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timezone

# ===== 설정 =====
START_DATE = "2000-01-01"
N_NEIGHBORS = 200
HORIZONS = [1, 5, 20]
DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)


def download_data():
    """yfinance에서 최신 데이터 다운로드"""
    print(f"[1/4] 데이터 다운로드 ({START_DATE} ~ 현재)")
    
    tickers = {"^NDX": "ndx", "^VIX": "vix", "^TNX": "tnx"}
    data = {}
    
    for ticker, name in tickers.items():
        print(f"  - {ticker} 다운로드 중...")
        df = yf.download(ticker, start=START_DATE, progress=False, auto_adjust=False)
        
        if df.empty:
            raise Exception(f"{ticker} 데이터 다운로드 실패")
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        data[name] = df
        print(f"    → {len(df):,}일 ({df.index[0].date()} ~ {df.index[-1].date()})")
    
    # 통합 데이터프레임
    df = pd.DataFrame(index=data['ndx'].index)
    df['close'] = data['ndx']['Close']
    df['high'] = data['ndx']['High']
    df['low'] = data['ndx']['Low']
    df['open'] = data['ndx']['Open']
    df['volume'] = data['ndx']['Volume']
    df['vix'] = data['vix']['Close'].reindex(df.index, method='ffill')
    df['tnx'] = data['tnx']['Close'].reindex(df.index, method='ffill')
    
    return df.dropna()


def make_features(df):
    """21개 피처 생성 (모두 시대 무관 정규화 형태)"""
    f = pd.DataFrame(index=df.index)
    c, h, l, v = df['close'], df['high'], df['low'], df['volume']
    
    # 가격 위치 (5)
    f['pos_ma20'] = (c - c.rolling(20).mean()) / c.rolling(20).mean() * 100
    f['pos_ma60'] = (c - c.rolling(60).mean()) / c.rolling(60).mean() * 100
    f['pos_ma200'] = (c - c.rolling(200).mean()) / c.rolling(200).mean() * 100
    f['pos_52w_high'] = (c - c.rolling(252).max()) / c.rolling(252).max() * 100
    f['pos_52w_low'] = (c - c.rolling(252).min()) / c.rolling(252).min() * 100
    
    # 모멘텀 (4)
    f['ret_1d'] = c.pct_change(1) * 100
    f['ret_5d'] = c.pct_change(5) * 100
    f['ret_20d'] = c.pct_change(20) * 100
    f['ret_60d'] = c.pct_change(60) * 100
    
    # RSI (1)
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    f['rsi14'] = 100 - 100 / (1 + gain/loss)
    
    # 스토캐스틱 (1)
    f['stoch_k'] = (c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min()) * 100
    
    # 볼린저 %B (1)
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    f['bb_pctb'] = (c - (bb_mid - 2*bb_std)) / (4*bb_std) * 100
    
    # MACD (1)
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    f['macd_hist_pct'] = (macd - macd.ewm(span=9).mean()) / c * 100
    
    # 변동성 (3)
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    f['atr_pct'] = tr.rolling(14).mean() / c * 100
    f['vol_20d'] = c.pct_change().rolling(20).std() * np.sqrt(252) * 100
    f['vix'] = df['vix']
    
    # 거래량 (2)
    f['vol_ratio'] = v / v.rolling(20).mean()
    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    f['obv_trend'] = obv.pct_change(20) * 100
    
    # ADX (1)
    plus_dm = h.diff().where((h.diff() > -l.diff()) & (h.diff() > 0), 0)
    minus_dm = -l.diff().where((-l.diff() > h.diff()) & (-l.diff() > 0), 0)
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr14
    minus_di = 100 * minus_dm.rolling(14).mean() / atr14
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    f['adx'] = dx.rolling(14).mean()
    
    # MA 정렬 (1)
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma200 = c.rolling(200).mean()
    aligned_up = ((ma5 > ma20) & (ma20 > ma60) & (ma60 > ma200)).astype(int)
    aligned_dn = ((ma5 < ma20) & (ma20 < ma60) & (ma60 < ma200)).astype(int)
    f['ma_align'] = aligned_up - aligned_dn
    
    # 매크로 (1)
    f['tnx_chg_20d'] = df['tnx'].pct_change(20) * 100
    
    return f


def find_neighbors(features_norm, target_idx, k, exclude_window=20):
    """현재 시점과 가장 유사한 k개 과거 시점 찾기 (유클리드 거리)"""
    target_vec = features_norm.loc[target_idx].values
    cutoff = target_idx - pd.Timedelta(days=exclude_window)
    candidates = features_norm[features_norm.index < cutoff].dropna()
    
    diffs = candidates.values - target_vec
    distances = np.sqrt((diffs ** 2).sum(axis=1))
    sorted_idx = np.argsort(distances)[:k]
    
    return pd.DataFrame({
        'date': candidates.index[sorted_idx],
        'distance': distances[sorted_idx]
    }).set_index('date')


def get_direction_label(up_pct):
    """상승 확률을 한국어 라벨로 변환"""
    if up_pct >= 60:
        return {"label": "상승 우세", "icon": "📈", "color": "strong-up"}
    elif up_pct >= 55:
        return {"label": "약한 상승", "icon": "↗", "color": "weak-up"}
    elif up_pct >= 45:
        return {"label": "중립", "icon": "→", "color": "neutral"}
    elif up_pct >= 40:
        return {"label": "약한 하락", "icon": "↘", "color": "weak-down"}
    else:
        return {"label": "하락 우세", "icon": "📉", "color": "strong-down"}


def analyze():
    """전체 분석 실행"""
    df = download_data()
    
    print("\n[2/4] 피처 생성 (21개)")
    features = make_features(df).dropna()
    print(f"  → 피처 {len(features.columns)}개, 데이터 {len(features):,}일")
    
    print("\n[3/4] 정규화 및 미래 수익률 계산")
    features_norm = (features - features.mean()) / features.std()
    
    c = df['close']
    future_rets = pd.DataFrame(index=df.index)
    for h in HORIZONS:
        future_rets[f'ret_{h}d'] = (c.shift(-h) / c - 1) * 100
    
    target_idx = features_norm.index[-1]
    print(f"  → 분석 기준일: {target_idx.date()}")
    
    print(f"\n[4/4] 유사 {N_NEIGHBORS}개 시점 검색")
    neighbors = find_neighbors(features_norm, target_idx, N_NEIGHBORS)
    neighbor_rets = future_rets.loc[neighbors.index].dropna()
    print(f"  → {len(neighbor_rets)}개 검색됨, 거리 {neighbors['distance'].min():.2f}~{neighbors['distance'].max():.2f}")
    
    # 결과 정리
    horizons_result = []
    for h in HORIZONS:
        rets = neighbor_rets[f'ret_{h}d'].dropna()
        up_count = int((rets > 0).sum())
        total = int(len(rets))
        up_pct = round(up_count / total * 100, 1)
        direction = get_direction_label(up_pct)
        
        horizons_result.append({
            "horizon_days": h,
            "horizon_label": f"{h}일 후" if h == 1 else (f"{h}일 후 (1주)" if h == 5 else f"{h}일 후 (1달)"),
            "up_probability": up_pct,
            "up_count": up_count,
            "total_count": total,
            "direction_label": direction["label"],
            "direction_icon": direction["icon"],
            "direction_color": direction["color"]
        })
    
    # 가장 닮은 상위 10개 시점
    top10 = []
    for date, row in neighbors.head(10).iterrows():
        item = {
            "date": date.strftime('%Y-%m-%d'),
            "distance": round(float(row['distance']), 2),
            "close": round(float(df.loc[date, 'close']), 2),
            "vix": round(float(df.loc[date, 'vix']), 2)
        }
        for h in HORIZONS:
            val = future_rets.loc[date, f'ret_{h}d']
            item[f'ret_{h}d'] = round(float(val), 2) if pd.notna(val) else None
        top10.append(item)
    
    # 10Y 금리 추이 분석 (1년 전, 2년 전, 5년 전 대비)
    tnx_now = float(df.loc[target_idx, 'tnx'])
    
    def get_tnx_at(days_back):
        """N일 전 금리값 가져오기 (대략적, 가장 가까운 영업일)"""
        target = target_idx - pd.Timedelta(days=days_back)
        # target 이전 가장 가까운 데이터
        past_data = df[df.index <= target]
        if len(past_data) == 0:
            return None
        return float(past_data.iloc[-1]['tnx'])
    
    tnx_1y = get_tnx_at(365)
    tnx_2y = get_tnx_at(730)
    tnx_5y = get_tnx_at(1825)
    
    # 1년 최고/최저
    one_year_data = df[df.index >= target_idx - pd.Timedelta(days=365)]
    tnx_1y_high = float(one_year_data['tnx'].max())
    tnx_1y_low = float(one_year_data['tnx'].min())
    
    # 추세 판정
    if tnx_1y is not None:
        diff_1y = tnx_now - tnx_1y
        if diff_1y > 0.5:
            tnx_trend = "상승"
        elif diff_1y < -0.5:
            tnx_trend = "하락"
        else:
            tnx_trend = "보합"
    else:
        diff_1y = 0
        tnx_trend = "보합"
    
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_date": target_idx.strftime('%Y-%m-%d'),
        "current_state": {
            "ndx_close": round(float(df.loc[target_idx, 'close']), 2),
            "vix": round(float(df.loc[target_idx, 'vix']), 2),
            "tnx": round(tnx_now, 2),
            "tnx_1y_ago": round(tnx_1y, 2) if tnx_1y is not None else None,
            "tnx_2y_ago": round(tnx_2y, 2) if tnx_2y is not None else None,
            "tnx_5y_ago": round(tnx_5y, 2) if tnx_5y is not None else None,
            "tnx_1y_high": round(tnx_1y_high, 2),
            "tnx_1y_low": round(tnx_1y_low, 2),
            "tnx_diff_1y": round(diff_1y, 2),
            "tnx_trend": tnx_trend,
            "rsi14": round(float(features.loc[target_idx, 'rsi14']), 2),
            "bb_pctb": round(float(features.loc[target_idx, 'bb_pctb']), 2),
            "ma_align": int(features.loc[target_idx, 'ma_align'])
        },
        "analysis": {
            "data_period": f"{features.index[0].strftime('%Y-%m-%d')} ~ {features.index[-1].strftime('%Y-%m-%d')}",
            "total_days": int(len(features)),
            "n_neighbors": N_NEIGHBORS,
            "n_features": int(len(features.columns)),
            "distance_range": [
                round(float(neighbors['distance'].min()), 2),
                round(float(neighbors['distance'].max()), 2)
            ]
        },
        "horizons": horizons_result,
        "top_similar_dates": top10
    }
    
    # JSON 저장
    output_path = os.path.join(DATA_DIR, "result.json")
    with open(output_path, 'w', encoding='utf-8') as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 결과 저장: {output_path}")
    print(f"\n=== 요약 ===")
    print(f"기준일: {result['target_date']}")
    print(f"NDX: {result['current_state']['ndx_close']:,}")
    for h in result['horizons']:
        print(f"  {h['horizon_label']}: {h['direction_icon']} {h['direction_label']} ({h['up_probability']}%)")
    
    return result


if __name__ == "__main__":
    analyze()
