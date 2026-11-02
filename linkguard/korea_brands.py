"""한국에서 자주 사칭되는 기관의 공식 도메인 목록 (사람이 관리하는 목록).

용도
  1) 공식 도메인 → '안전' (예: 진짜 CJ대한통운 배송조회 페이지가 모델에서 0.97로 오판되던 문제 해결)
  2) 주소에 기관 이름이 들어 있는데 공식 도메인이 아님 → '사칭 의심' (예: cjlogistics-delivery.top)

키워드는 호스트를 '.'과 '-'로 나눈 조각 단위로 비교한다.
  - 7글자 이상 키워드: 조각이 키워드로 시작하면 맞음 (cjlogistics-delivery.top, shinhancard-pay.cc)
  - 6글자 이하 키워드: 조각이 정확히 같을 때만 (ibk → ibkr.com, toss → tossup.com, hanjin → hanjinshipping.com 은 안 맞음)
계열사 도메인이 사칭으로 잡히지 않도록, 평판 도메인 확인을 사칭 판정보다 먼저 한다(policy.py).

※ 목록은 출시 전 각 기관 공식 홈페이지에서 다시 확인하고, 사용자 신고 로그로 누락을 보완한다.
"""
from __future__ import annotations

import re

BRANDS: dict[str, dict] = {
    # 택배·물류
    "CJ대한통운": {"keywords": ["cjlogistics", "cjkorea", "doortodoor"],
                  "domains": ["cjlogistics.com", "cj.net", "doortodoor.co.kr"]},
    "우체국": {"keywords": ["epost", "koreapost"], "domains": ["epost.go.kr", "koreapost.go.kr"]},
    "롯데택배": {"keywords": ["lotteglogis"], "domains": ["lotteglogis.com"]},
    "한진택배": {"keywords": ["hanjin"], "domains": ["hanjin.com", "hanjin.co.kr"]},
    "로젠택배": {"keywords": ["ilogen"], "domains": ["ilogen.com"]},
    # 은행·카드·결제
    "KB국민": {"keywords": ["kbstar", "kbcard", "kbfg"], "domains": ["kbstar.com", "kbcard.com", "kbfg.com"]},
    "신한": {"keywords": ["shinhan"], "domains": ["shinhan.com", "shinhancard.com", "shinhansec.com", "shinhanlife.co.kr", "shinhangroup.com"]},
    "우리": {"keywords": ["wooribank", "wooricard", "woorifg"], "domains": ["wooribank.com", "wooricard.com", "woorifg.com"]},
    "하나": {"keywords": ["hanabank", "hanacard"], "domains": ["hanabank.com", "hanacard.co.kr", "hanafn.com"]},
    "NH농협": {"keywords": ["nonghyup"], "domains": ["nonghyup.com"]},
    "IBK기업은행": {"keywords": ["ibk"], "domains": ["ibk.co.kr"]},
    "삼성카드": {"keywords": ["samsungcard"], "domains": ["samsungcard.com"]},
    "현대카드": {"keywords": ["hyundaicard"], "domains": ["hyundaicard.com"]},
    "롯데카드": {"keywords": ["lottecard"], "domains": ["lottecard.co.kr"]},
    "BC카드": {"keywords": ["bccard"], "domains": ["bccard.com"]},
    "토스": {"keywords": ["toss", "tossbank", "tosspay"], "domains": ["toss.im", "tossbank.com", "tosspayments.com"]},
    "카카오": {"keywords": ["kakao", "kakaobank", "kakaopay", "kakaotalk"], "domains": ["kakao.com", "kakaocorp.com", "kakaobank.com", "kakaopay.com", "kakaopaysec.com"]},
    "네이버": {"keywords": ["naver", "naverpay"], "domains": ["naver.com", "naver.me", "navercorp.com"]},
    # 쇼핑
    "쿠팡": {"keywords": ["coupang"], "domains": ["coupang.com", "coupangeats.com", "coupangplay.com"]},
    # 통신
    "SK텔레콤": {"keywords": ["sktelecom", "tworld"], "domains": ["sktelecom.com", "tworld.co.kr"]},
    "LG유플러스": {"keywords": ["lguplus", "uplus"], "domains": ["lguplus.com", "uplus.co.kr"]},
    # 공공 (.go.kr은 정부 도메인 규칙으로도 처리됨)
    "국민건강보험": {"keywords": ["nhis"], "domains": ["nhis.or.kr"]},
    "홈택스": {"keywords": ["hometax"], "domains": ["hometax.go.kr"]},
    "정부24": {"keywords": ["gov24"], "domains": ["gov.kr"]},
}

OFFICIAL_TO_BRAND = {d: name for name, b in BRANDS.items() for d in b["domains"]}


def official_brand(registered_domain: str) -> str | None:
    return OFFICIAL_TO_BRAND.get(registered_domain)


def impersonated_brand(hostname: str, registered_domain: str) -> str | None:
    """호스트에 기관 키워드가 있는데 그 기관의 공식 도메인이 아니면 기관 이름을 돌려준다."""
    if registered_domain in OFFICIAL_TO_BRAND:
        return None
    tokens = [t for t in re.split(r"[.\-]", hostname.lower()) if t]
    for name, b in BRANDS.items():
        if any((t.startswith(k) if len(k) >= 7 else t == k) for t in tokens for k in b["keywords"]):
            return name
    return None
