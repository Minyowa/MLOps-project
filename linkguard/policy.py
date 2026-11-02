"""최종 판정 규칙 — API(app/main.py)와 평가 스크립트가 같은 함수를 쓴다.

순서
  1. 정부·공공 도메인 (.go.jp, .lg.jp, .go.kr …)          → 안전
  2. 주요 기관 공식 도메인 (brands.py, BRAND_REGION)        → 안전
     (단, live.com처럼 사용자 콘텐츠를 올릴 수 있는 곳은 제외 → 모델)
  3. 평판 도메인 (인기 상위 1만 − 피싱 이력)              → 안전   (계열사 실제 사이트 보호)
  4. 기관 이름을 넣은 비공식 도메인 (사칭 의심)            → 위험 (모델 점수와 0.9 중 큰 값)
  5. 그 외                                               → 모델 점수

이유(reasons)는 코드로 돌려주고, 문장은 linkguard/i18n.py가 언어별로 만든다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from linkguard.brands import BRANDS, USER_CONTENT_HOSTS, impersonated_brand, official_brand
from linkguard.features import extract, host_of, is_official, reasons, registered_domain

IMPERSONATION_FLOOR = 0.9


@dataclass
class Decision:
    risk: float
    stage: str
    reasons: list[dict] = field(default_factory=list)
    brand: str | None = None


def decide(norm_url: str, model_risk: float, reputable: set[str]) -> Decision:
    hostname = host_of(norm_url).split(":")[0]
    dom = registered_domain(hostname)

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
