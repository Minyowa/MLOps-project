"""판정 규칙 (linkguard/policy.py, brands.py) — 기본 지역 jp."""
import pytest

from linkguard.brands import USER_CONTENT_HOSTS, impersonated_brand, official_brand
from linkguard.features import host_of, normalize, registered_domain
from linkguard.i18n import MESSAGES, render
from linkguard.policy import decide


def brand_of(url):
    h = host_of(normalize(url))
    d = registered_domain(h)
    return official_brand(d), impersonated_brand(h, d)


@pytest.mark.parametrize("url,brand", [
    ("https://toi.kuronekoyamato.co.jp/cgi-bin/tneko", "ヤマト運輸"),
    ("https://www.smbc-card.com/mem/index.jsp", "三井住友カード"),
    ("https://www.post.japanpost.jp", "日本郵便"), ("https://www.bk.mufg.jp", "三菱UFJ"),
    ("https://www.amazon.co.uk", "Amazon"), ("https://www.eki-net.com", "えきねっと"),
])
def test_official_brand_domains(url, brand):
    assert brand_of(url) == (brand, None)


@pytest.mark.parametrize("url,brand", [
    ("https://kuronekoyamato-delivery.top/jp", "ヤマト運輸"), ("https://smbc-card-login.top/vpass", "三井住友カード"),
    ("https://amazon.co.jp.verify-account.xyz", "Amazon"), ("https://eki-net-pay.cc", "えきねっと"),
    ("https://etc-meisai.zuj74.com", "ETC利用照会サービス"), ("https://jcb-secure.shop", "JCB"),
])
def test_impersonation_detected(url, brand):
    assert brand_of(url)[1] == brand


@pytest.mark.parametrize("url", ["https://jcbfoods.com", "https://www.amazonia-travel.com",
                                 "https://www.google.co.jp", "https://news.yahoo.co.jp"])
def test_no_overmatch(url):
    assert brand_of(url) == (None, None)


def test_user_content_hosts_are_not_trusted():
    for d in USER_CONTENT_HOSTS:
        assert official_brand(d) is None
    assert decide(normalize("https://forms.office.com/r/abc"), 0.8, {"office.com"}).stage == "model"


def test_decide_order_and_messages():
    assert decide(normalize("https://toi.kuronekoyamato.co.jp/x"), 0.97, set()).stage == "official_brand"
    assert decide(normalize("https://www.city.yokohama.lg.jp"), 0.99, set()).stage == "official_domain"
    assert decide(normalize("https://kddi-research.jp"), 0.6, {"kddi-research.jp"}).stage == "reputable_domain"
    d = decide(normalize("https://jcb-secure.shop"), 0.1, set())
    assert d.stage == "brand_impersonation" and d.risk == 0.9 and d.brand == "JCB"
    assert "JCB" in render(d.reasons[0], "ja") and "사칭" in render(d.reasons[0], "ko")


def test_i18n_tables_have_same_keys():
    assert set(MESSAGES["ja"]) == set(MESSAGES["ko"])


def test_open_redirect_on_official_domain_is_not_safe():
    # JPCERT 실제 사례: 네이버 공식 도메인의 전달 링크로 피싱 사이트에 보냄 (주소를 퍼센트 인코딩으로 숨김)
    from linkguard.policy import decide
    from linkguard.features import normalize
    u = normalize("https://cc.naver.com/cc?a=pst.link&u=https://%6C%65%6E%64%69%6E%61%62%6F%78.%63%6F%6D/x")
    d = decide(u, 0.0, {"naver.com"})
    assert d.stage == "open_redirect" and d.risk >= 0.5 and d.reasons[0]["target"] == "lendinabox.com"
    # 같은 사이트 안으로 넘기는 링크는 해당 없음
    assert decide(normalize("https://www.google.com/url?q=https://maps.google.com/x"), 0.0, {"google.com"}).stage == "reputable_domain"


def test_japan_and_korea_rules_both_on_by_default():
    from linkguard.brands import BRANDS, REGION
    assert REGION == "jp,kr" and "ヤマト運輸" in BRANDS and "CJ대한통운" in BRANDS
