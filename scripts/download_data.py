"""NSMC(네이버 영화 리뷰 20만 건) 내려받기.

출처: https://github.com/e9t/nsmc (CC0 1.0)
사용법: python scripts/download_data.py
"""
from pathlib import Path
from urllib.request import urlretrieve

BASE = "https://raw.githubusercontent.com/e9t/nsmc/master/"
OUT = Path(__file__).resolve().parents[1] / "data"

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name in ("ratings_train.txt", "ratings_test.txt"):
        dest = OUT / f"nsmc_{name.split('_')[1]}"
        if dest.exists():
            print(f"이미 있음: {dest}")
            continue
        urlretrieve(BASE + name, dest)
        print(f"저장: {dest}")
