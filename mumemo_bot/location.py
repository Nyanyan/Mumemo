from __future__ import annotations

import unicodedata


UNKNOWN_LOCATION = "不明"

PREFECTURES = [
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
]

PREFECTURE_ALIASES = {
    "北海道": "北海道",
    "東京": "東京都",
    "東京都": "東京都",
    "京都": "京都府",
    "京都府": "京都府",
    "大阪": "大阪府",
    "大阪府": "大阪府",
}
for _prefecture in PREFECTURES:
    PREFECTURE_ALIASES[_prefecture] = _prefecture
    if _prefecture.endswith("県"):
        PREFECTURE_ALIASES.setdefault(_prefecture[:-1], _prefecture)

LOCATION_KEYWORDS = [
    ("長崎県", ["長崎", "諫早", "大浦天主堂", "グラバー", "軍艦島", "出島", "爆心地", "平和祈念", "片島", "川棚"]),
    ("福井県", ["福井", "勝山", "恐竜博物館"]),
    ("新潟県", ["新潟", "糸魚川", "フォッサマグナ", "長者ケ原", "マリンピア日本海"]),
    ("石川県", ["石川", "金沢", "鼠多門", "しいのき", "水引", "自遊花人"]),
    ("富山県", ["富山", "高岡", "砺波", "となみ", "城端", "伏木", "瑞龍寺", "勝興寺", "越中", "チューリップ四季彩館", "イタイイタイ", "佐藤記念", "御車山"]),
    ("大分県", ["大分", "竹田", "滝廉太郎"]),
]

COUNTRY_KEYWORDS = [
    ("台湾", ["台湾", "台北", "台南", "高雄"]),
    ("韓国", ["韓国", "ソウル", "釜山"]),
    ("中国", ["中国", "北京", "上海"]),
    ("アメリカ", ["アメリカ", "米国", "ニューヨーク", "ワシントン"]),
    ("イギリス", ["イギリス", "英国", "ロンドン"]),
    ("フランス", ["フランス", "パリ"]),
    ("ドイツ", ["ドイツ", "ベルリン"]),
    ("イタリア", ["イタリア", "ローマ"]),
]


def normalize_location(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not normalized or normalized.casefold() in {"unknown", "none", "null", "-"}:
        return UNKNOWN_LOCATION
    if normalized in {"不明", "不詳", "未設定"}:
        return UNKNOWN_LOCATION
    return PREFECTURE_ALIASES.get(normalized, normalized)


def infer_location(title: str, body: str = "") -> str:
    title_text = unicodedata.normalize("NFKC", str(title or ""))
    body_text = unicodedata.normalize("NFKC", str(body or ""))

    for text in [title_text, body_text]:
        for prefecture in PREFECTURES:
            if prefecture in text:
                return prefecture

        for location, keywords in LOCATION_KEYWORDS:
            if any(keyword in text for keyword in keywords):
                return location

        for country, keywords in COUNTRY_KEYWORDS:
            if any(keyword in text for keyword in keywords):
                return country

    return UNKNOWN_LOCATION