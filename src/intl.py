"""海外向けページ（英語・中国語繁体字・韓国語）
日本のポケカ・ワンピースカードの発売日・BOX相場・高額カード・日本での買い方を、/en/ /zh-tw/ /ko/ に書き出す。
抽選情報は載せない（海外の人は応募できないため。2026/11/7 ユーザー指示）。
データは日本語サイトと同じもの（souba.json＝スニダンの取引相場、souba_cards.json、弾の発売日情報）を使う。
11/7 各国のSEO調査をもとに改良：現地の検索語（日版・일판・Japanese booster box）、弾コード、公式の現地名・英語版の対応、
現地通貨（NT$・HK$・원）、現地の日付の書き方、OG・構造化データ・hreflang（zh-TW / zh-HK）、NAVER向けの短いタイトル。
"""
import json
import re
import datetime as _dt
from html import escape
from pathlib import Path
from urllib.parse import quote

LANGS = {
    "en": {"html": "en", "name": "English", "og": "en_US", "hreflang": ["en"]},
    "zh-tw": {"html": "zh-Hant", "name": "繁體中文", "og": "zh_TW", "hreflang": ["zh-Hant", "zh-TW", "zh-HK"]},
    "ko": {"html": "ko", "name": "한국어", "og": "ko_KR", "hreflang": ["ko"]},
}

# ---- 弾の情報：コード・日本版の英語名・英語版で対応する弾・繁体字の公式名・韓国語の公式名 ----
# 公式名は調査で確かめられたものだけ（2026/11/7）。わからないものは空にして、日本語名＋コードで出す
# (code, en_name, en_counterpart, zh, ko)
SETS = {
    "pokemon": {
        "ハドウシーカー": ("M7", "Aura Seeker", "Flowing Fists", "波導探求者", ""),
        "スペシャルデッキセットMEGA": ("", "Special Deck Set MEGA", "", "", ""),
        "30周年御三家カードセット": ("", "30th Anniversary Starter Card Set", "", "", ""),
        "30th CELEBRATION": ("M6a", "30th CELEBRATION", "30th Celebration", "30th CELEBRATION", ""),
        "30周年 FUTURISTIC BOX": ("", "30th CELEBRATION FUTURISTIC BOX", "", "", ""),
        "30周年エーフィ・ブラッキーデッキ": ("", "30th Premium Deck Set Espeon & Umbreon", "", "", ""),
        "ストームエメラルダ": ("M6", "Storm Emeralda", "Delta Reign", "綠寶石風暴", "스톰에메랄다"),
        "スターターセットex": ("", "Starter Set ex", "", "", ""),
        "アビスアイ": ("M5", "Abyss Eye", "Pitch Black", "深淵之瞳", ""),
        "ニンジャスピナー": ("M4", "Ninja Spinner", "Chaos Rising", "忍者飛旋", "닌자스피너"),
        "ムニキスゼロ": ("M3", "Nihil Zero", "Perfect Order", "虛無歸零", ""),
        "MEGAドリームex": ("M2a", "MEGA Dream ex", "Ascended Heroes", "超級進化夢想ex", "MEGA 드림 ex"),
        "インフェルノX": ("M2", "Inferno X", "Phantasmal Flames", "烈獄狂火X", "인페르노X"),
        "メガブレイブ": ("M1L", "Mega Brave", "", "", ""),
        "メガシンフォニア": ("M1S", "Mega Symphonia", "", "", ""),
        "ブラックボルト": ("SV11B", "Black Bolt", "", "", ""),
        "ホワイトフレア": ("SV11W", "White Flare", "", "", ""),
        "ロケット団の栄光": ("SV10", "Glory of Team Rocket", "", "", ""),
        "熱風のアリーナ": ("SV9a", "Heat Wave Arena", "", "", ""),
        "バトルパートナーズ": ("SV9", "Battle Partners", "", "", ""),
        "テラスタルフェスex": ("SV8a", "Terastal Festival ex", "Prismatic Evolutions", "太晶慶典ex", "테라스탈 페스타 ex"),
        "超電ブレイカー": ("SV8", "Super Electric Breaker", "", "", ""),
        "楽園ドラゴーナ": ("SV7a", "Paradise Dragona", "", "", ""),
        "ステラミラクル": ("SV7", "Stellar Miracle", "", "", ""),
        "ナイトワンダラー": ("SV6a", "Night Wanderer", "", "", ""),
        "変幻の仮面": ("SV6", "Mask of Change", "", "", ""),
        "クリムゾンヘイズ": ("SV5a", "Crimson Haze", "", "", ""),
        "ワイルドフォース": ("SV5K", "Wild Force", "", "", ""),
        "サイバージャッジ": ("SV5M", "Cyber Judge", "", "", ""),
        "シャイニートレジャーex": ("SV4a", "Shiny Treasure ex", "", "", ""),
        "古代の咆哮": ("SV4K", "Ancient Roar", "", "", ""),
        "未来の一閃": ("SV4M", "Future Flash", "", "", ""),
        "レイジングサーフ": ("SV3a", "Raging Surf", "", "", ""),
        "黒炎の支配者": ("SV3", "Ruler of the Black Flame", "", "", ""),
        "ポケモンカード151": ("SV2a", "Pokémon Card 151", "Scarlet & Violet—151", "寶可夢卡牌151", "포켓몬 카드 151"),
        "スノーハザード": ("SV2P", "Snow Hazard", "", "", ""),
        "クレイバースト": ("SV2D", "Clay Burst", "", "", ""),
        "トリプレットビート": ("SV1a", "Triplet Beat", "", "", ""),
        "スカーレットex": ("SV1S", "Scarlet ex", "", "", ""),
        "バイオレットex": ("SV1V", "Violet ex", "", "", ""),
        "VSTARユニバース": ("S12a", "VSTAR Universe", "Crown Zenith", "", "VSTAR 유니버스"),
        "パラダイムトリガー": ("S12", "Paradigm Trigger", "", "", ""),
        "白熱のアルカナ": ("S11a", "Incandescent Arcana", "", "", ""),
        "ロストアビス": ("S11", "Lost Abyss", "", "", ""),
        "ダークファンタズマ": ("S10a", "Dark Phantasma", "", "", ""),
        "スペースジャグラー": ("S10P", "Space Juggler", "", "", ""),
        "タイムゲイザー": ("S10D", "Time Gazer", "", "", ""),
        "ポケモンGO": ("S10b", "Pokémon GO", "", "", ""),
        "バトルリージョン": ("S9a", "Battle Region", "", "", ""),
        "スターバース": ("S9", "Star Birth", "", "", ""),
        "VMAXクライマックス": ("S8b", "VMAX Climax", "", "", ""),
        "25th ANNIVERSARY COLLECTION": ("S8a", "25th ANNIVERSARY COLLECTION", "", "", ""),
        "フュージョンアーツ": ("S8", "Fusion Arts", "", "", ""),
        "蒼空ストリーム": ("S7R", "Blue Sky Stream", "", "", ""),
        "摩天パーフェクト": ("S7D", "Skyscraping Perfection", "", "", ""),
        "イーブイヒーローズ": ("S6a", "Eevee Heroes", "Evolving Skies", "伊布英雄", "이브이 히어로즈"),
        "白銀のランス": ("S6H", "Silver Lance", "", "", ""),
        "漆黒のガイスト": ("S6K", "Jet-Black Spirit", "", "", ""),
        "双璧のファイター": ("S5a", "Matchless Fighters", "", "", ""),
        "一撃マスター": ("S5I", "Single Strike Master", "", "", ""),
        "連撃マスター": ("S5R", "Rapid Strike Master", "", "", ""),
        "シャイニースターV": ("S4a", "Shiny Star V", "", "", ""),
        "仰天のボルテッカー": ("S4", "Amazing Volt Tackle", "", "", ""),
        "伝説の鼓動": ("S3a", "Legendary Heartbeat", "", "", ""),
        "ムゲンゾーン": ("S3", "Infinity Zone", "", "", ""),
        "爆炎ウォーカー": ("S2a", "Explosive Walker", "", "", ""),
        "反逆クラッシュ": ("S2", "Rebellion Crash", "", "", ""),
        "タッグオールスターズ": ("SM12a", "Tag Team GX All Stars", "", "", ""),
        "ドリームリーグ": ("SM11b", "Dream League", "", "", ""),
        "リミックスバウト": ("SM11a", "Remix Bout", "", "", ""),
        "ダブルブレイズ": ("SM10", "Double Blaze", "", "", ""),
        "タッグボルト": ("SM9", "Tag Bolt", "", "", ""),
        "裂空のカリスマ": ("SM7", "Sky-Splitting Charisma", "", "", ""),
        "20th Anniversary": ("CP6", "20th Anniversary", "", "", ""),
    },
    "onepiece": {
        "応答せよ、世界": ("OP-19", "OP-19", "", "", ""),
        "EAST BLUE": ("EB-06", "EAST BLUE", "", "", ""),
        "神の支配": ("OP-18", "The Dominance of God", "The Dominance of God", "", ""),
        "ヒロインズエディション vol.2": ("EB-05", "Heroines Edition vol.2", "Heroines Edition vol.2", "", ""),
        "HEROINES PRECIOUS BOX": ("", "HEROINES PRECIOUS BOX", "", "", ""),
        "世界最強の戦士": ("OP-17", "The World's Strongest Warriors", "The World's Strongest Warriors", "世界最強的戰士", ""),
        "決戦の刻": ("OP-16", "The Time of Battle", "The Time of Battle", "", ""),
        "神の島の冒険": ("OP-15", "Adventure on Kami's Island", "Adventure on Kami's Island", "", ""),
        "蒼海の七傑": ("OP-14", "The Azure Sea's Seven", "The Azure Sea's Seven", "", ""),
        "受け継がれる意志": ("OP-13", "Carrying On His Will", "Carrying On His Will", "", ""),
        "師弟の絆": ("OP-12", "Legacy of the Master", "Legacy of the Master", "", ""),
        "神速の拳": ("OP-11", "A Fist of Divine Speed", "A Fist of Divine Speed", "", ""),
        "王族の血統": ("OP-10", "Royal Blood", "Royal Blood", "", ""),
        "新たなる皇帝": ("OP-09", "Emperors in the New World", "Emperors in the New World", "", ""),
        "二つの伝説": ("OP-08", "Two Legends", "Two Legends", "", ""),
        "500年後の未来": ("OP-07", "500 Years in the Future", "500 Years in the Future", "", ""),
        "双璧の覇者": ("OP-06", "Wings of the Captain", "Wings of the Captain", "", ""),
        "新時代の主役": ("OP-05", "Awakening of the New Era", "Awakening of the New Era", "", ""),
        "謀略の王国": ("OP-04", "Kingdoms of Intrigue", "Kingdoms of Intrigue", "", ""),
        "強大な敵": ("OP-03", "Pillars of Strength", "Pillars of Strength", "", ""),
        "頂上決戦": ("OP-02", "Paramount War", "Paramount War", "", ""),
        "ロマンスドーン": ("OP-01", "Romance Dawn", "Romance Dawn", "", ""),
        "メモリアルコレクション": ("EB-01", "Memorial Collection", "Memorial Collection", "", ""),
        "アニメ25thコレクション": ("EB-02", "Anime 25th Collection", "Anime 25th Collection", "", ""),
        "ヒロインズエディション": ("EB-03", "Heroines Edition", "Heroines Edition", "", ""),
        "EGGHEAD CRISIS": ("EB-04", "EGGHEAD CRISIS", "EGGHEAD CRISIS", "", ""),
        "ONE PIECE CARD THE BEST": ("PRB-01", "ONE PIECE CARD THE BEST", "ONE PIECE CARD THE BEST", "", ""),
        "ONE PIECE CARD THE BEST vol.2": ("PRB-02", "ONE PIECE CARD THE BEST vol.2", "ONE PIECE CARD THE BEST vol.2", "", ""),
    },
}

