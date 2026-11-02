"""한국 맞춤 판정 규칙 (linkguard/policy.py, korea_brands.py)."""
import pytest

from linkguard.features import host_of, normalize, registered_domain
from linkguard.korea_brands import impersonated_brand, official_brand
from linkguard.policy import decide


def brand_of(url):
    n = normalize(url)
    h = host_of(n)
    return official_brand(registered_domain(h)), impersonated_brand(h, registered_domain(h))


@pytest.mark.parametrize("url,brand", [
    ("https://www.cjlogistics.com/ko/tool/parcel/tracking", "CJ대한통운"),
    ("https://open.kakao.com/o/x", "카카오"), ("https://m.kakaobank.com", "카카오"),
    ("https://www.shinhanlife.co.kr", "신한"),
])
def test_official_brand_domains(url, brand):
    assert brand_of(url) == (brand, None)


@pytest.mark.parametrize("url,brand", [
    ("https://cjlogistics-delivery.top/kr", "CJ대한통운"), ("http://epost-kr.cfd/?info=x", "우체국"),
    ("https://kakaobank-login.top", "카카오"), ("https://naver.com.verify.top/login", "네이버"),
    ("https://shinhancard-pay.cc", "신한"), ("https://ibk-bank.xyz", "IBK기업은행"),
])
def test_impersonation_detected(url, brand):
    assert brand_of(url)[1] == brand


@pytest.mark.parametrize("url", ["https://ibkr.com", "https://tossup.com", "https://hanjinshipping.com",
                                 "https://mycjlogistics.com", "https://www.google.com"])
def test_short_keywords_do_not_overmatch(url):
    assert brand_of(url) == (None, None)


def test_decide_order():
    # 공식 기관 도메인은 모델 점수가 높아도 안전
    assert decide(normalize("https://www.cjlogistics.com/ko/tool"), 0.97, set()).stage == "official_brand"
    # 평판 도메인이 사칭 판정보다 먼저 (계열사 실제 사이트 보호)
    assert decide(normalize("https://kakaogames.com"), 0.6, {"kakaogames.com"}).stage == "reputable_domain"
    # 사칭은 모델 점수가 낮아도 최소 0.9
    d = decide(normalize("https://toss-event.shop"), 0.1, set())
    assert d.stage == "brand_impersonation" and d.risk == 0.9 and "토스" in d.reasons[0]
    # 정부 도메인
    assert decide(normalize("https://www.hometax.go.kr"), 0.99, set()).stage == "official_domain"
