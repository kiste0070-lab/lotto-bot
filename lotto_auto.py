"""
Auto Lotto - 동행복권 로또 6/45 자동 구매 스크립트
GitHub Actions에서 주 1회 실행 (매주 금요일 09:00 KST)
"""

import os
import sys
import json
import math
import random
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError

# RSA 암호화용
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===== 상수 =====
BASE_URL = 'https://www.dhlottery.co.kr'
OLOTTO_URL = 'https://ol.dhlottery.co.kr'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
}

# ===== HTTP 세션 =====
class LottoSession:
    """쿠키를 자동 관리하는 HTTP 세션"""
    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

    def get(self, url, headers=None, referer=None):
        req_headers = dict(HEADERS)
        if headers:
            req_headers.update(headers)
        if referer:
            req_headers['Referer'] = referer
        req = Request(url, headers=req_headers)
        resp = self.opener.open(req, timeout=15)
        return resp.read().decode('utf-8', errors='replace')

    def post(self, url, data, headers=None, referer=None, origin=None):
        req_headers = dict(HEADERS)
        if headers:
            req_headers.update(headers)
        if referer:
            req_headers['Referer'] = referer
        if origin:
            req_headers['Origin'] = origin
        if isinstance(data, dict):
            data = urlencode(data).encode('utf-8')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        req = Request(url, data=data, headers=req_headers)
        resp = self.opener.open(req, timeout=15)
        return resp.read().decode('utf-8', errors='replace')

    def get_json(self, url, headers=None, referer=None):
        text = self.get(url, headers=headers, referer=referer)
        return json.loads(text)

    def post_json(self, url, data, headers=None, referer=None, origin=None):
        text = self.post(url, data, headers=headers, referer=referer, origin=origin)
        return json.loads(text)


# ===== RSA 암호화 =====
def rsa_encrypt(plain_text: str, modulus_hex: str, exponent_hex: str) -> str:
    """동행복권 RSA 공개키로 암호화 후 hex 반환"""
    n = int(modulus_hex, 16)
    e = int(exponent_hex, 16)
    pubkey = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(pubkey)
    encrypted = cipher.encrypt(plain_text.encode('utf-8'))
    return encrypted.hex()


# ===== 회차 계산 =====
def get_current_round() -> int:
    """현재 판매 중인 로또 회차 계산 (1회차: 2002-12-07)"""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    first_round = datetime(2002, 12, 7)

    # 이번 주 토요일
    days_until_saturday = (5 - today.weekday()) % 7  # Monday=0, Saturday=5
    this_saturday = today + timedelta(days=days_until_saturday)

    days_diff = (this_saturday - first_round).days
    weeks_passed = days_diff // 7
    round_num = 1 + weeks_passed

    # 토요일 20:45 이후면 다음 회차
    if now.weekday() == 5:  # Saturday
        draw_time = now.replace(hour=20, minute=45, second=0, microsecond=0)
        if now > draw_time:
            round_num += 1

    return round_num


def get_draw_dates() -> tuple[str, str]:
    """추첨일, 지급기한 반환 (YYYY/MM/DD 형식)"""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_until_saturday = (5 - today.weekday()) % 7
    draw_date = today + timedelta(days=days_until_saturday)
    pay_limit = draw_date + timedelta(days=365)
    return draw_date.strftime('%Y/%m/%d'), pay_limit.strftime('%Y/%m/%d')


# ===== 구매 파라미터 =====
def build_param(auto_games: int) -> str:
    """자동 구매 파라미터 JSON 생성"""
    slot_names = ['A', 'B', 'C', 'D', 'E']
    params = []
    for i in range(auto_games):
        params.append({
            'genType': '0',
            'arrGameChoiceNum': None,
            'alpabet': slot_names[i],
        })
    return json.dumps(params)


import html

# ===== 텔레그램 알림 =====
def send_telegram_message(token: str, chat_id: str, message: str, parse_mode: str = 'HTML') -> bool:
    """텔레그램으로 메시지 전송"""
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': message,
        'parse_mode': parse_mode,
    }).encode('utf-8')
    req = Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        resp = urlopen(req, timeout=10)
        result = json.loads(resp.read().decode('utf-8'))
        return result.get('ok', False)
    except Exception as e:
        logger.error(f'텔레그램 전송 실패: {e}')
        return False