# 各国の発売日（調べて確かめられたものだけ。11/7）。en＝英語版（対応する弾）、tw＝台湾・香港の繁体字版、kr＝韓国版
LOCAL_REL = {
    "pokemon": {
        "ハドウシーカー": {"en": "2027-02-05", "tw": "2026-12-04"},
        "30th CELEBRATION": {"en": "2026-09-16", "tw": "2026-09-16"},
        "ストームエメラルダ": {"en": "2026-11-06", "tw": "2026-08-07", "kr": "2026-08-21"},
        "アビスアイ": {"en": "2026-07-17", "tw": "2026-06-05"},
        "ニンジャスピナー": {"en": "2026-05-22", "tw": "2026-03-27", "kr": "2026-05-01"},
        "ムニキスゼロ": {"en": "2026-03-27", "tw": "2026-02-06"},
        "MEGAドリームex": {"en": "2026-01-30", "tw": "2025-12-05", "kr": "2026-01-23"},
        "インフェルノX": {"en": "2025-11-14", "tw": "2025-10-09", "kr": "2025-11-28"},
        "テラスタルフェスex": {"en": "2025-01-17", "tw": "2024-12-20", "kr": "2025-01-22"},
        "ポケモンカード151": {"en": "2023-09-22"},
        "VSTARユニバース": {"en": "2023-01-20"},
        "イーブイヒーローズ": {"en": "2021-08-27", "tw": "2021-06-11", "kr": "2021-08-11"},
    },
    "onepiece": {
        "神の支配": {"en": "2026-11-20"},
        "ヒロインズエディション vol.2": {"en": "2026-10-30"},
        "世界最強の戦士": {"en": "2026-08-28"},
        "決戦の刻": {"en": "2026-06-12"},
    },
}

# カード名の中の日本語（キャラ名・レアリティの説明）→ 英語。長いものから順に置き換える
CARD_EN = {
    "モンキー・D・ルフィ": "Monkey.D.Luffy", "ポートガス・D・エース": "Portgas.D.Ace", "ゴール・D・ロジャー": "Gol.D.Roger", "サボ": "Sabo",
    "ロックス・D・ジーベック": "Rocks.D.Xebec", "マーシャル・D・ティーチ": "Marshall.D.Teach", "トニートニー・チョッパー": "Tony Tony.Chopper",
    "ロロノア・ゾロ": "Roronoa Zoro", "シャンクス": "Shanks", "ボア・ハンコック": "Boa Hancock", "バギー": "Buggy", "ボルサリーノ": "Borsalino",
    "クザン": "Kuzan", "ニコ・ロビン": "Nico Robin", "サンジ": "Sanji", "ナミ": "Nami", "ヤマト": "Yamato", "カイドウ": "Kaido", "ビッグ・マム": "Big Mom",
    "シャーロット・リンリン": "Charlotte Linlin", "トラファルガー・ロー": "Trafalgar Law", "ユースタス・キッド": "Eustass Kid", "ウタ": "Uta",
    "白ひげ": "Whitebeard", "エドワード・ニューゲート": "Edward.Newgate", "イム": "Imu", "ネフェルタリ・ビビ": "Nefeltari Vivi", "レイジュ": "Reiju",
    "ミュウツー": "Mewtwo", "ミュウ": "Mew", "レックウザ": "Rayquaza", "ブラッキー": "Umbreon", "エーフィ": "Espeon", "ニンフィア": "Sylveon",
    "グレイシア": "Glaceon", "リーフィア": "Leafeon", "イーブイ": "Eevee", "ラティアス&ラティオス": "Latias & Latios", "ピカチュウ": "Pikachu",
    "Mリザードン": "M Charizard", "リザードン": "Charizard", "ギラティナ": "Giratina", "ルチア": "Lisia", "ルギア": "Lugia", "ゲンガー": "Gengar",
    "カイリュー": "Dragonite", "オーダイル": "Feraligatr", "フシギバナ": "Venusaur", "カメックス": "Blastoise", "ナンジャモ": "Iono", "リーリエ": "Lillie",
    "マリィ": "Marnie", "シロナ": "Cynthia", "テラパゴス": "Terapagos", "ミモザ": "Miriam", "セレナ": "Serena", "アセロラ": "Acerola",
    "ゲッコウガ": "Greninja", "メガゲッコウガ": "Mega Greninja", "レシラム": "Reshiram", "ゼクロム": "Zekrom",
    "レッドコミパラ": "Red Manga Alt Art", "コミパラ": "Manga Alt Art", "海賊団スーパーパラレル": "Pirates Super Parallel",
    "3周年スペシャルカード": "3rd Anniversary Special", "金背景": "Gold", "銀背景": "Silver", "サインルフィ": "Signed Luffy",
    "レッド": "Red", "ブルー": "Blue", "グリーン": "Green", "（": " (", "）": ")",
}

WEEK = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "zh-tw": "一二三四五六日", "ko": "월화수목금토일"}

