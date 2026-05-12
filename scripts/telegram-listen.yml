"""
텔레그램 명령어 응답 처리
5분마다 GitHub Actions가 실행:
1. 텔레그램 봇에 새 메시지 왔는지 확인 (getUpdates)
2. /report 명령어 감지하면 즉시 리포트 전송
3. 마지막 처리한 message_id를 파일로 저장 (중복 방지)

지원 명령어:
- /report : 즉시 일일 리포트
- /help : 명령어 안내
"""
import os
import json
import requests
import time
from datetime import datetime, timezone

# 환경변수
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 환경변수가 설정되지 않음")

# 마지막 처리한 update_id 저장 위치
STATE_FILE = 'data/telegram_state.json'


def send_telegram(message):
    """텔레그램 메시지 전송 (HTML)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload, timeout=10)
    if res.status_code != 200:
        print(f"⚠️ 전송 실패: {res.status_code} - {res.text}")
        return False
    return True


def load_state():
    """마지막 update_id 읽기"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ 상태 파일 읽기 실패: {e}")
    return {"last_update_id": 0}


def save_state(state):
    """update_id 저장"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"⚠️ 상태 파일 저장 실패: {e}")


def get_updates(offset):
    """텔레그램 새 메시지 가져오기"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {
        "offset": offset + 1,  # 이전에 처리한 메시지 이후부터
        "timeout": 5,
        "limit": 20
    }
    try:
        res = requests.get(url, params=params, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ getUpdates 실패: {res.status_code}")
            return []
        data = res.json()
        if not data.get('ok'):
            return []
        return data.get('result', [])
    except Exception as e:
        print(f"⚠️ getUpdates 예외: {e}")
        return []


def handle_report_command():
    """/report 명령어 처리: telegram_report.py의 build_report 사용"""
    print("[명령] /report 처리 중...")
    
    # telegram_report.py를 import해서 사용
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "telegram_report", 
        os.path.join(os.path.dirname(__file__), "telegram_report.py")
    )
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    
    try:
        message = tr.build_report()
        if send_telegram(message):
            print("✅ 리포트 발송 성공")
        else:
            print("⚠️ 리포트 발송 실패")
    except Exception as e:
        print(f"❌ 리포트 생성 실패: {e}")
        send_telegram(f"⚠️ <b>리포트 생성 실패</b>\n{str(e)[:300]}")


def handle_help_command():
    """/help 명령어 처리"""
    msg = (
        "📌 <b>사용 가능한 명령어</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "/report - 즉시 시장 지표 리포트\n"
        "/help - 명령어 안내\n"
        "━━━━━━━━━━━━━━━━\n"
        "※ 자동 발송: 매일 18:00, 22:00 (한국시간)\n"
        "※ 명령어 응답은 최대 5분 소요"
    )
    send_telegram(msg)
    print("✅ /help 응답 발송")


def main():
    print(f"[명령어 폴링] {datetime.now(timezone.utc).isoformat()}")
    
    # 마지막 처리 update_id 읽기
    state = load_state()
    last_id = state.get('last_update_id', 0)
    print(f"  마지막 처리 ID: {last_id}")
    
    # 새 메시지 가져오기
    updates = get_updates(last_id)
    
    if not updates:
        print("  새 명령어 없음")
        return
    
    print(f"  새 메시지 {len(updates)}개 발견")
    
    new_last_id = last_id
    commands_processed = 0
    
    for update in updates:
        update_id = update.get('update_id', 0)
        new_last_id = max(new_last_id, update_id)
        
        msg = update.get('message', {})
        chat_id = str(msg.get('chat', {}).get('id', ''))
        text = msg.get('text', '').strip().lower()
        
        # 본인 Chat ID만 허용 (보안)
        if chat_id != str(TELEGRAM_CHAT_ID):
            print(f"  ⚠️ 허용되지 않은 Chat ID: {chat_id} → 무시")
            continue
        
        # /report 처리
        if text in ['/report', 'report']:
            print(f"  명령 수신: /report (update_id={update_id})")
            handle_report_command()
            commands_processed += 1
        
        # /help 처리
        elif text in ['/help', 'help']:
            print(f"  명령 수신: /help (update_id={update_id})")
            handle_help_command()
            commands_processed += 1
        
        # /start 처리 (안내 메시지)
        elif text in ['/start', 'start']:
            print(f"  명령 수신: /start (update_id={update_id})")
            send_telegram(
                "🤖 <b>junirich 시장 지표 봇</b>\n\n"
                "매일 한국시간 <b>18:00, 22:00</b>에 자동으로 시장 지표 리포트를 발송합니다.\n\n"
                "/report - 지금 즉시 리포트 받기\n"
                "/help - 명령어 안내"
            )
            commands_processed += 1
    
    # 상태 저장 (다음 실행 때 중복 처리 안 하도록)
    if new_last_id > last_id:
        save_state({'last_update_id': new_last_id})
        print(f"  상태 저장: last_update_id = {new_last_id}")
    
    print(f"[완료] 명령어 {commands_processed}개 처리")


if __name__ == "__main__":
    main()