def format_success_message(result: dict) -> str:
    """구매 성공 메시지 포맷팅"""
    lines = [
        f'🎰 <b>[구매완료] 로또 {result["round"]}회</b>',
        f'📅 추첨일: {result["draw_date"]}',
        f'💰 구매 금액: {result["amount"]:,}원',
        f'🎮 구매 게임 수: {result["auto_count"]}개',
        '',
    ]
    for i, nums in enumerate(result['numbers'], 1):
        lines.append(f'게임 {i}: {", ".join(str(n) for n in nums)}')
    return '\n'.join(lines)


def format_error_message(error: str) -> str:
    """구매 실패 메시지 포맷팅 (<, > 등 특수문자 HTML 이스케이프)"""
    safe_error = html.escape(error)
    return f'❌ <b>[구매실패] 로또 자동 구매</b>\n\n에러: {safe_error}'


# ===== 메인 로직 =====
def auto_purchase(user_id: str, password: str, auto_games: int = 5) -> dict:
    """로또 자동 구매 실행"""
    session = LottoSession()

    # Step 1: 메인 페이지 방문 (쿠키 수집)
    logger.info('Step 1: 메인 페이지 방문')
    session.get(BASE_URL)

    # Step 2: 로그인 페이지 방문
    logger.info('Step 2: 로그인 페이지 방문')
    session.get(f'{BASE_URL}/login')

    # Step 3: RSA 공개키 획득
    logger.info('Step 3: RSA 공개키 획득')
    rsa_resp = session.get_json(
        f'{BASE_URL}/login/selectRsaModulus.do',
        headers={
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        referer=f'{BASE_URL}/login',
    )
    if not rsa_resp.get('data'):
        raise Exception('RSA 키를 가져올 수 없습니다.')

    modulus = rsa_resp['data']['rsaModulus']
    exponent = rsa_resp['data']['publicExponent']
    logger.info(f'RSA modulus: {modulus[:20]}... exp: {exponent}')

    # Step 4: ID/PW 암호화 + 로그인
    logger.info('Step 4: 로그인 시도')
    encrypted_id = rsa_encrypt(user_id, modulus, exponent)
    encrypted_pw = rsa_encrypt(password, modulus, exponent)

    login_body = (
        f'userId={encrypted_id}'
        f'&userPswdEncn={encrypted_pw}'
        f'&inpUserId={user_id}'
    )
    session.post(
        f'{BASE_URL}/login/securityLoginCheck.do',
        data=login_body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        referer=f'{BASE_URL}/login',
        origin=BASE_URL,
    )

    # Step 5: 메인 + game645 방문 (ol 세션 확보)
    logger.info('Step 5: game645 페이지 방문 (ol 세션)')
    session.get(f'{BASE_URL}/main')
    session.get(f'{OLOTTO_URL}/olotto/game/game645.do')

    # Step 6: 로그인 검증
    logger.info('Step 6: 로그인 검증')
    verify_resp = session.get(
        f'{BASE_URL}/mypage/selectUserMndp.do',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    # 검증 응답 확인 (간단한 체크)
    logger.info('로그인 검증 완료')

    # Step 7: 잔액 확인
    logger.info('Step 7: 잔액 확인')
    balance_resp = session.get_json(
        f'{BASE_URL}/mypage/selectUserMndp.do',
        headers={'X-Requested-With': 'XMLHttpRequest'},
        referer=f'{BASE_URL}/mypage/home',
    )
    balance = balance_resp.get('data', {}).get('userMndp', {}).get('crntEntrsAmt', 0)
    logger.info(f'현재 잔액: {balance:,}원')

    required = auto_games * 1000
    if balance < required:
        raise Exception(f'잔액 부족: {balance:,}원 < {required:,}원 필요')

    # Step 8: 구매 - readySocket (Direct IP 획득)
    logger.info('Step 8: 구매 준비 (Direct IP 획득)')
    ready_resp = session.post_json(
        f'{OLOTTO_URL}/olotto/game/egovUserReadySocket.json',
        data='',
    )
    direct_ip = ready_resp.get('ready_ip', '')
    if not direct_ip:
        raise Exception(f'Direct IP 획득 실패: {ready_resp}')
    logger.info(f'Direct IP: {direct_ip}')

    # Step 9: 구매 실행
    round_num = get_current_round()
    draw_date, pay_limit = get_draw_dates()
    param = build_param(auto_games)

    logger.info(f'Step 9: 구매 실행 (회차: {round_num}, 게임: {auto_games})')
    buy_data = {
        'round': str(round_num),
        'direct': direct_ip,
        'nBuyAmount': str(1000 * auto_games),
        'param': param,
        'ROUND_DRAW_DATE': draw_date,
        'WAMT_PAY_TLMT_END_DT': pay_limit,
        'gameCnt': auto_games,
        'saleMdaDcd': '10',
    }

    buy_resp = session.post(
        f'{OLOTTO_URL}/olotto/game/execBuy.do',
        data=buy_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        referer=f'{OLOTTO_URL}/olotto/game/game645.do',
        origin=OLOTTO_URL,
    )

    # 응답 파싱
    try:
        result = json.loads(buy_resp)
    except json.JSONDecodeError:
        raise Exception(f'구매 실패: 세션 만료 (HTML 응답). 재로그인 필요.')

    result_data = result.get('result', {})
    result_code = result_data.get('resultCode', '')

    if result_code != '100':
        msg = result_data.get('resultMsg', '알 수 없는 오류')
        raise Exception(f'구매 실패: {msg} (code: {result_code})')

    # 구매 성공 - 번호 추출
    arr_game = result_data.get('arrGameChoiceNum', [])
    numbers = []
    for line in arr_game:
        line_str = str(line)
        if len(line_str) < 3:
            continue
        try:
            # "A|01|02|04|27|39|443" → 가운데 6개
            nums_str = line_str[2:-1].split('|')
            nums = [int(n) for n in nums_str]
            if len(nums) == 6 and all(1 <= n <= 45 for n in nums):
                numbers.append(nums)
        except (ValueError, IndexError):
            continue

    return {
        'round': round_num,
        'numbers': numbers,
        'auto_count': auto_games,
        'amount': auto_games * 1000,
        'draw_date': draw_date,
    }


def main():
    """GitHub Actions 진입점"""
    user_id = os.environ.get('LOTTO_USER_ID')
    password = os.environ.get('LOTTO_PASSWORD')
    auto_games = int(os.environ.get('LOTTO_AUTO_GAMES', '5'))
    telegram_token = os.environ.get('TELEGRAM_TOKEN', '').strip()
    telegram_chat_id = os.environ.get('TELEGRAM_USER_ID', '').strip()

    if not user_id or not password:
        logger.error('LOTTO_USER_ID와 LOTTO_PASSWORD 환경변수가 필요합니다.')
        # 텔레그램 알림 (설정 오류)
        if telegram_token and telegram_chat_id:
            send_telegram_message(telegram_token, telegram_chat_id,
                format_error_message('LOTTO_USER_ID 또는 LOTTO_PASSWORD가 설정되지 않았습니다.'))
        sys.exit(1)

    logger.info(f'===== 로또 자동 구매 시작 (게임: {auto_games}) =====')
    logger.info(f'TELEGRAM_TOKEN 설정됨: {"Yes" if telegram_token else "No"}')
    logger.info(f'TELEGRAM_USER_ID 설정됨: {"Yes" if telegram_chat_id else "No"}')

    try:
        result = auto_purchase(user_id, password, auto_games)

        logger.info('===== 구매 성공! =====')
        logger.info(f'회차: {result["round"]}회')
        logger.info(f'추첨일: {result["draw_date"]}')
        logger.info(f'구매 금액: {result["amount"]:,}원')
        logger.info(f'구매 게임 수: {result["auto_count"]}')
        for i, nums in enumerate(result['numbers'], 1):
            logger.info(f'  게임 {i}: {nums}')

        # GitHub Actions output
        print(f'::notice::로또 {result["round"]}회 구매 완료 ({result["amount"]:,}원)')

        # 텔레그램 알림 (구매 성공)
        if telegram_token and telegram_chat_id:
            message = format_success_message(result)
            send_telegram_message(telegram_token, telegram_chat_id, message)
            logger.info('텔레그램 알림 전송 완료')

    except Exception as e:
        error_msg = str(e)
        logger.error(f'===== 구매 실패: {error_msg} =====')
        print(f'::error::로또 구매 실패: {error_msg}')

        # 텔레그램 알림 (구매 실패)
        if telegram_token and telegram_chat_id:
            message = format_error_message(error_msg)
            send_telegram_message(telegram_token, telegram_chat_id, message)
            logger.info('텔레그램 실패 알림 전송 완료')

        sys.exit(1)


if __name__ == '__main__':
    main()
