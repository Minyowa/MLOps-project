"""학습 데이터 3종 내려받기 (모두 GitHub 공개 데이터).

1. data/urls.csv        2017년 무렵 정상·악성 URL 41만 건 (faizann24)
2. data/top100k.txt     인기 웹사이트 10만 개 도메인 (zer0h, Alexa 순위 기반) — 요즘 정상 사이트
3. data/jpcert/*.csv    JPCERT/CC가 확인한 실제 피싱 URL, 2019년~ 월별 파일

사용법: python scripts/download_data.py
"""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1] / "data"
SOURCES = {
    "urls.csv": "https://raw.githubusercontent.com/faizann24/Using-machine-learning-to-detect-malicious-URLs/master/data/data.csv",
    "top100k.txt": "https://raw.githubusercontent.com/zer0h/top-1000000-domains/master/top-100000-domains",
}
JPCERT = "https://raw.githubusercontent.com/JPCERTCC/phishurl-list/main/{y}/{y}{m:02d}.csv"


def fetch(url, dest):
    if dest.exists():
        return "있음"
    try:
        urlretrieve(url, dest)
        return "저장"
    except HTTPError as e:
        return f"없음({e.code})"


if __name__ == "__main__":
    (ROOT / "jpcert").mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        print(name, fetch(url, ROOT / name))
    got = 0
    for y in range(2019, 2027):
        for m in range(1, 13):
            if fetch(JPCERT.format(y=y, m=m), ROOT / "jpcert" / f"{y}{m:02d}.csv") in ("저장", "있음"):
                got += 1
    print(f"JPCERT 월별 파일 {got}개")
