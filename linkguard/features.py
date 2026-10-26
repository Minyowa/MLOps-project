"""링크 정규화·규칙·설명 (학습·서빙 공용 — training-serving skew 방지).

정규화가 중요한 이유
  학습 데이터(2017년 수집)의 정상 링크는 전부 'https://', 'www.' 없이 경로가 붙은 형태로 저장돼 있다.
  사용자가 붙여 넣는 'https://www.naver.com' 을 그대로 쓰면 "학습 때 본 적 없는 모양"이라
  위험으로 오판한다. 그래서 학습과 서빙 모두 normalize()를 거친다.

모델 입력은 정규화된 주소의 글자 3~5개 조각(scripts/train.py)이다.
  아래 구조 피처(extract)는 v3' 실험에서 모델 입력으로 써 봤지만 최신 스미싱 탐지율이 더 낮아
  (0.530 vs 0.645) 채택하지 않았고, 지금은 사용자에게 보여 줄 위험 신호 설명(reasons)에만 쓴다.
"""
from __future__ import annotations

import math
import re

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_SHORTENERS = {"bit.ly", "goo.gl", "tinyurl.com", "t.co", "ow.ly", "is.gd", "buff.ly", "han.gl", "me2.do", "url.kr"}
SUSPICIOUS_WORDS = ("login", "signin", "verify", "account", "secure", "update", "confirm", "bank",
                    "paypal", "webscr", "ebayisapi", "wallet", "password", "free", "bonus", "admin", "wp-")
COMMON_TLDS = {"com", "org", "net", "edu", "gov", "kr", "jp", "uk", "de", "fr", "ca", "au", "us", "io"}
EXEC_EXT = re.compile(r"\.(exe|apk|scr|zip|rar|jar|bat|msi|dmg)(\?|$|/)", re.I)

FEATURE_NAMES = [
    "url_len", "host_len", "path_len", "n_dots", "n_hyphens", "n_slashes", "n_query_params",
    "n_at", "n_percent", "digit_ratio", "host_digits", "is_ip", "n_subdomains",
    "n_suspicious_words", "entropy", "tld_len", "common_tld", "exec_ext", "is_shortener", "has_port",
]


def normalize(url: str) -> str:
    """'https://www.Example.com' → 'example.com/' (호스트만 소문자, 경로 대소문자는 유지)."""
    u = str(url).strip()
    u = _SCHEME.sub("", u)
    m = re.search(r"[/?#]", u)
    host, sep, rest = (u[:m.start()], u[m.start()], u[m.start() + 1:]) if m else (u, "", "")
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if not sep:
        sep = "/"
    return f"{host}{sep}{rest}"


def host_of(norm_url: str) -> str:
    return re.split(r"[/?#]", norm_url, maxsplit=1)[0]


def registered_domain(host: str) -> str:
    """간이 버전: 마지막 두 마디 (co.kr 같은 2단계 TLD는 세 마디)."""
    h = host.split(":")[0]
    if _IPV4.match(h):
        return h
    parts = h.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "or", "ac", "go", "ne", "com", "org", "net"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(s.count(c) / n * math.log2(s.count(c) / n) for c in set(s)) if n else 0.0


def extract(url: str) -> dict[str, float]:
    u = normalize(url)
    host = host_of(u)
    hostname = host.split(":")[0]
    path = u[len(host):]
    tld = hostname.rsplit(".", 1)[-1] if "." in hostname else ""
    is_ip = bool(_IPV4.match(hostname))
    low = u.lower()
    return {
        "url_len": float(len(u)),
        "host_len": float(len(hostname)),
        "path_len": float(len(path)),
        "n_dots": float(u.count(".")),
        "n_hyphens": float(u.count("-")),
        "n_slashes": float(u.count("/")),
        "n_query_params": float(u.count("=")),
        "n_at": float(u.count("@")),
        "n_percent": float(u.count("%")),
        "digit_ratio": sum(c.isdigit() for c in u) / len(u),
        "host_digits": float(sum(c.isdigit() for c in hostname)),
        "is_ip": float(is_ip),
        "n_subdomains": 0.0 if is_ip else float(max(0, hostname.count(".") - registered_domain(hostname).count("."))),
        "n_suspicious_words": float(sum(w in low for w in SUSPICIOUS_WORDS)),
        "entropy": _entropy(u),
        "tld_len": float(len(tld)),
        "common_tld": float(tld in COMMON_TLDS),
        "exec_ext": float(bool(EXEC_EXT.search(path))),
        "is_shortener": float(registered_domain(hostname) in _SHORTENERS),
        "has_port": float(":" in host),
    }


OFFICIAL_SUFFIXES = (".go.kr", ".gov", ".mil", ".korea.kr")
OFFICIAL_EXACT = {"gov.kr", "korea.kr"}


def is_official(norm_url: str) -> bool:
    """개인이 등록할 수 없는 정부·공공 도메인. 모델 대신 규칙으로 '안전' 처리한다."""
    h = host_of(norm_url).split(":")[0]
    return h in OFFICIAL_EXACT or any(h.endswith(s) or h == s[1:] for s in OFFICIAL_SUFFIXES) \
        or any(h.endswith("." + e) for e in OFFICIAL_EXACT)


def load_reputable(path) -> set[str]:
    try:
        return {line.strip() for line in open(path, encoding="utf-8") if line.strip()}
    except FileNotFoundError:
        return set()


def redact(norm_url: str) -> str:
    """로그 저장용: 쿼리 값을 지운다 (전화번호·토큰 같은 개인정보가 섞일 수 있음)."""
    base, sep, query = norm_url.partition("?")
    if not sep:
        return base
    keys = [p.split("=", 1)[0] for p in query.split("&") if p]
    return base + "?" + "&".join(f"{k}=*" for k in keys)


def to_vector(feats: dict[str, float]) -> list[float]:
    return [feats[n] for n in FEATURE_NAMES]


def reasons(feats: dict[str, float]) -> list[str]:
    """사용자에게 보여 줄 '눈에 띄는 특징' (모델 판단의 보조 설명, 규칙 기반)."""
    r = []
    if feats["is_ip"]:
        r.append("사이트 이름 대신 IP 주소(숫자)로 된 링크예요")
    if feats["n_at"]:
        r.append("주소에 '@'가 있어요 — 앞부분을 무시하고 다른 사이트로 보내는 수법에 쓰여요")
    if feats["is_shortener"]:
        r.append("단축 URL이라 실제 목적지가 가려져 있어요")
    if feats["n_suspicious_words"]:
        r.append("로그인·계정 확인·보안 업데이트 같은 단어가 들어 있어요")
    if feats["exec_ext"]:
        r.append("파일 다운로드나 실행 스크립트(.apk, .exe 등)로 이어지는 링크예요")
    if feats["n_subdomains"] >= 3:
        r.append("하위 주소(점으로 구분된 마디)가 지나치게 많아요")
    if feats["host_digits"] >= 4:
        r.append("사이트 이름에 숫자가 많이 섞여 있어요")
    if not feats["common_tld"] and not feats["is_ip"]:
        r.append("흔하지 않은 도메인 끝자리예요")
    if feats["has_port"]:
        r.append("특수한 포트 번호를 지정한 링크예요")
    if feats["url_len"] >= 90:
        r.append("주소가 비정상적으로 길어요")
    return r