T = {
    "en": {
        "site": "Japan TCG Navi", "home": "Home", "releases": "JP Release Dates", "box": "JP Box Prices", "cards": "Top JP Cards",
        "buy": "Buy in Japan", "pokemon": "Pokémon TCG (Japanese)", "onepiece": "ONE PIECE Card Game (Japanese)",
        "release": "JP release", "msrp": "MSRP", "price": "Japan price", "x": "vs MSRP", "chg": "30d", "trend": "90-day trend",
        "us": "US (TCGplayer)", "set": "Set", "card": "Card", "upcoming": "Upcoming Japanese releases",
        "movers": "Japanese booster box prices", "hot": "Most expensive Japanese cards right now", "more": "See all",
        "ebay": "eBay", "amazon": "Amazon", "updated": "Updated", "unreleased": "Coming soon", "counterpart": "English set", "ln_jp": "Japanese box in Japan", "ln_us": "Japanese box in the US", "ln_en": "English version", "ln_kr": "Korean version", "ln_tw": "Chinese (TW/HK) version", "etb": "Elite Trainer Box", "chart": "Price chart: Japan vs US vs English, Korean & Chinese versions", "chart_note": "All lines converted to {unit} at today's exchange rate. Japan = SNKRDUNK sold prices; US and English version = TCGplayer market price; Korean and Chinese versions = eBay listing prices.", "set_title": "{name} ({code}) Japanese Booster Box Price & Chart", "set_h1": "{name} ({code}) Japanese Box Price", "set_desc": "{name} {code} Japanese booster box price in Japan: {jp} ({local}), MSRP {msrp}. Chart comparing the Japan price, the US price of the Japanese box and the English version.", "no_local": "", "jprel": "🇯🇵 Japan", "enrel": "🇺🇸 English", "twrel": "", "krrel": "", "tba": "TBA",
        "local": "", "sources": "Sources & notes",
        "src": "Japan prices are the latest sold prices of sealed boxes and ungraded single cards on SNKRDUNK, a major Japanese marketplace (not asking prices). Release dates and MSRP come from the official Japanese Pokémon Card Game and ONE PIECE Card Game websites. Exchange rate: $1 = ¥{fx} ({fxd}); converted prices are approximate.",
        "names": "Set names: the Japanese set's English name and code are shown first; \"English set\" is the international English-language release with the same cards where one exists.",
        "aff": "This site contains affiliate links (Amazon Associates, eBay Partner Network). We may earn a commission at no extra cost to you.",
    },
    "zh-tw": {
        "site": "日本卡牌情報站", "home": "首頁", "releases": "日版發售日", "box": "日版卡盒價格", "cards": "日版高價單卡",
        "buy": "日本購買攻略", "pokemon": "寶可夢卡牌 PTCG（日版）", "onepiece": "航海王卡牌 ONE PIECE CARD GAME（日版）",
        "release": "日版發售", "msrp": "建議售價", "price": "日本市價", "x": "定價倍數", "chg": "30日", "trend": "90日走勢",
        "us": "美國（TCGplayer）", "set": "系列", "card": "單卡", "upcoming": "即將發售的日版新彈",
        "movers": "日版卡盒（補充包盒）價格", "hot": "日本目前最貴的單卡", "more": "看全部",
        "ebay": "eBay", "amazon": "Amazon", "updated": "更新", "unreleased": "即將發售", "counterpart": "英文版", "ln_jp": "日版・日本市價", "ln_us": "日版・美國市價", "ln_en": "英文版", "ln_kr": "韓文版", "ln_tw": "繁中版", "etb": "訓練家寶箱", "chart": "價格走勢：日版 vs 英文版 vs 韓文版 vs 繁中版", "chart_note": "所有線條以今天的匯率換算成{unit}。日本＝SNKRDUNK成交價；美國與英文版＝TCGplayer市價；韓文版與繁中版＝eBay刊登價。", "set_title": "{name}（{code}）日版卡盒價格・走勢圖", "set_h1": "{name}（{code}）日版卡盒價格", "set_desc": "{name} {code} 日版卡盒日本市價{jp}（{local}），建議售價{msrp}。比較日本市價、美國的日版價格與英文版價格的走勢圖。", "no_local": "繁中版的價格取自eBay的刊登價，台灣當地的價格可能不同。資料從2026年11月起每天累積。", "jprel": "🇯🇵 日版", "enrel": "🇺🇸 英文版", "twrel": "🇹🇼 繁中版", "krrel": "", "tba": "未公布",
        "local": "繁中版", "sources": "資料來源與說明",
        "src": "日本市價為日本大型交易平台 SNKRDUNK 上未拆封卡盒與未鑑定單卡的最新成交價（非掛牌價）。發售日與建議售價來自日本寶可夢卡牌與航海王卡牌官方網站。匯率：1美元＝{fx}日圓（{fxd}），換算金額僅供參考。",
        "names": "系列名稱：先列出日版的英文名稱與系列代碼，「繁中版」為台灣・香港發售的官方中文名稱，「英文版」為收錄相同卡片的國際英文版系列（若有）。",
        "aff": "本站含有聯盟行銷連結（Amazon Associates、eBay Partner Network），您透過連結購買時我們可能獲得佣金，不會增加您的費用。",
    },
    "ko": {
        "site": "재팬 TCG 내비", "home": "홈", "releases": "일판 발매일", "box": "일판 박스 시세", "cards": "일판 고가 카드",
        "buy": "일본 구매 가이드", "pokemon": "포켓몬 카드 게임 (일판)", "onepiece": "원피스 카드 게임 (일판)",
        "release": "일본 발매", "msrp": "정가", "price": "일본 시세", "x": "정가 대비", "chg": "30일", "trend": "90일 추이",
        "us": "미국 (TCGplayer)", "set": "세트", "card": "카드", "upcoming": "곧 발매되는 일판 신규 세트",
        "movers": "일판 부스터 박스 시세", "hot": "지금 일본에서 가장 비싼 카드", "more": "전체 보기",
        "ebay": "eBay", "amazon": "Amazon", "updated": "업데이트", "unreleased": "발매 예정", "counterpart": "영문판", "ln_jp": "일판 일본 시세", "ln_us": "일판 미국 시세", "ln_en": "영문판 시세", "ln_kr": "한글판 시세", "ln_tw": "중문판(대만) 시세", "etb": "엘리트 트레이너 박스", "chart": "시세 차트: 일판 vs 한글판 vs 영문판 vs 중문판", "chart_note": "모든 선은 오늘 환율로 {unit} 환산. 일본=SNKRDUNK 실거래가, 미국・영문판=TCGplayer 시세, 한글판・중문판=eBay 판매가.", "set_title": "{name} ({code}) 일판 박스 시세 차트", "set_h1": "{name} ({code}) 일판 박스 시세", "set_desc": "{name} {code} 일판 박스 일본 시세 {jp}({local}), 정가 {msrp}. 일본 시세・미국 일판 시세・영문판 시세 비교 차트.", "no_local": "한글판 시세는 eBay 판매가 기준이라 국내(번개장터・크림 등) 시세와 다를 수 있습니다. 2026년 11월부터 매일 쌓아 갑니다.", "jprel": "🇯🇵 일판", "enrel": "🇺🇸 영문판", "twrel": "", "krrel": "🇰🇷 한글판", "tba": "미정",
        "local": "한글판", "sources": "출처 및 안내",
        "src": "일본 시세는 일본 대형 거래 플랫폼 SNKRDUNK(스니덩)에서 미개봉 박스와 미감정 싱글 카드가 실제로 거래된 최근 가격입니다(호가 아님). 발매일과 정가는 일본 포켓몬 카드 게임・원피스 카드 게임 공식 사이트 기준입니다. 환율: 1달러 = {fx}엔({fxd}), 환산 금액은 참고용입니다.",
        "names": "세트 이름: 일판의 영어 이름과 세트 코드를 먼저 표시하고, '한글판'은 한국 정식 발매명, '영문판'은 같은 카드가 수록된 해외 영문판 세트입니다(있는 경우).",
        "aff": "이 사이트에는 제휴 링크(Amazon Associates, eBay Partner Network)가 포함되어 있으며, 링크를 통해 구매하시면 추가 비용 없이 수수료를 받을 수 있습니다.",
    },
}

