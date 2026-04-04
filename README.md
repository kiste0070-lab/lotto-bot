# 로또 자동 구매 (GitHub Actions)

동행복권 로또 6/45를 매주 자동으로 구매하는 스크립트입니다.

## 설정 방법

### 1. Repository Secrets 설정

GitHub Repository > Settings > Secrets and variables > Actions에서 다음을 추가하세요:

| Secret | 설명 |
|--------|------|
| `LOTTO_USER_ID` | 동행복권 아이디 |
| `LOTTO_PASSWORD` | 동행복권 비밀번호 |
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_USER_ID` | 텔레그램 채팅 ID |

### 2. 실행 스케줄

- **자동**: 매주 금요일 09:00 KST (토요일 추첨 전)
- **수동**: Actions 탭 > "Run workflow" 버튼

### 3. 구매 설정

`.github/workflows/auto_lotto.yml`에서 `LOTTO_AUTO_GAMES` 변경:

```yaml
env:
  LOTTO_AUTO_GAMES: '5'  # 1~5 게임 (게임당 1,000원)
```

## 주의사항

- 동행복권 계정에 **예치금 충전**이 되어 있어야 합니다
- 구매 가능 시간: 평일/일요일 06:00~23:59, 토요일 06:00~19:59
- 금요일 실행이 실패하면 토요일 오전에 수동으로 `workflow_dispatch`를 실행하세요

## 면책 조항

이 스크립트는 동행복권의 공식 서비스가 아니며, 사용에 따른 모든 책임은 사용자에게 있습니다.
