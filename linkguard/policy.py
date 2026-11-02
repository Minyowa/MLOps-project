"""최종 판정 규칙 — API(app/main.py)와 평가 스크립트가 같은 함수를 쓴다.

순서
  1. 정부·공공 도메인 (.go.kr, gov.kr …)                → 안전
  2. 한국 주요 기관 공식 도메인 (korea_brands.py)         → 안전
  3. 평판 도메인 (인기 상위 1만 − 피싱 이력)              → 안전   (계열사 실제 사이트 보호)
  4. 기관 이름을 넣은 비공식 도메인 (사칭 의심)            → 위험 (모델 점수와 0.9 중 큰 값)
  5. 그 외                                               → 모델 점수
"""
from __future__ import annotations

from dataclasses import dataclass, field

from linkguard.features import extract, host_of, is_official, reasons, registered_domain
from linkguard.korea_brands import BRANDS, impersonated_brand, official_brand

IMPERSONATION_FLOOR = 0.9


@dataclass
class Decision:
    risk: float
    stage: str
    reasons: list[str] = field(default_factory=list)


def decide(norm_url: str, model_risk: float, reputable: set[str]) -> Decision:
    hostname = host_of(norm_url).split(":")[0]
    dom = registered_domain(hostname)

    if is_official(norm_url):
        return Decision(0.0, "official_domain", ["정부·공공기관 전용 도메인이에요 (개인이 등록할 수 없음)"])
    brand = official_brand(dom)
    if brand:
        return Decision(0.0, "official_brand", [f"{brand} 공식 도메인이에요"])
    if dom in reputable:
        return Decision(0.0, "reputable_domain", [
            "많은 사람이 쓰는 사이트예요 (인기 상위 1만, 피싱 이력 없음). 단, 사이트 안의 글·채팅 내용까지 보장하지는 않아요"])
    fake = impersonated_brand(hostname, dom)
    if fake:
        official = ", ".join(BRANDS[fake]["domains"])
        return Decision(max(model_risk, IMPERSONATION_FLOOR), "brand_impersonation",
                        [f"{fake}을(를) 사칭한 주소일 수 있어요. {fake} 공식 주소: {official}"]
                        + reasons(extract(norm_url)))
    return Decision(model_risk, "model", reasons(extract(norm_url)))