# ページごとのタイトル・説明（調査した現地の検索語に合わせる。韓国語はNAVER向けにタイトル40字・説明80字以内）
META = {
    "en": {
        "home": ("Japanese Pokémon Card Prices & Release Dates (Japan Data)", "Japanese Pokémon & One Piece Card Prices and Release Dates from Japan",
                 "Live Japan-market prices for Japanese Pokémon and One Piece booster boxes, the most expensive Japanese cards, and the JP release calendar with MSRP and USD."),
        "releases": ("Japanese Pokémon TCG Release Dates {y}–{y1} + One Piece", "Japanese Pokémon TCG & One Piece Release Dates {y}–{y1}",
                     "Every Japanese set release date with MSRP in yen, set code and its English counterpart: {ex}"),
        "box": ("Japanese Pokémon Booster Box Prices Today (Japan Market)", "Japanese Booster Box Prices Today",
                "Current sealed Japanese booster box prices in Japan vs MSRP, multiple, 30-day change, USD and TCGplayer US price for 151 (SV2a), Terastal Festival ex (SV8a), MEGA Dream ex (M2a) and more."),
        "cards": ("Most Expensive Japanese Pokémon & One Piece Cards Now", "Most Expensive Japanese Cards Right Now",
                  "Top Japanese Pokémon and One Piece single cards by current Japan market price, with card number, set, yen and USD."),
        "buy": ("How to Buy Pokémon Cards in Japan: Tourist & Online Guide", "How to Buy Pokémon Cards in Japan",
                "Where to buy Japanese Pokémon cards at MSRP in Tokyo, Pokémon Center lotteries, the new tax-free refund system, purchase limits, and buying Japanese boxes from overseas."),
    },
    "zh-tw": {
        "home": ("日版寶可夢卡牌價格與發售日｜PTCG日本情報", "日版寶可夢卡牌・航海王卡牌 日本市價與發售日",
                 "日本當地日版寶可夢卡盒行情、最值錢單卡排行與日版發售日曆，附日圓定價與約NT$、HK$換算，每天更新。"),
        "releases": ("日版寶可夢卡牌發售日曆{y}-{y1}（含航海王）", "日版寶可夢卡牌・航海王卡牌 發售日曆",
                     "日版擴充包發售日、日圓建議售價、系列代碼與繁中版／英文版對照：{ex}"),
        "box": ("日版寶可夢卡盒價格行情：日本市價・定價倍數", "日版寶可夢卡盒（補充包盒）價格行情",
                "SNKRDUNK日本成交價vs建議售價、倍數、30日漲跌、約NT$／HK$與美國TCGplayer價格：151（SV2a）、太晶慶典ex（SV8a）、超級進化夢想ex（M2a）等。"),
        "cards": ("日版寶可夢・航海王最值錢單卡排行（日本行情）", "日本目前最貴的日版單卡排行",
                  "日本市場日版寶可夢卡牌・航海王卡牌單卡高價排行，附卡號、系列、日圓與約NT$價格，每天更新。"),
        "buy": ("日本買寶可夢卡攻略：寶可夢中心・抽選・免稅・代購", "到日本買日版寶可夢卡的方法",
                "到日本怎麼用原價買日版寶可夢卡：寶可夢中心與電器行、抽選、限購、2026年11月起的新免稅（退稅）制度，以及海外代購與直送。"),
    },
    "ko": {
        "home": ("일본판 포켓몬카드 시세·발매일 | 일본 현지 정보", "일판 포켓몬카드·원피스 카드 일본 시세와 발매일",
                 "일본 현지 일판 포켓몬카드 박스 시세, 고가 카드 순위, 일본 발매일과 정가(엔·원 환산). 매일 업데이트."),
        "releases": ("일본판 포켓몬카드 발매일 {y}-{y1} (원피스 포함)", "일판 포켓몬카드·원피스 카드 발매일",
                     "일본 확장팩 발매일·정가·세트 코드와 한글판/영문판 대응: {ex}"),
        "box": ("일본판 포켓몬카드 박스 시세 (일본 현지가)", "일판 포켓몬카드 박스 시세",
                "SNKRDUNK 일본 실거래가와 정가 배수, 30일 변동, 원·달러 환산, 미국 TCGplayer 가격. 151, 테라스탈 페스타 ex 등."),
        "cards": ("일본에서 가장 비싼 일판 카드 순위", "일본에서 가장 비싼 일판 카드 순위",
                  "일본 시장 기준 고가 일판 포켓몬카드·원피스 카드 순위. 카드 번호, 세트, 엔화·원화 시세. 매일 업데이트."),
        "buy": ("일본 포켓몬카드 구매 가이드: 포켓몬센터·추첨·면세", "일본에서 일판 포켓몬카드 사는 방법",
                "일본 여행 중 정가로 사는 법, 포켓몬센터·추첨, 구매 제한, 2026년 11월부터 바뀐 면세(환급) 제도, 해외 직구·구매대행."),
    },
}

LEAD = {
    "en": {
        "home": "Japan gets new Pokémon TCG and ONE PIECE Card Game sets first — often months before the English release. Track Japanese release dates and what sealed boxes and cards actually sell for in Japan, updated every day.",
        "releases": "Release dates, MSRP and set codes of upcoming and recent Japanese Pokémon TCG and ONE PIECE Card Game products, with the matching English set.",
        "box": "What sealed Japanese booster boxes are actually selling for in Japan today, compared with the official retail price (MSRP).",
        "cards": "The highest recent sold prices of Japanese single cards in Japan (ungraded).",
        "buy": "",
    },
    "zh-tw": {
        "home": "寶可夢卡牌與航海王卡牌的新彈都在日本最先發售，繁中版通常晚2〜8週。這裡每天更新日版發售日，以及日版卡盒、單卡在日本的實際成交價。",
        "releases": "日版寶可夢卡牌・航海王卡牌新彈的發售日、日圓建議售價與系列代碼，並對照繁中版與英文版名稱。",
        "box": "日版未拆封卡盒（補充包盒）目前在日本的實際成交價，與建議售價（定價）的比較。想代購或等繁中版前可以先參考。",
        "cards": "日本近期成交價最高的日版單卡（未鑑定・裸卡）。",
        "buy": "",
    },
    "ko": {
        "home": "포켓몬 카드 게임과 원피스 카드 게임의 신규 세트는 일본에서 가장 먼저 발매되며, 한글판은 보통 1.5〜3개월 뒤에 나옵니다. 일판 발매일과 미개봉 박스・카드의 일본 실거래 시세를 매일 업데이트합니다.",
        "releases": "일판 포켓몬 카드・원피스 카드 신규 세트의 발매일, 정가(엔), 세트 코드와 한글판・영문판 대응 세트를 정리했습니다.",
        "box": "일판 미개봉 부스터 박스가 지금 일본에서 실제로 거래되는 가격과 정가 비교입니다. 직구・구매대행 전에 참고하세요.",
        "cards": "최근 일본에서 실제로 거래된 일판 싱글 카드 최고가입니다(미감정).",
        "buy": "",
    },
}

TYPE_T = {  # 商品の種類
    "拡張パック": {"en": "Expansion pack", "zh-tw": "擴充包", "ko": "확장팩"},
    "強化拡張パック": {"en": "Enhanced expansion pack", "zh-tw": "強化擴充包", "ko": "강화 확장팩"},
    "ハイクラスパック": {"en": "High-class pack", "zh-tw": "高級擴充包", "ko": "하이클래스 팩"},
    "構築デッキ": {"en": "Deck", "zh-tw": "牌組", "ko": "덱"},
    "プレミアムデッキセット": {"en": "Premium deck set", "zh-tw": "高級牌組", "ko": "프리미엄 덱 세트"},
    "カードセット": {"en": "Card set", "zh-tw": "卡片組", "ko": "카드 세트"},
    "スターターセットex": {"en": "Starter set", "zh-tw": "入門組", "ko": "스타터 세트"},
    "公認店限定": {"en": "Official store exclusive", "zh-tw": "公認店限定", "ko": "공인점 한정"},
    "ブースターパック": {"en": "Booster pack", "zh-tw": "補充包", "ko": "부스터 팩"},
    "エクストラブースター": {"en": "Extra booster", "zh-tw": "額外補充包", "ko": "엑스트라 부스터"},
}

