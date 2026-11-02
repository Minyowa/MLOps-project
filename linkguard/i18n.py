"""판정 이유 코드 → 사용자 문장 (ja: 일본어 기본, ko: 한국어)."""
from __future__ import annotations

MESSAGES = {
    "ja": {
        "official_domain": "政府・公的機関専用のドメインです（個人は登録できません）",
        "official_brand": "{brand}の公式ドメインです",
        "reputable_domain": "多くの人が利用しているサイトです（人気上位1万・フィッシング履歴なし）。ただし、サイト内の投稿やチャットの内容までは保証できません",
        "brand_impersonation": "{brand}をかたった偽のアドレスの可能性があります。{brand}の公式アドレス: {official}",
        "ip_host": "サイト名ではなくIPアドレス（数字）のリンクです",
        "at_sign": "アドレスに「@」が含まれています。前の部分を無視して別のサイトへ送る手口に使われます",
        "shortener": "短縮URLのため、実際の行き先が隠れています",
        "suspicious_words": "ログイン・アカウント確認・セキュリティ更新などの単語が含まれています",
        "executable": "ファイルのダウンロードや実行ファイル（.apk、.exe など）につながるリンクです",
        "many_subdomains": "サブドメイン（点で区切られた部分）が多すぎます",
        "digits_in_host": "サイト名に数字が多く含まれています",
        "rare_tld": "あまり使われないドメインの末尾です",
        "port": "特殊なポート番号を指定したリンクです",
        "long_url": "アドレスが異常に長いです",
    },
    "ko": {
        "official_domain": "정부·공공기관 전용 도메인이에요 (개인이 등록할 수 없음)",
        "official_brand": "{brand} 공식 도메인이에요",
        "reputable_domain": "많은 사람이 쓰는 사이트예요 (인기 상위 1만, 피싱 이력 없음). 단, 사이트 안의 글·채팅 내용까지 보장하지는 않아요",
        "brand_impersonation": "{brand}을(를) 사칭한 주소일 수 있어요. {brand} 공식 주소: {official}",
        "ip_host": "사이트 이름 대신 IP 주소(숫자)로 된 링크예요",
        "at_sign": "주소에 '@'가 있어요 — 앞부분을 무시하고 다른 사이트로 보내는 수법에 쓰여요",
        "shortener": "단축 URL이라 실제 목적지가 가려져 있어요",
        "suspicious_words": "로그인·계정 확인·보안 업데이트 같은 단어가 들어 있어요",
        "executable": "파일 다운로드나 실행 파일(.apk, .exe 등)로 이어지는 링크예요",
        "many_subdomains": "하위 주소(점으로 구분된 마디)가 지나치게 많아요",
        "digits_in_host": "사이트 이름에 숫자가 많이 섞여 있어요",
        "rare_tld": "흔하지 않은 도메인 끝자리예요",
        "port": "특수한 포트 번호를 지정한 링크예요",
        "long_url": "주소가 비정상적으로 길어요",
    },
}
LANGS = tuple(MESSAGES)


def render(reason: dict, lang: str = "ja") -> str:
    table = MESSAGES.get(lang, MESSAGES["ja"])
    params = {k: v for k, v in reason.items() if k != "code"}
    return table[reason["code"]].format(**params)
