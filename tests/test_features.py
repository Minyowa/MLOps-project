import pytest

from linkguard.features import FEATURE_NAMES, extract, is_official, normalize, reasons, redact, registered_domain


@pytest.mark.parametrize("raw,norm", [
    ("https://www.naver.com", "naver.com/"),
    ("HTTP://WWW.Example.COM/Path?A=1", "example.com/Path?A=1"),
    ("naver.com", "naver.com/"),
    ("  https://a.b.co.kr/x  ", "a.b.co.kr/x"),
])
def test_normalize_removes_format_differences(raw, norm):
    assert normalize(raw) == norm


def test_registered_domain_handles_two_level_tld():
    assert registered_domain("news.naver.com") == "naver.com"
    assert registered_domain("a.b.co.kr") == "b.co.kr"
    assert registered_domain("10.0.0.1") == "10.0.0.1"


@pytest.mark.parametrize("url,official", [
    ("https://www.hometax.go.kr/websquare", True), ("gov.kr/portal", True), ("www.gov.kr", True),
    ("fake-gov.kr/login", False), ("gov.kr.evil.top/", False), ("go.kr-check.com/", False),
])
def test_official_domains(url, official):
    assert is_official(normalize(url)) is official


def test_redact_hides_query_values():
    assert redact("x.top/a?phone=01012345678&t=abc") == "x.top/a?phone=*&t=*"
    assert redact("x.top/a") == "x.top/a"


def test_reasons_for_obvious_signals():
    r = reasons(extract("http://192.168.0.1:8080/login/verify"))
    assert any("IP" in x for x in r) and any("로그인" in x for x in r) and any("포트" in x for x in r)
    assert set(extract("naver.com")) == set(FEATURE_NAMES)
