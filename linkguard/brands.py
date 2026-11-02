"""자주 사칭되는 기관의 공식 도메인 목록 (사람이 관리하는 목록). 지역은 BRAND_REGION(jp/kr)으로 선택.

용도
  1) 공식 도메인 → '안전' (예: 진짜 택배 조회 페이지가 모델에서 위험으로 오판되던 문제 해결)
  2) 주소에 기관 이름이 들어 있는데 공식 도메인이 아님 → '사칭 의심' (예: smbc-card-login.top)

키워드 비교 (호스트를 '.'과 '-'로 나눈 조각 단위)
  - 7글자 이상: 조각이 키워드로 시작하면 맞음 (kuronekoyamato-delivery.top)
  - 6글자 이하: 조각이 정확히 같을 때만 (jcb → jcbfoods.com은 안 맞음)
  - '-'가 들어간 키워드(eki-net, etc-meisai): 호스트 안에 그대로 있으면 맞음
계열사 실제 사이트가 사칭으로 잡히지 않도록 평판 도메인 확인을 사칭 판정보다 먼저 한다(policy.py).

JP 목록은 JPCERT/CC 피싱 데이터에서 사칭 건수가 많은 브랜드(description 열) 위주로 골랐다.
※ 공식 도메인은 출시 전 각 기관 공식 사이트에서 재확인하고, 누락은 사용자 신고 로그로 보완한다.
"""
from __future__ import annotations

import os
import re

