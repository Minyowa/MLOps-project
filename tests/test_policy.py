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