BUY = {  # 日本での買い方ガイド（固定の文章）。2026/11/1 からの免税制度の変更も反映
    "en": [
        ("When do new Japanese sets come out?", "Japanese Pokémon sets are usually released on a Friday, and ONE PIECE sets on a Saturday. Check the release calendar on this site — Japan is usually several months ahead of the English release."),
        ("Pokémon Center stores", "The official Pokémon Center stores (Tokyo, Osaka, Kyoto and more) sell new sets on release day, but popular sets often sell out within hours or are sold only by lottery (抽選) to members with a Japanese address and phone number. Check the store's official X account the day before."),
        ("Electronics stores, convenience stores and bookstores", "Yodobashi, Bic Camera, Yamada and bookstores sell new sets at MSRP, but in-demand products are mostly sold by lottery. Convenience stores (7-Eleven, FamilyMart, Lawson) sometimes have packs on release day, usually limited to a few packs per person."),
        ("Card shops in Akihabara, Nipponbashi and Nakano", "Specialist card shops sell singles and sealed boxes, usually above MSRP for popular sets. Compare shops — the box price table on this site shows what boxes actually sell for in Japan, so you can tell a fair price."),
        ("Tax-free shopping changed on November 1, 2026", "Japan switched to a refund system: you pay the full price including tax in the store, and the tax is refunded when you leave Japan after customs confirms your purchases (scan your passport at the tax-free terminal before check-in). You need to spend at least ¥5,000 (before tax) per store per day, keep the items unopened, and complete it within 90 days."),
        ("Watch out for resealed boxes", "Only buy sealed boxes from reputable shops. Japanese boxes have shrink wrap printed with the official logo; avoid boxes with loose or unbranded wrap."),
        ("Buying from overseas", "If you can't visit Japan, Japanese sealed boxes are widely sold on eBay and Amazon by importers. Compare the seller's price with the Japan price on this site plus shipping and import duties."),
    ],
    "zh-tw": [
        ("日版新彈什麼時候發售？", "日版寶可夢卡牌新彈通常在星期五發售，航海王卡牌通常在星期六。繁中版一般晚2〜8週。請參考本站的發售日曆。"),
        ("寶可夢中心", "官方寶可夢中心（東京、大阪、京都等）會在發售日販售新彈，但熱門系列常在幾小時內售完，或只以抽選方式賣給有日本地址與電話的會員。建議前一天先看各店的官方X帳號。"),
        ("電器行・超商・書店", "Yodobashi、Bic Camera、Yamada等電器行與書店以原價販售新彈，但熱門商品大多是抽選。7-ELEVEN、全家、LAWSON等超商發售日偶爾會有卡包，通常每人限購數包。"),
        ("秋葉原・日本橋・中野的卡牌專賣店", "專賣店有單卡與未拆封卡盒，熱門系列多半高於建議售價。可以多比較幾家，本站的卡盒價格表是日本的實際成交價，可以判斷價格是否合理。"),
        ("2026年11月1日起免稅改為「退稅制」", "日本的免稅制度改為先付含稅價格、出境時退稅：在店裡照含稅價付款，離境時在機場報到前用護照在免稅手續機器完成海關確認後退還消費稅。同一家店同一天需購買稅前5,000日圓以上，商品不可拆封使用，並須在購買後90天內辦理。"),
        ("小心重新封膜的卡盒", "請在可信賴的店家購買未拆封卡盒。日版卡盒的收縮膜上印有官方標誌，封膜鬆弛或沒有標誌的請避免購買。"),
        ("從台灣・香港購買日版", "無法到日本時，可以透過代購、蝦皮或eBay、Amazon的海外賣家購買日版卡盒。請用本站的日本市價加上運費與關稅，判斷價格是否合理。"),
    ],
    "ko": [
        ("일판 신규 세트는 언제 나오나요?", "일판 포켓몬 카드는 보통 금요일, 원피스 카드는 보통 토요일에 발매됩니다. 한글판은 대개 1.5〜3개월 뒤에 나옵니다. 이 사이트의 발매일 캘린더를 확인하세요."),
        ("포켓몬센터", "공식 포켓몬센터(도쿄, 오사카, 교토 등)에서 발매일에 신규 세트를 판매하지만, 인기 세트는 몇 시간 만에 품절되거나 일본 주소와 전화번호가 있는 회원 대상 추첨으로만 판매되는 경우가 많습니다. 전날 각 매장의 공식 X 계정을 확인하세요."),
        ("가전 양판점・편의점・서점", "요도바시, 빅카메라, 야마다 등 가전 양판점과 서점은 정가로 판매하지만, 인기 상품은 대부분 추첨입니다. 세븐일레븐, 패밀리마트, 로손 등 편의점에도 발매일에 팩이 들어오기도 하며, 보통 1인당 몇 팩으로 제한됩니다."),
        ("아키하바라・닛폰바시・나카노의 카드 전문점", "전문점에서는 싱글 카드와 미개봉 박스를 판매하며, 인기 세트는 보통 정가보다 비쌉니다. 여러 매장을 비교해 보세요. 이 사이트의 박스 시세표는 일본 실거래가라서 적정 가격을 판단할 수 있습니다."),
        ("2026년 11월 1일부터 면세가 '환급 방식'으로 변경", "일본의 면세 제도가 바뀌어, 매장에서는 세금 포함 가격을 내고 출국할 때 환급받습니다. 공항에서 체크인 전에 면세 절차 단말기에 여권을 스캔해 세관 확인을 받으면 소비세가 환급됩니다. 같은 매장에서 하루 5,000엔(세전) 이상 구매해야 하며, 상품은 개봉하지 말고 구매 후 90일 이내에 절차를 마쳐야 합니다."),
        ("재포장 박스 주의", "미개봉 박스는 신뢰할 수 있는 매장에서만 구매하세요. 일판 박스의 수축 포장에는 공식 로고가 인쇄되어 있으며, 포장이 헐겁거나 로고가 없는 박스는 피하세요."),
        ("한국에서 일판 구매하기 (직구・구매대행)", "일본에 가지 않는다면 구매대행이나 eBay, Amazon의 해외 판매자를 통해 일판 박스를 직구할 수 있습니다. 이 사이트의 일본 시세에 배송비와 관세를 더해 가격이 적당한지 판단하세요."),
    ],
}

PAGES = [("", "home"), ("releases/", "releases"), ("box-prices/", "box"), ("card-prices/", "cards"), ("buy-in-japan/", "buy")]

CSS = """:root{--bg:#f6f7fb;--card:#fff;--ink:#14161f;--ink2:#5b6070;--line:#e3e6ee;--acc:#c8102e;--up:#0a8a4a;--dn:#c8102e}
@media (prefers-color-scheme:dark){:root{--bg:#12141b;--card:#1b1e28;--ink:#eef0f6;--ink2:#a3a8b8;--line:#2c3040}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Noto Sans",sans-serif}
a{color:var(--acc)}header{background:var(--card);border-bottom:1px solid var(--line)}.w{max-width:960px;margin:0 auto;padding:0 16px}
.top{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0;flex-wrap:wrap}.logo{font-weight:900;font-size:19px;color:var(--ink);text-decoration:none}
.lang a{margin-left:10px;font-size:13px;color:var(--ink2)}.lang a[aria-current]{color:var(--ink);font-weight:800}
nav.tabs{display:flex;gap:4px;overflow-x:auto;padding-bottom:8px}nav.tabs a{white-space:nowrap;font-size:14px;padding:6px 10px;border-radius:999px;text-decoration:none;color:var(--ink2);background:var(--bg)}
nav.tabs a[aria-current]{background:var(--acc);color:#fff;font-weight:700}
.crumb{font-size:12px;color:var(--ink2);margin:12px 0 0}.crumb a{color:var(--ink2)}
main{padding:8px 0 40px}h1{font-size:26px;line-height:1.3;margin:6px 0 8px}h2{font-size:19px;margin:28px 0 10px;border-left:4px solid var(--acc);padding-left:10px}
.lead{color:var(--ink2);margin:0 0 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--ink2);background:var(--bg)}
td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.jp{display:block;font-size:12px;color:var(--ink2)}
.code{display:inline-block;font-size:11px;font-weight:800;padding:0 6px;border-radius:4px;background:#14161f;color:#fff;margin-left:6px;vertical-align:1px}
.up{color:var(--up);font-weight:700}.dn{color:var(--dn);font-weight:700}.buy{display:block;margin-top:4px}.buy a{display:inline-block;font-size:12px;font-weight:700;margin:2px 4px 2px 0;padding:3px 8px;border-radius:6px;text-decoration:none}
.b-eb{background:#0064d2;color:#fff}.b-az{background:#ffd814;color:#111}.tw{overflow-x:auto}.note{font-size:12px;color:var(--ink2)}
.spark{display:block;margin-top:4px}.spark path{fill:none;stroke:var(--ink2);stroke-width:1.5}
.rel{display:flex;gap:12px;align-items:baseline;border-bottom:1px solid var(--line);padding:10px 0}.rel:last-child{border-bottom:0}.rel time{font-weight:800;min-width:118px}.rel .g{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--bg);color:var(--ink2);margin-right:6px}
.soon{font-size:11px;font-weight:700;color:#fff;background:var(--acc);border-radius:4px;padding:1px 6px;margin-left:6px}
.rl{display:block;font-size:12px;font-weight:700;color:var(--ink);margin-top:2px}.rl:empty{display:none}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}.chart svg{width:100%;height:auto;font-size:11px;fill:var(--ink2)}
.leg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;margin:6px 4px}.leg i{display:inline-block;width:14px;height:4px;border-radius:2px;margin-right:6px;vertical-align:middle}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin:12px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.stat small{display:block;font-size:12px;color:var(--ink2)}.stat b{display:block;font-size:20px}.stat span{font-size:12px;color:var(--ink2)}
.src{font-size:12px;color:var(--ink2)}.src p{margin:0 0 8px}
footer{border-top:1px solid var(--line);padding:20px 0 40px;font-size:12px;color:var(--ink2)}
@media (max-width:600px){.hide-s{display:none}h1{font-size:22px}.rel{flex-direction:column;gap:2px}.rel time{min-width:0}}"""


