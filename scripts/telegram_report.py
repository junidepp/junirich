"""
텔레그램 일일 시장 리포트
매일 한국시간 22:00에 GitHub Actions가 실행
- result.json: NDX 패턴 분석 결과
- soxl_rsi.json: SOXL RSI 분석 결과
- CNN F&G API: 공포·탐욕 지수 (실시간 호출)
모든 지표를 한 메시지로 포맷팅하여 텔레그램 전송
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

# 환경변수에서 텔레그램 정보 읽기 (GitHub Secrets로 주입됨)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 환경변수가 설정되지 않음")


def send_telegram(message):
    """텔레그램 메시지 전송 (HTML 모드)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload, timeout=10)
    if res.status_code != 200:
        raise Exception(f"텔레그램 전송 실패: {res.status_code} - {res.text}")
    print(f"✅ 텔레그램 전송 성공")


def get_cnn_fear_greed():
    """CNN 공포·탐욕 지수 조회"""
    url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://edition.cnn.com/',
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None
        data = res.json()
        cur = data.get('fear_and_greed', {})
        score = round(cur.get('score', 0))
        rating = cur.get('rating', '').replace('_', ' ').upper()
        ko_rating = {
            'EXTREME FEAR': '극도의 공포',
            'FEAR': '공포',
            'NEUTRAL': '중립',
            'GREED': '탐욕',
            'EXTREME GREED': '극도의 탐욕'
        }.get(rating, rating)
        return {'score': score, 'rating': ko_rating}
    except Exception as e:
        print(f"⚠️ CNN F&G 조회 실패: {e}")
        return None