JP: dict[str, dict] = {
    # 쇼핑·플랫폼
    "Amazon": {"keywords": ["amazon"], "domains": [
        "amazon.co.jp", "amazon.com", "amazon.jp", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.fr",
        "amazon.it", "amazon.es", "amazon.in", "amazon.com.au", "amazon.com.br", "amazon.com.mx", "amazon.sg",
        "amazon.nl", "amazon.se", "amazon.pl", "amazon.ae", "amazon.sa", "amazon.com.tr", "amazon.cn",
        "images-amazon.com", "ssl-images-amazon.com"]},
    "楽天": {"keywords": ["rakuten"], "domains": ["rakuten.co.jp", "rakuten.com", "rakuten-card.co.jp",
                                                   "rakuten-bank.co.jp", "rakuten-sec.co.jp", "rakuten.ne.jp"]},
    "メルカリ": {"keywords": ["mercari"], "domains": ["mercari.com", "mercari.jp"]},
    "ヨドバシカメラ": {"keywords": ["yodobashi"], "domains": ["yodobashi.com"]},
    "Apple": {"keywords": ["apple", "appleid", "icloud"], "domains": ["apple.com", "icloud.com", "cdn-apple.com"]},
    "Microsoft": {"keywords": ["microsoft", "office365"], "domains": ["microsoft.com", "microsoftonline.com", "live.com", "office.com",
                                                                        "office365.com", "outlook.com"]},
    # 카드·결제
    "三井住友カード": {"keywords": ["smbc", "vpass", "smbccard"], "domains": ["smbc-card.com", "smbc.co.jp"]},
    "イオンカード": {"keywords": ["aeon", "aeoncard", "aeonbank"], "domains": ["aeon.co.jp", "aeon.com", "aeonbank.co.jp"]},
    "セゾンカード": {"keywords": ["saison", "saisoncard", "creditsaison", "credit-saison"],
                   "domains": ["saisoncard.co.jp", "saison.co.jp", "credit-saison.co.jp", "ins-saison.co.jp"]},
    "JCB": {"keywords": ["jcb", "myjcb"], "domains": ["jcb.co.jp", "jcb.jp"]},
    "エポスカード": {"keywords": ["epos", "eposcard"], "domains": ["eposcard.co.jp"]},
    "三菱UFJ": {"keywords": ["mufg", "nicos"], "domains": ["mufg.jp", "nicos.co.jp"]},
    "UCカード": {"keywords": ["uccard"], "domains": ["uccard.co.jp"]},
    "MICARD": {"keywords": ["micard"], "domains": ["micard.co.jp"]},
    "オリコ": {"keywords": ["orico"], "domains": ["orico.co.jp"]},
    "American Express": {"keywords": ["amex", "americanexpress"], "domains": ["americanexpress.com"]},
    "ビューカード": {"keywords": ["viewcard", "viewsnet"], "domains": ["viewsnet.jp", "jreast.co.jp"]},
    "PayPay": {"keywords": ["paypay"], "domains": ["paypay.ne.jp"]},
    # 은행·증권
    "みずほ銀行": {"keywords": ["mizuho", "mizuhobank"], "domains": ["mizuhobank.co.jp", "mizuho-fg.co.jp", "mizuho-sc.com"]},
    "JAバンク": {"keywords": ["jabank"], "domains": ["jabank.org"]},
    "マネックス証券": {"keywords": ["monex"], "domains": ["monex.co.jp"]},
    "SBI証券": {"keywords": ["sbisec"], "domains": ["sbisec.co.jp"]},
    "信用金庫": {"keywords": ["shinkin"], "domains": ["shinkin.co.jp"]},
    # 통신·생활
    "au/KDDI": {"keywords": ["kddi", "aupay", "au-pay"], "domains": ["au.com", "kddi.com"]},
    "NTTドコモ": {"keywords": ["docomo"], "domains": ["docomo.ne.jp"]},
    "ソフトバンク": {"keywords": ["softbank"], "domains": ["softbank.jp", "softbankbb.co.jp"]},
    "BIGLOBE": {"keywords": ["biglobe"], "domains": ["biglobe.ne.jp"]},
    "東京電力": {"keywords": ["tepco"], "domains": ["tepco.co.jp"]},
    "えきねっと": {"keywords": ["ekinet", "eki-net"], "domains": ["eki-net.com"]},
    "ETC利用照会サービス": {"keywords": ["etcmeisai", "etc-meisai"], "domains": ["etc-meisai.jp"]},
    # 택배
    "ヤマト運輸": {"keywords": ["kuroneko", "kuronekoyamato", "yamato"],
                 "domains": ["kuronekoyamato.co.jp", "yamato-hd.co.jp"]},
    "佐川急便": {"keywords": ["sagawa"], "domains": ["sagawa-exp.co.jp"]},
    "日本郵便": {"keywords": ["japanpost", "jppost"], "domains": ["japanpost.jp"]},
    # 공공 (.go.jp는 정부 도메인 규칙으로도 처리됨)
    "国税庁": {"keywords": ["nta", "e-tax"], "domains": ["nta.go.jp"]},
    "総務省": {"keywords": ["soumu"], "domains": ["soumu.go.jp"]},
}