def _last(d):
    if not d:
        return None, None
    k = max(d)
    return d[k], k


def _ago(d, days):
    if not d:
        return None
    k = max(d)
    lim = (_dt.date.fromisoformat(k) - _dt.timedelta(days=days)).isoformat()
    ks = [x for x in d if x <= lim]
    return d[max(ks)] if ks else None


def set_info(g, x):
    """(コード, 日本版の英語名, 英語版の弾, 繁中名, 韓国名)"""
    return SETS.get(g, {}).get(x) or ("", x, "", "", "")


def set_slug(g, x):
    """弾ページのアドレス（例 pokemon-m7-aura-seeker）"""
    code, en = set_info(g, x)[:2]
    base = f"{code} {en}" if code and code.lower() not in en.lower() else en
    sl = re.sub(r"[^a-z0-9]+", "-", re.sub(r"[éÉ]", "e", base.lower())).strip("-")
    import hashlib
    return f"{'pokemon' if g == 'pokemon' else 'one-piece'}-{sl or hashlib.md5(x.encode()).hexdigest()[:8]}"


def set_name(g, x):
    return set_info(g, x)[1] or x


def card_name(label):
    s = label
    for k in sorted(CARD_EN, key=len, reverse=True):
        s = s.replace(k, CARD_EN[k])
    s = re.sub(r"\s*:\s*", " · ", s).strip()
    s = re.sub(r"([a-z])(VMAX|VSTAR|GX|EX|V)\b", r"\1 \2", s)
    return s if not re.search(r"[぀-ヿ]", s) else ""


def fmt_date(L, iso):
    d = _dt.date.fromisoformat(iso)
    w = WEEK[L][d.weekday()]
    if L == "en":
        return f"{d.strftime('%b')} {d.day}, {d.year} ({w})"
    if L == "zh-tw":
        return f"{d.year}/{d.month:02d}/{d.day:02d}（{w}）"
    return f"{d.year}년 {d.month}월 {d.day}일({w})"


def _spark(series, days=90):
    """日本の相場の90日の折れ線（小さなSVG）"""
    if not series:
        return ""
    k = max(series)
    lim = (_dt.date.fromisoformat(k) - _dt.timedelta(days=days)).isoformat()
    pts = sorted((d, v) for d, v in series.items() if d >= lim and v)
    if len(pts) < 4:
        return ""
    vs = [v for _, v in pts]
    lo, hi = min(vs), max(vs)
    w, h = 96, 22
    xs = [i * (w - 2) / (len(pts) - 1) + 1 for i in range(len(pts))]
    ys = [h - 2 - ((v - lo) / (hi - lo) * (h - 4) if hi > lo else (h - 4) / 2) for v in vs]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true"><path d="{d}"/></svg>'