def load_json(path):
    """JSON 파일 안전하게 읽기"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ {path} 로드 실패: {e}")
        return None


def get_vix_zone(vix):
    """VIX 값에 따른 구간"""
    if vix < 15:   return "지나친안정"
    if vix < 20:   return "정상"
    if vix < 30:   return "주의"
    if vix < 40:   return "공포"
    return "극단적공포"


def get_rsi_zone(rsi):
    """RSI 값에 따른 구간"""
    if rsi >= 80:  return "극단 과매수"
    if rsi >= 70:  return "과매수"
    if rsi >= 50:  return "강세"
    if rsi >= 30:  return "약세"
    return "과매도"


def get_bb_zone(bb):
    """볼린저 %B 구간"""
    if bb >= 100:  return "상단 돌파"
    if bb >= 80:   return "상단 근접"
    if bb >= 50:   return "중심선 위"
    if bb >= 20:   return "중심선 아래"
    if bb >= 0:    return "하단 근접"
    return "하단 돌파"


def get_ma_align_label(ma):
    """MA 정렬 라벨"""
    if ma == 1:    return "정배열↑"
    if ma == -1:   return "역배열↓"
    return "혼조"


def build_report():
    """리포트 메시지 생성"""
    # 데이터 로드
    ndx_data = load_json('data/result.json')
    soxl_data = load_json('data/soxl_rsi.json')
    fg = get_cnn_fear_greed()
    
    # 현재 한국시간
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    weekday = ['월', '화', '수', '목', '금', '토', '일'][now.weekday()]
    now_str = now.strftime(f'%Y-%m-%d ({weekday}) %H:%M')
    
    lines = []
    lines.append("📊 <b>시장 지표 일일 리포트</b>")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"🗓 {now_str}")
    lines.append("")
    
    # ===== 변동성 지표 =====
    lines.append("<b>[변동성 지표]</b>")
    
    if ndx_data and ndx_data.get('current_state', {}).get('vix'):
        vix = ndx_data['current_state']['vix']
        vix_zone = get_vix_zone(vix)
        lines.append(f"VIX:        <b>{vix}</b>  ({vix_zone})")
    else:
        lines.append("VIX:        조회 실패")
    
    if fg:
        lines.append(f"CNN F&amp;G:    <b>{fg['score']}/100</b>  ({fg['rating']})")
    else:
        lines.append("CNN F&amp;G:    조회 실패")
    
    lines.append("")
    
    # ===== NDX 현재 상태 =====
    if ndx_data and ndx_data.get('current_state'):
        cs = ndx_data['current_state']
        lines.append("<b>[NDX 현재 상태]</b>")
        lines.append(f"기준일:     {ndx_data.get('target_date', '-')}")
        lines.append(f"NDX 종가:   <b>{cs['ndx_close']:,}</b>")
        
        rsi = cs.get('rsi14', 0)
        lines.append(f"RSI(14):    <b>{rsi}</b>  ({get_rsi_zone(rsi)})")
        
        bb = cs.get('bb_pctb', 0)
        lines.append(f"볼린저 %B:  <b>{bb}</b>  ({get_bb_zone(bb)})")
        
        ma = cs.get('ma_align', 0)
        lines.append(f"MA 정렬:    <b>{get_ma_align_label(ma)}</b>")
        
        tnx = cs.get('tnx', 0)
        tnx_trend = cs.get('tnx_trend', '-')
        tnx_diff = cs.get('tnx_diff_1y', 0)
        diff_sign = '+' if tnx_diff > 0 else ''
        lines.append(f"10Y 금리:   <b>{tnx}%</b>  ({tnx_trend}, 1년 {diff_sign}{tnx_diff}%p)")
        lines.append("")
        
        # ===== NDX 1일 후 예측 =====
        horizons = ndx_data.get('horizons', [])
        h1 = next((h for h in horizons if h.get('horizon_days') == 1), None)
        if h1:
            lines.append("<b>[NDX 1일 후 예측]</b>")
            prob = h1.get('up_probability', 0)
            label = h1.get('direction_label', '-')
            icon = h1.get('direction_icon', '')
            up = h1.get('up_count', 0)
            total = h1.get('total_count', 0)
            lines.append(f"방향:       {icon} <b>{label}</b>")
            lines.append(f"상승확률:   <b>{prob}%</b>  ({up}/{total})")
            
            # 강한 신호 여부 표시
            if prob >= 55 or prob <= 45:
                lines.append("→ <b>강한 신호 구간</b> (참고 가치 ↑)")
            else:
                lines.append("→ 약한 신호 (참고 의미 작음)")
            lines.append("")
    
    # ===== SOXL =====
    if soxl_data and soxl_data.get('current'):
        c = soxl_data['current']
        s = soxl_data.get('signal', {})
        lines.append("<b>[SOXL]</b>")
        lines.append(f"종가:       <b>${c.get('close', 0):,}</b>")
        
        rsi = c.get('rsi', 0)
        rsi_change = c.get('rsi_change', 0)
        change_sign = '+' if rsi_change > 0 else ''
        change_arrow = '▲' if rsi_change > 0 else '▼' if rsi_change < 0 else '—'
        lines.append(f"RSI(14):    <b>{rsi}</b>  ({change_arrow} {change_sign}{rsi_change})")
        
        # 신호
        icon = s.get('icon', '')
        label = s.get('label', '-')
        action = s.get('action', '')
        lines.append(f"신호:       {icon} <b>{label}</b>")
        if action and s.get('tier', 0) != 0:
            # 짧게 줄이기
            lines.append(f"            {action}")
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("🔗 https://junirich.netlify.app")
    
    return "\n".join(lines)


def main():
    print(f"[리포트 시작] {datetime.now(timezone.utc).isoformat()}")
    
    try:
        message = build_report()
        print("\n=== 메시지 미리보기 ===")
        # HTML 태그 제거해서 콘솔 출력
        preview = message.replace('<b>', '').replace('</b>', '').replace('&amp;', '&')
        print(preview)
        print("=" * 40)
        
        send_telegram(message)
        print("\n✅ 일일 리포트 발송 완료")
    
    except Exception as e:
        print(f"❌ 리포트 발송 실패: {e}")
        # 실패해도 에러 알림은 보내려고 시도
        try:
            error_msg = f"⚠️ <b>리포트 생성 실패</b>\n\n에러: {str(e)[:500]}"
            send_telegram(error_msg)
        except:
            pass
        raise


if __name__ == "__main__":
    main()
