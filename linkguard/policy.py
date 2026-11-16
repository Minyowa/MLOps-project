"""최종 판정 규칙 — API(app/main.py)와 평가 스크립트가 같은 함수를 쓴다.

순서
  0. 쿼리에 다른 사이트 주소를 품은 전달(리다이렉트) 링크이고, 넘어가는 곳이 믿을 수 있는 곳(1~3번)이 아니면
                                                          → 주의 이상 (모델 점수와 0.5 중 큰 값)
     예: cc.naver.com/cc?…&u=https://(피싱) — 공식 도메인이라도 안전 처리하지 않는다 (JPCERT 실제 사례)
     넘어가는 곳이 공공·공식·평판 도메인이면(google.com/url?q=https://www.yahoo.co.jp) 이 규칙은 건너뛴다
  1. 정부·공공 도메인 (.go.jp, .lg.jp, .go.kr …)          → 안전
  2. 주요 기관 공식 도메인 (brands.py, BRAND_REGION 기본 jp,kr)        → 안전
     (단, live.com처럼 사용자 콘텐츠를 올릴 수 있는 곳은 제외 → 모델)
  3. 평판 도메인 (인기 상위 1만 − 피싱 이력)              → 안전   (계열사 실제 사이트 보호)
  4. 기관 이름을 넣은 비공식 도메인 (사칭 의심)            → 위험 (모델 점수와 0.9 중 큰 값)
  5. 그 외                                               → 모델 점수

이유(reasons)는 코드로 돌려주고, 문장은 linkguard/i18n.py가 언어별로 만든다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from linkguard.brands import BRANDS, USER_CONTENT_HOSTS, impersonated_brand, official_brand
from linkguard.features import extract, host_of, is_official, reasons, registered_domain

IMPERSONATION_FLOOR = 0.9
REDIRECT_FLOOR = 0.5
_EMBEDDED_URL = re.compile(r"https?://([^/?#&\s]+)", re.I)


def redirect_target(norm_url: str) -> str | None:
    """쿼리 안에 다른 사이트 주소가 들어 있으면 그 호스트 (퍼센트 인코딩으로 숨긴 것도 푼다)."""
    _, sep, query = norm_url.partition("?")
    if not sep:
        return None
    m = _EMBEDDED_URL.search(unquote(unquote(query)))
    if not m:
        return None
    # https://www.naver.com@evil.top 처럼 '@' 앞은 꾸밈(사용자 정보)이고 실제 목적지는 뒤쪽
    target = m.group(1).lower().split("@")[-1].split(":")[0].removeprefix("www.")
    own = registered_domain(host_of(norm_url).split(":")[0])
    return target if registered_domain(target) != own else None


@dataclass
class Decision:
    risk: float
    stage: str
    reasons: list[dict] = field(default_factory=list)
    brand: str | None = None


def trusted_host(host: str, reputable: set[str]) -> bool:
    """공공 도메인, 주요 기관 공식 도메인, 평판 도메인(사용자 콘텐츠 호스팅 제외)."""
    dom = registered_domain(host)
    return (is_official(f"{host}/") or official_brand(dom) is not None
            or (dom in reputable and dom not in USER_CONTENT_HOSTS))


def decide(norm_url: str, model_risk: float, reputable: set[str]) -> Decision:
    hostname = host_of(norm_url).split(":")[0]
    dom = registered_domain(hostname)

    target = redirect_target(norm_url)
    if target and not trusted_host(target, reputable):
        return Decision(max(model_risk, REDIRECT_FLOOR), "open_redirect",
                        [{"code": "open_redirect", "target": target}] + reasons(extract(norm_url)))
    if is_official(norm_url):
        return Decision(0.0, "official_domain", [{"code": "official_domain"}])
    brand = official_brand(dom)
    if brand:
        return Decision(0.0, "official_brand", [{"code": "official_brand", "brand": brand}], brand)
    if dom in reputable and dom not in USER_CONTENT_HOSTS:
        return Decision(0.0, "reputable_domain", [{"code": "reputable_domain"}])
    fake = None if dom in USER_CONTENT_HOSTS else impersonated_brand(hostname, dom)
    if fake:
        official = ", ".join(BRANDS[fake]["domains"][:3])
        return Decision(max(model_risk, IMPERSONATION_FLOOR), "brand_impersonation",
                        [{"code": "brand_impersonation", "brand": fake, "official": official}]
                        + reasons(extract(norm_url)), fake)
    return Decision(model_risk, "model", reasons(extract(norm_url)))