KR: dict[str, dict] = {
    "CJ대한통운": {"keywords": ["cjlogistics", "cjkorea", "doortodoor"],
                  "domains": ["cjlogistics.com", "cj.net", "doortodoor.co.kr"]},
    "우체국": {"keywords": ["epost", "koreapost"], "domains": ["epost.go.kr", "koreapost.go.kr"]},
    "롯데택배": {"keywords": ["lotteglogis"], "domains": ["lotteglogis.com"]},
    "한진택배": {"keywords": ["hanjin"], "domains": ["hanjin.com", "hanjin.co.kr"]},
    "로젠택배": {"keywords": ["ilogen"], "domains": ["ilogen.com"]},
    "KB국민": {"keywords": ["kbstar", "kbcard", "kbfg"], "domains": ["kbstar.com", "kbcard.com", "kbfg.com"]},
    "신한": {"keywords": ["shinhan"], "domains": ["shinhan.com", "shinhancard.com", "shinhansec.com",
                                                 "shinhanlife.co.kr", "shinhangroup.com"]},
    "우리": {"keywords": ["wooribank", "wooricard", "woorifg"], "domains": ["wooribank.com", "wooricard.com", "woorifg.com"]},
    "하나": {"keywords": ["hanabank", "hanacard"], "domains": ["hanabank.com", "hanacard.co.kr", "hanafn.com"]},
    "NH농협": {"keywords": ["nonghyup"], "domains": ["nonghyup.com"]},
    "IBK기업은행": {"keywords": ["ibk"], "domains": ["ibk.co.kr"]},
    "삼성카드": {"keywords": ["samsungcard"], "domains": ["samsungcard.com"]},
    "현대카드": {"keywords": ["hyundaicard"], "domains": ["hyundaicard.com"]},
    "롯데카드": {"keywords": ["lottecard"], "domains": ["lottecard.co.kr"]},
    "BC카드": {"keywords": ["bccard"], "domains": ["bccard.com"]},
    "토스": {"keywords": ["toss", "tossbank", "tosspay"], "domains": ["toss.im", "tossbank.com", "tosspayments.com"]},
    "카카오": {"keywords": ["kakao", "kakaobank", "kakaopay", "kakaotalk"],
             "domains": ["kakao.com", "kakaocorp.com", "kakaobank.com", "kakaopay.com", "kakaopaysec.com"]},
    "네이버": {"keywords": ["naver", "naverpay"], "domains": ["naver.com", "naver.me", "navercorp.com"]},
    "쿠팡": {"keywords": ["coupang"], "domains": ["coupang.com", "coupangeats.com", "coupangplay.com"]},
    "SK텔레콤": {"keywords": ["sktelecom", "tworld"], "domains": ["sktelecom.com", "tworld.co.kr"]},
    "LG유플러스": {"keywords": ["lguplus", "uplus"], "domains": ["lguplus.com", "uplus.co.kr"]},
    "국민건강보험": {"keywords": ["nhis"], "domains": ["nhis.or.kr"]},
    "홈택스": {"keywords": ["hometax"], "domains": ["hometax.go.kr"]},
    "정부24": {"keywords": ["gov24"], "domains": ["gov.kr"]},
}

# 공식 도메인이지만 사용자가 페이지·문서를 올릴 수 있어 피싱이 실제로 올라간 곳 (JPCERT 데이터로 확인).
# '안전'으로 처리하지 않고 모델이 판단한다. 사칭 판정에서도 제외한다.
USER_CONTENT_HOSTS = {"live.com", "office.com", "outlook.com", "biglobe.ne.jp"}

REGIONS = {"jp": JP, "kr": KR}
REGION = os.getenv("BRAND_REGION", "jp").lower()
BRANDS: dict[str, dict] = REGIONS[REGION]
OFFICIAL_TO_BRAND = {d: name for name, b in BRANDS.items() for d in b["domains"]}


def official_brand(registered_domain: str) -> str | None:
    """공식 도메인이면 기관 이름. 단, 사용자 콘텐츠 호스팅 도메인은 None (모델이 판단)."""
    if registered_domain in USER_CONTENT_HOSTS:
        return None
    return OFFICIAL_TO_BRAND.get(registered_domain)


def _matches(keyword: str, hostname: str, tokens: list[str]) -> bool:
    if "-" in keyword:
        return keyword in hostname
    if len(keyword) >= 7:
        return any(t.startswith(keyword) for t in tokens)
    return keyword in tokens


def impersonated_brand(hostname: str, registered_domain: str) -> str | None:
    """호스트에 기관 키워드가 있는데 그 기관의 공식 도메인이 아니면 기관 이름을 돌려준다."""
    if registered_domain in OFFICIAL_TO_BRAND:
        return None
    h = hostname.lower()
    tokens = [t for t in re.split(r"[.\-]", h) if t]
    for name, b in BRANDS.items():
        if any(_matches(k, h, tokens) for k in b["keywords"]):
            return name
    return None