def build_intl(out, s, souba_raw, card_raw, info, site, today):
    """海外向けページを書き出して、サイトマップ用の [(URL, 日付)] を返す"""
    fx = souba_raw.get("fx") or 150
    fxu = souba_raw.get("fx_usd") or {}
    fxd = str(souba_raw.get("checked") or today.isoformat())
    jpy_per = {"USD": fx}
    for c in ("TWD", "HKD", "KRW"):
        if fxu.get(c) and fxu.get("JPY"):
            jpy_per[c] = fxu["JPY"] / fxu[c]
    items = souba_raw.get("items") or {}
    az_tag = (s.get("intl_amazon_tag") or "").strip()
    ebay = (s.get("ebay_campid") or "").strip()
    naver = (s.get("naver_site_verification") or "").strip()
    urls = []
    tdy = today.isoformat()
    rel_a = 'target="_blank" rel="nofollow sponsored noopener"'

    def money(L, yen):
        """日本円のあとに、その国の人に分かりやすい通貨で「約〇〇」"""
        if L == "en":
            return f"≈ ${yen / fx:,.0f}"
        if L == "zh-tw":
            out_ = []
            if jpy_per.get("TWD"):
                out_.append(f"約NT${yen / jpy_per['TWD']:,.0f}")
            if jpy_per.get("HKD"):
                out_.append(f"HK${yen / jpy_per['HKD']:,.0f}")
            return " / ".join(out_) or f"約US${yen / fx:,.0f}"
        if jpy_per.get("KRW"):
            w = yen / jpy_per["KRW"]
            return f"약 {w / 10000:,.1f}만원" if w >= 10000 else f"약 {w:,.0f}원"
        return f"약 ${yen / fx:,.0f}"

    def ebay_url(q):
        u = f"https://www.ebay.com/sch/i.html?_nkw={quote(q)}"
        if ebay:
            u += f"&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={quote(ebay)}&toolid=10001&mkevt=1"
        return u

    def amz_url(q):
        return f"https://www.amazon.com/s?k={quote(q)}" + (f"&tag={quote(az_tag)}" if az_tag else "")

    def buy_btns(g, x, t):
        code = set_info(g, x)[0]
        q = f"Japanese {'Pokemon' if g == 'pokemon' else 'One Piece'} {set_name(g, x)} {code} booster box".replace("  ", " ")
        return (f'<span class="buy"><a class="b-eb" href="{escape(ebay_url(q))}" {rel_a}>{t["ebay"]}</a>'
                f'<a class="b-az" href="{escape(amz_url(q))}" {rel_a}>{t["amazon"]}</a></span>')

    def names_html(L, g, x, t, with_jp=True):
        """弾の名前（日本版の英語名＋コード）と、その下に日本語名・現地の公式名・英語版の弾"""
        code, en, ctp, zh, ko = set_info(g, x)
        top = f'<b>{escape(en)}</b>' + (f'<span class="code">{escape(code)}</span>' if code else "")
        sub = []
        if with_jp and x != en:
            sub.append(x)
        loc = zh if L == "zh-tw" else ko if L == "ko" else ""
        if loc:
            sub.append(f'{t["local"]}「{loc}」')
        if ctp and ctp != en:
            sub.append(f'{t["counterpart"]}: {ctp}')
        return top, " · ".join(sub)

    def rel_line(L, g, x, t, jp=""):
        """日本の発売日と、その国（繁中版・韓国版）・英語版の発売日を1行に"""
        lr = (LOCAL_REL.get(g) or {}).get(x) or {}
        recent = bool(jp) and jp >= (today - _dt.timedelta(days=150)).isoformat()
        parts = [f'{t["jprel"]} {fmt_date(L, jp)}'] if jp else []
        loc_key = "tw" if L == "zh-tw" else "kr" if L == "ko" else ""
        lab = t["twrel"] if L == "zh-tw" else t["krrel"] if L == "ko" else ""
        if loc_key and g == "pokemon" and (lr.get(loc_key) or (recent and set_info(g, x)[0])):
            parts.append(f'{lab} {fmt_date(L, lr[loc_key]) if lr.get(loc_key) else t["tba"]}')
        if lr.get("en"):
            parts.append(f'{t["enrel"]} {fmt_date(L, lr["en"])}')
        elif recent and g == "pokemon" and set_info(g, x)[0]:
            parts.append(f'{t["enrel"]} {t["tba"]}')
        return f'<span class="rl">{escape(" ／ ".join(parts))}</span>' if parts else ""

    # 弾ごとの相場
    rows = []
    for k, v in items.items():
        g, x = k.split("|", 1)
        p, day = _last(v.get("jp") or {})
        if not p:
            continue
        us, _ = _last(v.get("us") or {})
        rel = str(((info.get(g) or {}).get(x) or {}).get("release") or "")
        rows.append({"g": g, "x": x, "p": p, "day": day, "teika": v.get("teika"), "old": _ago(v.get("jp") or {}, 30),
                     "us": us, "rel": rel, "jpser": v.get("jp") or {}, "usser": v.get("us") or {},
                     # ワンピースの tcg は英語版のBOX（souba.yaml の説明どおり）なので、英語版として扱う
                     "enser": v.get("en") or (v.get("us") if g == "onepiece" else None) or {},
                     "en_kind": v.get("en_kind") or "box", "krser": v.get("kr") or {}, "twser": v.get("tw") or {}})
    rows.sort(key=lambda r: (r["rel"] or "0000"), reverse=True)

    cards = []
    for v in (card_raw or {}).values():
        p, day = _last(v.get("jp") or {})
        if p:
            g, x = (v.get("key") or "|").split("|", 1)
            cards.append({"g": g, "x": x, "label": v.get("label") or "", "num": v.get("num") or "", "p": p})
    cards.sort(key=lambda c: -c["p"])

    d0 = (today - _dt.timedelta(days=75)).isoformat()
    rels = []
    for g in ("pokemon", "onepiece"):
        for x, inf in (info.get(g) or {}).items():
            r = str(inf.get("release") or "")
            if r >= d0:
                rels.append((r, g, x, inf))
    rels.sort()
    fut = [r for r in rels if r[0] > tdy]

    def chg(r):
        if not r["old"]:
            return "–"
        c = (r["p"] - r["old"]) / r["old"] * 100
        return f'<span class="{"up" if c >= 0 else "dn"}">{"+" if c >= 0 else ""}{c:.0f}%</span>'

    def price_table(L, t, game, limit=None):
        rs = [r for r in rows if r["g"] == game][:limit]
        if not rs:
            return ""
        h = [f'<div class="tw"><table><tr><th>{t["set"]}</th><th class="n">{t["price"]}</th><th class="n hide-s">{t["msrp"]}</th>'
             f'<th class="n">{t["x"]}</th><th class="n hide-s">{t["chg"]}</th></tr>']
        for r in rs:
            top, sub = names_html(L, game, r["x"], t)
            top = f'<a href="/{L}/sets/{set_slug(game, r["x"])}/" style="color:inherit">{top}</a>'
            mult = f'×{r["p"] / r["teika"]:.1f}' if r.get("teika") else "–"
            us = f'<span class="jp">{t["us"]}: ${r["us"]:,.0f}</span>' if (r["us"] and game == "pokemon") else ""
            h.append(f'<tr><td>{top}<span class="jp">{escape(sub)}</span>{rel_line(L, game, r["x"], t, r["rel"])}{buy_btns(game, r["x"], t)}</td>'
                     f'<td class="n"><b>¥{r["p"]:,}</b><span class="jp">{money(L, r["p"])}</span>{us}{_spark(r["jpser"])}</td>'
                     f'<td class="n hide-s">' + (f'¥{r["teika"]:,}' if r.get("teika") else "–") + f'</td><td class="n">{mult}</td>'
                     f'<td class="n hide-s">{chg(r)}</td></tr>')
        h.append("</table></div>")
        return "".join(h)

    def card_table(L, t, limit):
        h = [f'<div class="tw"><table><tr><th>{t["card"]}</th><th class="hide-s">{t["set"]}</th><th class="n">{t["price"]}</th></tr>']
        for c in cards[:limit]:
            en = card_name(c["label"])
            code = set_info(c["g"], c["x"])[0]
            h.append(f'<tr><td><b>{escape(en or c["label"])}</b><span class="jp">{escape(c["num"])}'
                     + (f' · {escape(c["label"])}' if en else "") + f'</span></td>'
                     f'<td class="hide-s">{escape(set_name(c["g"], c["x"]))}' + (f'<span class="code">{escape(code)}</span>' if code else "") + '</td>'
                     f'<td class="n"><b>¥{c["p"]:,}</b><span class="jp">{money(L, c["p"])}</span></td></tr>')
        h.append("</table></div>")
        return "".join(h)

    def rel_list(L, t, only_future=False, limit=None):
        rs = (fut if only_future else rels)[:limit]
        h = []
        for r, g, x, inf in rs:
            ty = TYPE_T.get(re.sub(r"【.*?】", "", inf.get("type") or ""), {}).get(L) or ""
            yen = re.findall(r"([\d,]+)円", inf.get("price") or "")
            top, sub = names_html(L, g, x, t)
            extra = [e for e in (sub, ty, (f'{t["msrp"]} ¥{yen[-1]} ({money(L, int(yen[-1].replace(",", "")))})' if yen else "")) if e]
            h.append(f'<div class="rel"><time datetime="{r}">{fmt_date(L, r)}</time><div><span class="g">{"Pokémon" if g == "pokemon" else "ONE PIECE"}</span>'
                     f'{top}' + (f'<span class="soon">{t["unreleased"]}</span>' if r > tdy else "")
                     + f'<span class="jp">{escape(" · ".join(extra))}</span>{rel_line(L, g, x, t, r).replace(escape(t["jprel"] + " " + fmt_date(L, r)) + " ／ ", "").replace(escape(t["jprel"] + " " + fmt_date(L, r)), "")}</div></div>')
        return "".join(h)

    # ---- 弾ごとのページ：日本の相場・アメリカでの日本版の相場・英語版の相場を1つのチャートに（11/7 ユーザー指示）----
    def to_cur(L, yen):
        """円 → そのページの通貨（チャートの縦軸）"""
        if L == "zh-tw" and jpy_per.get("TWD"):
            return yen / jpy_per["TWD"], "NT$"
        if L == "ko" and jpy_per.get("KRW"):
            return yen / jpy_per["KRW"], "원"
        return yen / fx, "$"

    def cur_fmt(L, v, unit):
        if unit == "원":
            return f"{v / 10000:,.1f}만원" if v >= 10000 else f"{v:,.0f}원"
        return f"{unit}{v:,.0f}"

    def chart_svg(L, t, r):
        lines = []  # (ラベル, 色, {日付: 現地通貨})
        if r["jpser"]:
            lines.append((t["ln_jp"], "#c8102e", {d: to_cur(L, v)[0] for d, v in r["jpser"].items()}))
        if r["usser"] and r["g"] == "pokemon":
            lines.append((t["ln_us"], "#2563eb", {d: to_cur(L, v * fx)[0] for d, v in r["usser"].items()}))
        if r["enser"]:
            lines.append((t["ln_en"] + ("" if r["en_kind"] == "box" else f' ({t["etb"]})'), "#16a34a",
                          {d: to_cur(L, v * fx)[0] for d, v in r["enser"].items()}))
        if r["krser"]:  # 韓国版はeBayの出品価格（ドル）
            lines.append((t["ln_kr"], "#f59e0b", {d: to_cur(L, v * fx)[0] for d, v in r["krser"].items()}))
        if r["twser"]:
            lines.append((t["ln_tw"], "#8b5cf6", {d: to_cur(L, v * fx)[0] for d, v in r["twser"].items()}))
        unit = to_cur(L, 1)[1]
        alld = sorted({d for _, _, m in lines for d in m})
        if not alld:
            return ""
        d1 = alld[-1]
        d0 = max(alld[0], (_dt.date.fromisoformat(d1) - _dt.timedelta(days=120)).isoformat())
        vals = [v for _, _, m in lines for d, v in m.items() if d >= d0]
        if not vals:
            return ""
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.08 or hi * 0.05 or 1
        lo, hi = max(0, lo - pad), hi + pad
        W, H, L0, R0, T0, B0 = 640, 260, 64, 12, 12, 28
        t0 = _dt.date.fromisoformat(d0).toordinal()
        span = max(1, _dt.date.fromisoformat(d1).toordinal() - t0)

        def X(d):
            return L0 + (_dt.date.fromisoformat(d).toordinal() - t0) / span * (W - L0 - R0)

        def Y(v):
            return T0 + (hi - v) / (hi - lo) * (H - T0 - B0)
        g = []
        for i in range(5):  # 横の目盛り線
            v = lo + (hi - lo) * i / 4
            y = Y(v)
            g.append(f'<line x1="{L0}" x2="{W - R0}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)"/>'
                     f'<text x="{L0 - 6}" y="{y + 4:.1f}" text-anchor="end">{escape(cur_fmt(L, v, unit))}</text>')
        for d in (d0, d1):
            g.append(f'<text x="{X(d):.1f}" y="{H - 8}" text-anchor="{"start" if d == d0 else "end"}">{d[5:].replace("-", "/")}</text>')
        for lab, col, m in lines:
            pts = sorted((d, v) for d, v in m.items() if d >= d0)
            if len(pts) >= 2:
                g.append(f'<path d="M' + " L".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in pts) + f'" fill="none" stroke="{col}" stroke-width="2.2"/>')
            if pts:
                g.append(f'<circle cx="{X(pts[-1][0]):.1f}" cy="{Y(pts[-1][1]):.1f}" r="3.5" fill="{col}"/>')
        leg = "".join(f'<span><i style="background:{c}"></i>{escape(lab)}</span>' for lab, c, _ in lines)
        return (f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(t["chart"])}">{"".join(g)}</svg>'
                f'<div class="leg">{leg}</div><p class="note">{escape(t["chart_note"].format(unit=unit))}</p></div>')

    def set_page(L, t, r):
        g, x = r["g"], r["x"]
        code, en, ctp, zh, ko = set_info(g, x)
        nm = (zh if L == "zh-tw" else ko if L == "ko" else "") or en
        game = "Pokémon" if g == "pokemon" else "One Piece"
        title = t["set_title"].format(name=nm, code=code, game=game).replace("  ", " ").replace("（）", "").replace("()", "")
        h1 = t["set_h1"].format(name=nm, code=code, game=game).replace("  ", " ").replace("（）", "").replace("()", "")
        en_now, _ = _last(r["enser"])
        us_now = r["us"] if g == "pokemon" else None
        desc = t["set_desc"].format(name=nm, code=code, jp=f'¥{r["p"]:,}', local=money(L, r["p"]),
                                    msrp=(f'¥{r["teika"]:,}' if r.get("teika") else "–"))
        top, sub = names_html(L, g, x, t)
        stats = [(t["ln_jp"], f'¥{r["p"]:,}', money(L, r["p"]))]
        if r.get("teika"):
            stats.append((t["msrp"], f'¥{r["teika"]:,}', f'×{r["p"] / r["teika"]:.1f}'))
        if r["old"]:
            stats.append((t["chg"], chg(r), ""))
        if us_now:
            stats.append((t["ln_us"], f'${us_now:,.0f}', ""))
        if en_now:
            stats.append((t["ln_en"], f'${en_now:,.0f}', "" if r["en_kind"] == "box" else t["etb"]))
        kr_now, _ = _last(r["krser"])
        if kr_now:
            stats.append((t["ln_kr"], f'${kr_now:,.0f}', "eBay"))
        tw_now, _ = _last(r["twser"])
        if tw_now:
            stats.append((t["ln_tw"], f'${tw_now:,.0f}', "eBay"))
        st_html = "".join(f'<div class="stat"><small>{escape(a)}</small><b>{b}</b><span>{escape(c)}</span></div>' for a, b, c in stats)
        body = (f'<div class="card">{top}<span class="jp">{escape(sub)}</span>{rel_line(L, g, x, t, r["rel"])}{buy_btns(g, x, t)}</div>'
                f'<div class="stats">{st_html}</div><h2>{escape(t["chart"])}</h2>{chart_svg(L, t, r)}'
                + (f'<p class="note">{escape(t["no_local"])}</p>' if L in ("zh-tw", "ko") else "")
                + f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/releases/">{t["releases"]} →</a></p>')
        return (f"sets/{set_slug(g, x)}/", "set", title, h1, desc, "", body, "box")

    ex_rel = ", ".join(f'{set_name(g, x)} {set_info(g, x)[0]} ({r[5:7].lstrip("0")}/{r[8:]})'.replace(" ()", "")
                       for r, g, x, _ in fut[:3])

    for L, meta in LANGS.items():
        t = T[L]
        src_html = (f'<section class="src"><h2>{t["sources"]}</h2><p>{escape(t["src"].format(fx=round(fx, 1), fxd=fxd))}</p>'
                    f'<p>{escape(t["names"])}</p><p>{escape(t["aff"])}</p></section>')
        specs = []  # (path, key, title, h1, desc, lead, body, 親ページのkey)
        for path, key in PAGES:
            title, h1, desc = META[L][key]
            title = title.format(y=today.year, y1=today.year + 1)
            h1 = h1.format(y=today.year, y1=today.year + 1)
            desc = desc.format(ex=ex_rel)
            lead = LEAD[L][key]
            if key == "home":
                body = (f'<h2>{t["upcoming"]}</h2><div class="card">{rel_list(L, t, True, 6) or "–"}</div>'
                        f'<p><a href="/{L}/releases/">{t["releases"]} →</a></p>'
                        f'<h2>{t["movers"]} · {t["pokemon"]}</h2>{price_table(L, t, "pokemon", 8)}'
                        f'<h2>{t["movers"]} · {t["onepiece"]}</h2>{price_table(L, t, "onepiece", 6)}'
                        f'<p><a href="/{L}/box-prices/">{t["box"]} →</a></p>'
                        f'<h2>{t["hot"]}</h2>{card_table(L, t, 10)}<p><a href="/{L}/card-prices/">{t["cards"]} →</a></p>'
                        f'<p><a href="/{L}/buy-in-japan/">{t["buy"]} →</a></p>')
            elif key == "releases":
                body = f'<div class="card">{rel_list(L, t)}</div><p><a href="/{L}/box-prices/">{t["box"]} →</a></p>'
            elif key == "box":
                body = (f'<h2>{t["pokemon"]}</h2>{price_table(L, t, "pokemon")}<h2>{t["onepiece"]}</h2>{price_table(L, t, "onepiece")}'
                        f'<p><a href="/{L}/releases/">{t["releases"]} →</a></p>')
            elif key == "cards":
                body = card_table(L, t, 60) + f'<p><a href="/{L}/box-prices/">{t["box"]} →</a></p>'
            else:
                body = "".join(f'<div class="card"><h2 style="margin-top:0">{escape(a)}</h2><p>{escape(b)}</p></div>' for a, b in BUY[L])
                body += f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/releases/">{t["releases"]} →</a></p>'
            specs.append((path, key, title, h1, desc, lead, body, None))
        for r in rows:  # 弾ごとのページ（チャート付き）
            specs.append(set_page(L, t, r))
        for path, key, title, h1, desc, lead, body, parent in specs:
            url = f"{site}/{L}/{path}"
            # hreflang：自分を含む全言語。中国語は zh-Hant・zh-TW・zh-HK を同じページに
            alt = "".join(f'<link rel="alternate" hreflang="{hl}" href="{site}/{l}/{path}">' for l, m in LANGS.items() for hl in m["hreflang"])
            alt += f'<link rel="alternate" hreflang="x-default" href="{site}/en/{path}">'
            # 構造化データ：パンくず・ページ（更新日）・一覧
            crumbs = [{"@type": "ListItem", "position": 1, "name": t["home"], "item": f"{site}/{L}/"}]
            if parent:
                crumbs.append({"@type": "ListItem", "position": 2, "name": t[parent], "item": f"{site}/{L}/box-prices/"})
            if path:
                crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": h1 if parent else t[key], "item": url})
            ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs},
                  {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc, "url": url,
                   "inLanguage": meta["html"], "dateModified": tdy, "isPartOf": {"@type": "WebSite", "name": t["site"], "url": f"{site}/{L}/"}}]
            if key in ("box", "releases"):
                lst = [r for r in rows] if key == "box" else [{"g": g, "x": x} for _, g, x, _ in rels]
                ld.append({"@context": "https://schema.org", "@type": "ItemList",
                           "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                                "name": f'{set_name(r["g"], r["x"])} {set_info(r["g"], r["x"])[0]}'.strip()}
                                               for i, r in enumerate(lst[:50])]})
            ld_html = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
            og_img = f"{site}/og-{L}.png"
            ogalt = '<meta property="og:locale:alternate" content="zh_HK">' if L == "zh-tw" else ""
            cur = parent or key
            tabs = "".join(f'<a href="/{L}/{p}"{" aria-current=\"page\"" if k == cur else ""}>{t[k]}</a>' for p, k in PAGES)
            langs = "".join(f'<a href="/{l}/{path}" hreflang="{m["html"]}"{" aria-current=\"true\"" if l == L else ""}>{m["name"]}</a>' for l, m in LANGS.items())
            crumb_html = ""
            if parent:
                crumb_html = f'<p class="crumb"><a href="/{L}/">{t["home"]}</a> › <a href="/{L}/box-prices/">{escape(t[parent])}</a> › {escape(h1)}</p>'
            elif path:
                crumb_html = f'<p class="crumb"><a href="/{L}/">{t["home"]}</a> › {escape(t[key])}</p>'
            html = (f'<!doctype html><html lang="{meta["html"]}"><head><meta charset="utf-8">'
                    f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>'
                    f'<meta name="description" content="{escape(desc)}"><link rel="canonical" href="{url}">{alt}'
                    + (f'<meta name="naver-site-verification" content="{escape(naver)}">' if naver else "")
                    + f'<meta property="og:type" content="website"><meta property="og:site_name" content="{escape(t["site"])}">'
                    f'<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(desc)}">'
                    f'<meta property="og:url" content="{url}"><meta property="og:image" content="{og_img}">'
                    f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
                    f'<meta property="og:locale" content="{meta["og"]}">{ogalt}<meta name="twitter:card" content="summary_large_image">'
                    f'<link rel="icon" href="/favicon.svg" type="image/svg+xml">{ld_html}'
                    f'<style>{CSS}</style></head><body><header><div class="w"><div class="top"><a class="logo" href="/{L}/">{t["site"]}</a>'
                    f'<div class="lang">{langs}<a href="/" hreflang="ja">日本語</a></div></div><nav class="tabs">{tabs}</nav></div></header>'
                    f'<main class="w">{crumb_html}<h1>{escape(h1)}</h1>' + (f'<p class="lead">{escape(lead)}</p>' if lead else "")
                    + f'<p class="note">{t["updated"]}: {fmt_date(L, tdy)}</p>{body}{src_html}</main>'
                    f'<footer><div class="w"><p>© {escape(t["site"])} (tcg-chusen.com)</p></div></footer></body></html>')
            p = Path(out) / L / path / "index.html"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf-8")
            urls.append((url, tdy))
    return urls
