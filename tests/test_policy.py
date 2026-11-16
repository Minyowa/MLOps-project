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


def test_redirect_to_trusted_site_is_not_flagged():
    # PR #10 리뷰: 넘어가는 곳이 공공·공식·평판 도메인이면 전달 링크 규칙을 건너뛴다
    from linkguard.policy import decide
    from linkguard.features import normalize
    rep = {"yahoo.co.jp", "nhk.or.jp", "facebook.com"}
    for u in ["https://www.google.com/url?q=https://www.yahoo.co.jp/",
              "https://www.facebook.com/sharer/sharer.php?u=https://www.nhk.or.jp/news",
              "https://www.nta.go.jp/?next=https://www.yahoo.co.jp"]:
        assert decide(normalize(u), 0.0, rep).stage != "open_redirect", u
    # 처음 보는 곳으로 넘기면 공공 도메인이라도 주의 (공공기관 전달 링크도 악용됨)
    assert decide(normalize("https://www.nta.go.jp/?next=https://example.com"), 0.0, rep).stage == "open_redirect"


def test_redirect_target_ignores_userinfo():
    from linkguard.policy import redirect_target
    from linkguard.features import normalize
    assert redirect_target(normalize("https://x.top/?u=https://www.naver.com@evil.top")) == "evil.top"


def test_short_common_words_are_not_impersonation():
    # PR #10 리뷰: visa·ana 같은 일반 단어와 겹치는 키워드로 정상 사이트가 사칭(0.9)이 되면 안 됨
    from linkguard.brands import impersonated_brand
    from linkguard.features import registered_domain
    for h in ["visa.vfsglobal.com", "jp-visa.info", "ana.hamburg.de", "ana-kitchen.jp", "banana-shop.jp"]:
        assert impersonated_brand(h, registered_domain(h)) is None, h
    assert impersonated_brand("ana-mileage.xyz", "ana-mileage.xyz") == "ANA"
