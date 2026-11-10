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
        "30th CELEBRATION": ("M6a", "30th CELEBRATION", "30th Celebration", "30th CELEBRATION", "30th CELEBRATION"),
        "30周年 FUTURISTIC BOX": ("", "30th CELEBRATION FUTURISTIC BOX", "", "", ""),
        "30周年エーフィ・ブラッキーデッキ": ("", "30th Premium Deck Set Espeon & Umbreon", "", "", ""),
        "ストームエメラルダ": ("M6", "Storm Emeralda", "Delta Reign", "綠寶石風暴", "스톰에메랄다"),
        "スターターセットex": ("", "Starter Set ex", "", "", ""),
        "アビスアイ": ("M5", "Abyss Eye", "Pitch Black", "深淵之瞳", "어비스아이"),
        "ニンジャスピナー": ("M4", "Ninja Spinner", "Chaos Rising", "忍者飛旋", "닌자스피너"),
        "ムニキスゼロ": ("M3", "Nihil Zero", "Perfect Order", "虛無歸零", "니힐제로"),
        "MEGAドリームex": ("M2a", "MEGA Dream ex", "Ascended Heroes", "超級進化夢想ex", "MEGA 드림 ex"),
        "インフェルノX": ("M2", "Inferno X", "Phantasmal Flames", "烈獄狂火X", "인페르노X"),
        "メガブレイブ": ("M1L", "Mega Brave", "Mega Evolution", "超級勇氣", "메가브레이브"),
        "メガシンフォニア": ("M1S", "Mega Symphonia", "Mega Evolution", "超級交響樂", "메가심포니아"),
        "ブラックボルト": ("SV11B", "Black Bolt", "Black Bolt", "漆黑伏特", "블랙볼트"),
        "ホワイトフレア": ("SV11W", "White Flare", "White Flare", "純白閃焰", "화이트플레어"),
        "ロケット団の栄光": ("SV10", "Glory of Team Rocket", "Destined Rivals", "火箭隊的榮耀", "로켓단의 영광"),
        "熱風のアリーナ": ("SV9a", "Heat Wave Arena", "Destined Rivals", "熱風競技場", ""),
        "バトルパートナーズ": ("SV9", "Battle Partners", "Journey Together", "對戰搭檔", ""),
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
        "夢の一枚": ("PEB-01", "The Drawing of Your Dreams", "The Drawing of Your Dreams", "", ""),  # 新シリーズ「プレミアムエクストラブースター」第1弾。英語名は 11/10 英語版公式（en.onepiece-cardgame.com）で確認
        "応答せよ、世界": ("OP-19", "Come In, World", "Come In, World", "", ""),
        "EAST BLUE": ("EB-06", "EAST BLUE", "EAST BLUE", "", ""),
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
        "30th CELEBRATION": {"en": "2026-09-16", "tw": "2026-09-16", "kr": "2026-09-16"},
        "ストームエメラルダ": {"en": "2026-11-06", "tw": "2026-08-07", "kr": "2026-08-21"},
        "アビスアイ": {"en": "2026-07-17", "tw": "2026-06-05"},
        "ニンジャスピナー": {"en": "2026-05-22", "tw": "2026-03-27", "kr": "2026-05-01"},
        "ムニキスゼロ": {"en": "2026-03-27", "tw": "2026-02-06", "kr": "2026-03-13"},
        "MEGAドリームex": {"en": "2026-01-30", "tw": "2025-12-05", "kr": "2026-01-23"},
        "インフェルノX": {"en": "2025-11-14", "tw": "2025-10-09", "kr": "2025-11-28"},
        "テラスタルフェスex": {"en": "2025-01-17", "tw": "2024-12-20", "kr": "2025-01-22"},
        "ポケモンカード151": {"en": "2023-09-22"},
        "VSTARユニバース": {"en": "2023-01-20"},
        "イーブイヒーローズ": {"en": "2021-08-27", "tw": "2021-06-11", "kr": "2021-08-11"},
    },
    "onepiece": {
        "夢の一枚": {"en": "2027-04-23"},
        "応答せよ、世界": {"en": "2027-03-05"},
        "EAST BLUE": {"en": "2027-01-29"},
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
    # 11/8 追加（細かい検索語「カード名＋番号 japanese」を取るため。確かな英語名だけ）
    "いちげきウーラオス": "Single Strike Urshifu", "こくばバドレックス": "Shadow Rider Calyrex", "はくばバドレックス": "Ice Rider Calyrex",
    "イッカネズミ": "Maushold", "ウミディグダ": "Wiglett", "オリジンディアルガ": "Origin Forme Dialga", "オリジンパルキア": "Origin Forme Palkia",
    "カイオーガ": "Kyogre", "カイリキー": "Machamp", "カビゴン": "Snorlax", "カスミのコダック": "Misty's Psyduck", "ガブリアス": "Garchomp",
    "ガマゲロゲ": "Seismitoad", "ガラルファイヤー": "Galarian Moltres", "クワガノン": "Vikavolt", "グラードン": "Groudon", "コイキング": "Magikarp",
    "サーナイト": "Gardevoir", "サーフゴー": "Gholdengo", "シャワーズ": "Vaporeon", "ジジーロン": "Drampa", "ジュラルドン": "Duraludon",
    "ジラーチ": "Jirachi", "スターミー": "Starmie", "セレビィ": "Celebi", "ゼラオラ": "Zeraora", "ゼルネアス": "Xerneas", "ソルガレオ": "Solgaleo",
    "チラチーノ": "Cinccino", "チルタリス": "Altaria", "テールナー": "Braixen", "デオキシス": "Deoxys", "デカヌチャン": "Tinkaton",
    "トドロクツキ": "Roaring Moon", "トルネロス": "Tornadus", "ロケット団のニャース": "Team Rocket's Meowth", "ロケット団の": "Team Rocket's ",
    "ニャース": "Meowth", "ノノクラゲ": "Toedscool", "バシャーモ": "Blaziken", "バンギラス": "Tyranitar", "ヒスイウインディ": "Hisuian Arcanine",
    "ヒトカゲ": "Charmander", "ヒビキのホウオウ": "Ethan's Ho-Oh", "ヒンバス": "Feebas", "ビクティニ": "Victini", "フリーザー": "Articuno",
    "ヘルガー": "Houndoom", "ペルシアン": "Persian", "ホエルオー": "Wailord", "ポッチャマ": "Piplup", "ヤドラン": "Slowbro", "ライコウ": "Raikou",
    "ラッキー": "Chansey", "ラティアス": "Latias", "ラティオス": "Latios", "ルナアーラ": "Lunala", "ルカリオ": "Lucario", "ダークライ": "Darkrai",
    "ジガルデ": "Zygarde", "リザードンX": "Charizard X", "リザードンY": "Charizard Y", "メガ": "Mega ",
    "おじょうさま": "Lady", "ふりそで": "Kimono Girl", "アスナ": "Flannery", "アセロラのいたずら": "Acerola's Mischief", "エリカのおもてなし": "Erika's Invitation",
    "オリーヴ": "Oleana", "カシオペア": "Cassiopeia", "カスミ": "Misty", "カンナ": "Lorelei", "キハダ": "Dendra", "クララ": "Klara", "グルーシャ": "Grusha",
    "コルニの気合い": "Korrina's Focus", "サイトウ": "Bea", "サカキ": "Giovanni", "サザレ": "Briar", "サナ": "Shauna", "スグリ": "Kieran",
    "ゼイユ": "Carmine", "タロ": "Lacey", "ツツジ": "Roxanne", "トウコ": "Hilda", "ナタネの活気": "Gardenia's Vigor", "ネズ": "Piers",
    "パラソルおねえさん": "Parasol Lady", "ヒカリ": "Dawn", "ベルのまごころ": "Bianca's Devotion", "ボスの指令": "Boss's Orders",
    "マツバの確信": "Morty's Conviction", "メイのはげまし": "Rosa's Encouragement", "モノマネむすめ": "Copycat", "ローラースケーター": "Roller Skater",
    "リーリエの決心": "Lillie's Determination", "ネオアッパーエネルギー": "Neo Upper Energy",
    "しらほし": "Shirahoshi", "そげキング": "Sogeking", "ウソ八": "Usohachi", "エネル": "Enel", "コビー": "Koby", "サカズキ": "Sakazuki",
    "シャーロット・プリン": "Charlotte Pudding", "シルバーズ・レイリー": "Silvers Rayleigh", "ジュエリー・ボニー": "Jewelry Bonney",
    "ジュラキュール・ミホーク": "Dracule Mihawk", "ゼウス": "Zeus", "ドンキホーテ・ドフラミンゴ": "Donquixote Doflamingo", "ペローナ": "Perona",
    "ミス・オールサンデー": "Miss All Sunday", "ゴムゴムの巨人": "Gum-Gum Giant", "Mr.2・ボン・クレー": "Mr.2 Bon Clay",
    "マスターボールミラー": "Master Ball Mirror", "モンスターボールミラー": "Poké Ball Mirror", "ミラー": "Mirror", "フルアート": "Full Art",
    "イラスト修正前": "Pre-correction Art", "和柄アート": "Japanese Pattern Art", "新四皇スペシャルカード": "New Four Emperors Special", "仕様": "",
}

SEP = {"en": " · ", "zh-tw": "／", "ko": " / "}
HSEP = {"en": " — ", "zh-tw": "｜", "ko": " | "}
WEEK = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "zh-tw": "一二三四五六日", "ko": "월화수목금토일"}

T = {
    "en": {
        "site": "Japan TCG Navi", "setsidx": "Set list", "home": "Home", "releases": "JP Release Dates", "box": "JP Box Prices", "cards": "Top JP Cards",
        "buy": "Buy in Japan", "pokemon": "Pokémon TCG", "onepiece": "ONE PIECE Card Game",
        "release": "JP release", "msrp": "MSRP", "price": "Japan price", "x": "vs MSRP", "chg": "30d", "trend": "90-day trend",
        "us": "US (TCGplayer)", "set": "Set", "card": "Card", "upcoming": "Upcoming Japanese releases",
        "movers": "Japanese booster box prices", "hot": "Most expensive Japanese cards right now", "more": "See all",
        "ebay": "eBay", "amazon": "Amazon", "updated": "Updated", "unreleased": "Coming soon", "counterpart": "English set", "ln_jp": "Japanese box in Japan", "ln_us": "Japanese box in the US", "ln_en": "English version", "ln_kr": "Korean version", "ln_tw": "Chinese (TW/HK) version", "etb": "Elite Trainer Box", "chart": "Price chart", "chart_note": "All lines converted to {unit} at today's exchange rate. Japan = SNKRDUNK sold prices; US and English version = TCGplayer market price; Korean and Chinese versions = eBay listing prices.", "set_title": "{name} ({code}) Japanese Booster Box Price, Chart & Release Date", "set_h1": "{name} ({code}) Japanese Box Price", "set_desc": "{name} {code} Japanese booster box price in Japan: {jp} ({local}), MSRP {msrp}. Chart comparing the Japan price, the US price of the Japanese box and the English version.", "no_local": "", "jprel": "🇯🇵 Japan", "enrel": "🇺🇸 English", "twrel": "", "krrel": "", "tba": "TBA",
        "local": "", "sources": "Sources & notes",
        "src": "Japan prices are the latest sold prices of sealed boxes and ungraded single cards on SNKRDUNK, a major Japanese marketplace (not asking prices). Release dates and MSRP come from the official Japanese Pokémon Card Game and ONE PIECE Card Game websites. Exchange rate: $1 = ¥{fx} ({fxd}); converted prices are approximate.",
        "names": "Set names: the Japanese set's English name and code are shown first; \"English set\" is the international English-language release with the same cards where one exists.",
        "aff": "As an Amazon Associate, Japan TCG Navi earns from qualifying purchases. This site also uses eBay Partner Network links; if you buy through them we may earn a commission at no extra cost to you.",
        "privacy": "Privacy Policy", "affnote": "", "amazon_note": "", "deck": "deck",
    },
    "zh-tw": {
        "site": "日本卡牌情報站", "setsidx": "系列一覽", "home": "首頁", "releases": "日版發售日", "box": "日版卡盒價格", "cards": "日版高價單卡",
        "buy": "日本購買攻略", "pokemon": "寶可夢卡牌 PTCG", "onepiece": "航海王卡牌 ONE PIECE CARD GAME",
        "release": "日版發售", "msrp": "建議售價", "price": "日本市價", "x": "定價倍數", "chg": "30日", "trend": "90日走勢",
        "us": "美國（TCGplayer）", "set": "系列", "card": "單卡", "upcoming": "即將發售的日版新彈",
        "movers": "日版卡盒（補充包盒）價格", "hot": "日本目前最貴的單卡", "more": "看全部",
        "ebay": "eBay", "amazon": "日本亞馬遜", "updated": "更新", "unreleased": "即將發售", "counterpart": "英文版", "ln_jp": "日版 日本市價", "ln_us": "日版 美國市價", "ln_en": "英文版", "ln_kr": "韓文版", "ln_tw": "繁中版", "etb": "訓練家寶箱", "chart": "價格走勢", "chart_note": "所有線條以今天的匯率換算成{unit}。日本＝SNKRDUNK成交價；美國與英文版＝TCGplayer市價；韓文版與繁中版＝eBay刊登價。", "set_title": "{name}（{code}）日版卡盒價格、走勢圖與發售日", "set_h1": "{name}（{code}）日版卡盒價格", "set_desc": "{name} {code} 日版卡盒日本成交價{jp}（{local}），建議售價{msrp}。日本市價、美國的日版價格與英文版價格走勢圖，附發售日。", "no_local": "繁中版的價格取自eBay的刊登價，台灣當地的價格可能不同。", "jprel": "🇯🇵 日版", "enrel": "🇺🇸 英文版", "twrel": "🇹🇼 繁中版", "krrel": "", "tba": "未公布",
        "local": "繁中版", "sources": "資料來源與說明",
        "src": "日本市價為日本大型交易平台 SNKRDUNK 上未拆封卡盒與未鑑定單卡的最新成交價（非掛牌價）。發售日與建議售價來自日本寶可夢卡牌與航海王卡牌官方網站。匯率：1美元＝{fx}日圓（{fxd}），換算金額僅供參考。",
        "names": "系列名稱：先列出日版的英文名稱與系列代碼，「繁中版」為台灣、香港發售的官方中文名稱，「英文版」為收錄相同卡片的國際英文版系列（若有）。",
        "aff": "本站為 Amazon Associates（亞馬遜聯盟）成員，會從符合資格的購買中獲得收益；也使用 eBay Partner Network 聯盟連結。您透過連結購買不會多付任何費用。",
        "privacy": "隱私權政策", "affnote": "※ 含聯盟行銷連結", "amazon_note": "日本亞馬遜僅限可海外配送的商品", "deck": "deck",
    },
    "ko": {
        "site": "재팬 TCG 시세", "setsidx": "세트 목록", "home": "홈", "releases": "일판 발매일", "box": "일판 박스 시세", "cards": "일판 고가 카드",
        "buy": "일본 구매 가이드", "pokemon": "포켓몬 카드 게임", "onepiece": "원피스 카드 게임",
        "release": "일본 발매", "msrp": "정가", "price": "일본 시세", "x": "정가 대비", "chg": "30일", "trend": "90일 추이",
        "us": "미국 (TCGplayer)", "set": "세트", "card": "카드", "upcoming": "곧 발매되는 일판 신규 세트",
        "movers": "일판 부스터 박스 시세", "hot": "지금 일본에서 가장 비싼 카드", "more": "전체 보기",
        "ebay": "eBay", "amazon": "아마존재팬", "updated": "업데이트", "unreleased": "발매 예정", "counterpart": "영문판", "ln_jp": "일판 일본 시세", "ln_us": "일판 미국 시세", "ln_en": "영문판 시세", "ln_kr": "한글판 시세", "ln_tw": "중문판(대만) 시세", "etb": "엘리트 트레이너 박스", "chart": "시세 차트", "chart_note": "모든 선은 오늘 환율로 {unit} 환산. 일본=SNKRDUNK 실거래가, 미국·영문판=TCGplayer 시세, 한글판·중문판=eBay 판매가.", "set_title": "{name} ({code}) 일판 박스 시세·차트·발매일", "set_h1": "{name} ({code}) 일판 박스 시세", "set_desc": "{name} {code} 일판 박스 일본 실거래가 {jp}({local}), 정가 {msrp}. 일본 시세·미국 일판 시세·영문판 시세 비교 차트와 발매일.", "no_local": "한글판 시세는 eBay 판매가 기준이라 국내(번개장터·크림 등) 시세와 다를 수 있습니다.", "jprel": "🇯🇵 일판", "enrel": "🇺🇸 영문판", "twrel": "", "krrel": "🇰🇷 한글판", "tba": "미정",
        "local": "한글판", "sources": "출처 및 안내",
        "src": "일본 시세는 일본 대형 거래 플랫폼 SNKRDUNK(스니덩)에서 미개봉 박스와 미감정 싱글 카드가 실제로 거래된 최근 가격입니다(호가 아님). 발매일과 정가는 일본 포켓몬 카드 게임·원피스 카드 게임 공식 사이트 기준입니다. 환율: 1달러 = {fx}엔({fxd}), 환산 금액은 참고용입니다.",
        "names": "세트 이름: 일판의 영어 이름과 세트 코드를 먼저 표시하고, '한글판'은 한국 정식 발매명, '영문판'은 같은 카드가 수록된 해외 영문판 세트입니다(있는 경우).",
        "aff": "이 사이트는 Amazon 어소시에이트 프로그램 참가자로서 적격 구매를 통해 수수료를 받습니다. eBay Partner Network 제휴 링크도 사용하며, 링크로 구매하셔도 추가 비용은 없습니다.",
        "privacy": "개인정보 처리방침", "affnote": "※ 제휴 링크가 포함되어 있습니다", "amazon_note": "아마존재팬은 해외배송 가능 상품만 주문 가능", "deck": "deck",
    },
}

# ページごとのタイトル・説明（調査した現地の検索語に合わせる。韓国語はNAVER向けにタイトル40字・説明80字以内）
META = {
    "en": {
        "home": ("Japanese Pokémon Card Prices & Release Dates | Japan TCG Navi", "Japanese Pokémon & One Piece Card Prices and Release Dates, Straight from Japan",
                 "Daily Japan-market prices for Japanese Pokémon and One Piece booster boxes, the priciest Japanese singles, and every JP release date with MSRP in yen and USD."),
        "releases": ("Japanese Pokémon TCG Release Dates {y}–{y1} (+ One Piece Card Game)", "Japanese Pokémon TCG & One Piece Release Dates {y}–{y1}",
                     "Upcoming and recent Japanese Pokémon TCG and One Piece sets: release date, set code, MSRP in yen and the matching English set. Next up: {ex}"),
        "box": ("Japanese Pokémon Booster Box Prices — Japan Market, Updated Daily", "Japanese Booster Box Prices Today",
                "What sealed Japanese Pokémon and One Piece boxes sell for in Japan today vs MSRP, with 30-day change, USD and TCGplayer US prices: 151 (SV2a), Terastal Festival ex (SV8a), MEGA Dream ex (M2a) and more."),
        "cards": ("Most Expensive Japanese Pokémon & One Piece Cards (Japan Prices)", "Most Expensive Japanese Cards Right Now",
                  "Top Japanese Pokémon and One Piece single cards by current Japan market price, with card number, set, yen and USD, updated daily."),
        "buy": ("How to Buy Pokémon Cards in Japan: Stores, Lotteries & Tax-Free ({y} Guide)", "How to Buy Pokémon Cards in Japan",
                "Where to buy Japanese Pokémon cards at MSRP in Japan, Pokémon Center lotteries, purchase limits, the new tax-free refund system, and buying Japanese boxes from the US."),
    },
    "zh-tw": {
        "home": ("日版寶可夢卡盒價格與發售日｜日本行情每日更新", "日版寶可夢卡牌、航海王卡牌 日本行情與發售日",
                 "日版寶可夢（PTCG）與航海王卡牌：日本當地卡盒成交價、最貴單卡排行、日版發售日曆，附日圓定價與 NT$／HK$ 換算，每天更新。"),
        "releases": ("日版寶可夢卡牌發售日曆 {y}–{y1}｜含航海王、繁中版對照", "日版寶可夢卡牌、航海王卡牌 發售日曆",
                     "日版擴充包發售日、日圓建議售價、系列代碼與繁中版／英文版對照：{ex}"),
        "box": ("日版寶可夢卡盒價格行情｜日本成交價、定價倍數，每日更新", "日版寶可夢卡盒（補充包盒）價格行情",
                "SNKRDUNK 日本成交價 vs 建議售價、倍數、30日漲跌、NT$／HK$ 換算與美國 TCGplayer 價格：151（SV2a）、太晶慶典ex（SV8a）、超級進化夢想ex（M2a）等。"),
        "cards": ("日版寶可夢、航海王最貴單卡排行｜日本行情", "日本目前最貴的日版單卡排行",
                  "日本市場日版寶可夢卡牌、航海王卡牌單卡高價排行，附卡號、系列、日圓與 NT$ 價格，每天更新。"),
        "buy": ("去日本買寶可夢卡攻略：寶可夢中心、抽選、退稅、代購", "到日本買日版寶可夢卡的方法",
                "到日本怎麼用原價買日版寶可夢卡：寶可夢中心與電器行、抽選、限購、2026年11月起的新免稅（退稅）制度，以及從台灣、香港代購與直購。"),
    },
    "ko": {
        "home": ("일판 포켓몬카드 박스 시세·발매일 | 일본 현지 실거래가", "일판 포켓몬카드·원피스 카드 일본 시세와 발매일",
                 "일본 현지 일판 포켓몬카드·원피스 카드 박스 실거래 시세, 고가 카드 순위, 일판 발매일과 정가(엔·원 환산)를 매일 업데이트합니다."),
        "releases": ("일판 포켓몬카드 발매일 {y}-{y1} | 원피스·한글판 대응", "일판 포켓몬카드·원피스 카드 발매일",
                     "일본 확장팩 발매일·정가·세트 코드와 한글판/영문판 대응: {ex}"),
        "box": ("일판 포켓몬카드 박스 시세 | 일본 실거래가·정가 배수", "일판 포켓몬카드 박스 시세",
                "SNKRDUNK 일본 실거래가와 정가 배수, 30일 변동, 원·달러 환산, 미국 TCGplayer 가격. 151, 테라스탈 페스타 ex 등."),
        "cards": ("일본에서 가장 비싼 일판 포켓몬카드·원피스 카드 순위", "일본에서 가장 비싼 일판 카드 순위",
                  "일본 시장 기준 고가 일판 포켓몬카드·원피스 카드 순위. 카드 번호, 세트, 엔화·원화 시세. 매일 업데이트."),
        "buy": ("일본 포켓몬카드 구매 가이드 | 포켓몬센터·추첨·면세 환급·직구", "일본에서 일판 포켓몬카드 사는 방법",
                "일본 여행 중 정가로 사는 법, 포켓몬센터·추첨, 구매 제한, 2026년 11월부터 바뀐 면세(환급) 제도, 해외 직구·구매대행."),
    },
}

LEAD = {
    "en": {
        "home": "New Pokémon TCG sets launch in Japan first — usually 2–4 months before the English set with the same cards — while ONE PIECE Card Game sets now release in Japan and the West within days of each other. Track every Japanese release date and what sealed boxes and singles actually sell for in Japan, updated daily.",
        "releases": "Release dates, MSRP and set codes of upcoming and recent Japanese Pokémon TCG and ONE PIECE Card Game products, with the matching English set.",
        "box": "What sealed Japanese booster boxes are actually selling for in Japan today, compared with the official retail price (MSRP).",
        "cards": "The highest recent sold prices of Japanese single cards in Japan (ungraded).",
        "buy": "",
    },
    "zh-tw": {
        "home": "寶可夢卡牌與航海王卡牌的新彈都是日本最先發售：寶可夢繁中版通常晚日版1～2週、英文版晚2～4個月，航海王英文版則幾乎同步。這裡每天更新日版發售日，以及日版卡盒、單卡在日本的實際成交價，代購或等繁中版之前可以先比價。",
        "releases": "日版寶可夢卡牌、航海王卡牌新彈的發售日、日圓建議售價與系列代碼，並對照繁中版與英文版名稱。",
        "box": "日版未拆封卡盒（補充包盒）目前在日本的實際成交價，與建議售價（定價）的比較。想代購或等繁中版前可以先參考。",
        "cards": "日本近期成交價最高的日版單卡（未鑑定、裸卡）。",
        "buy": "",
    },
    "ko": {
        "home": "포켓몬 카드 게임과 원피스 카드 게임의 신규 세트는 일본에서 가장 먼저 나옵니다. 포켓몬 한글판은 보통 일판보다 3주~2개월, 영문판은 2~4개월 늦게 발매되고, 원피스 영문판은 거의 동시에 나옵니다. 일판 발매일과 미개봉 박스·싱글 카드의 일본 실거래 시세를 매일 업데이트합니다. 직구·구매대행 전에 확인하세요.",
        "releases": "일판 포켓몬 카드·원피스 카드 신규 세트의 발매일, 정가(엔), 세트 코드와 한글판·영문판 대응 세트를 정리했습니다.",
        "box": "일판 미개봉 부스터 박스가 지금 일본에서 실제로 거래되는 가격과 정가 비교입니다. 직구·구매대행 전에 참고하세요.",
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
    "プレミアムエクストラブースター": {"en": "Premium Extra Booster", "zh-tw": "Premium Extra Booster（高級額外補充包）", "ko": "프리미엄 엑스트라 부스터"},
}

# ===== 2026/11/6 の公式特別番組で発表されたワンピースの4弾（11/8）=====
# 海外からの「OP-19 release date」「PEB-01」「EB-06 East Blue Japanese」などの検索が増える時期なので、弾ページを厚くする。
# 書いてよい事実は公式発表のものだけ（収録カード・BOXのパック数・値段は、発表されたものだけ書く）。
# 1BOXのパック数と値段が公式に出ているのは OP-18 だけ。PEB-01 は未発表。
OP_NEW_ORDER = ["神の支配", "EAST BLUE", "応答せよ、世界", "夢の一枚"]
OP_NEW = {
    "神の支配": {"code": "OP-18", "rel": "2026-11-21", "pack": 240, "box": (24, 5760), "per_pack": None, "jp_slug": "op18-kami-no-shihai"},
    "EAST BLUE": {"code": "EB-06", "rel": "2027-01-30", "pack": 240, "box": None, "per_pack": None, "jp_slug": "eb06-east-blue"},
    "応答せよ、世界": {"code": "OP-19", "rel": "2027-02-27", "pack": 240, "box": None, "per_pack": None, "jp_slug": "op19-outou-seyo-sekai"},
    "夢の一枚": {"code": "PEB-01", "rel": "2027-04-24", "pack": 440, "box": None, "per_pack": 8, "jp_slug": "peb01-yume-no-ichimai"},
}
# 表のラベルと共通の文言
OP_NEW_LBL = {
    "en": {"h_about": "About this set", "h_facts": "Key facts", "h_faq": "FAQ", "h_links": "Upcoming Japanese ONE PIECE Card Game sets (announced Nov 6, 2026)",
           "rel": "Japanese release date", "type": "Product type", "price": "Price in Japan (MSRP)", "box": "Box", "per_pack": "Cards per pack", "theme": "Theme",
           "ann": "Announced", "ann_v": "November 6, 2026, official ONE PIECE Card Game special broadcast", "en": "English edition", "tba": "Not yet announced",
           "jp": "Japanese page", "jp_link": "Japanese page of this set (pre-order & lottery info in Japan) →", "per_pack_v": "{n} cards, all foil",
           "pack_v": "¥{pack} per pack ({packl})", "box_v": "{n} packs · ¥{box} ({boxl})", "list": "Set list", "tbd_en": "Not yet announced",
           "kind": {"OP-18": "Booster pack (18th)", "EB-06": "Extra Booster (6th)", "OP-19": "Booster pack (19th)", "PEB-01": "Premium Extra Booster (new series, 1st)"},
           "theme_v": {"EB-06": "East Blue", "OP-19": "Egghead"}, "pack_short": "¥{pack}/pack"},
    "zh-tw": {"h_about": "關於這個系列", "h_facts": "重點整理", "h_faq": "常見問題", "h_links": "即將發售的日版航海王卡牌新彈（2026/11/6 官方發表）",
              "rel": "日版發售日", "type": "商品類型", "price": "日本定價（建議售價）", "box": "整盒", "per_pack": "每包張數", "theme": "主題",
              "ann": "發表", "ann_v": "2026年11月6日 航海王卡牌官方特別節目", "en": "英文版", "tba": "尚未公布",
              "jp": "日文版頁面", "jp_link": "這個系列的日文版頁面（日本的預購、抽選資訊）→", "per_pack_v": "{n}張，全部閃卡",
              "pack_v": "每包{pack}日圓（{packl}）", "box_v": "{n}包／{box}日圓（{boxl}）", "list": "系列一覽", "tbd_en": "尚未公布",
              "kind": {"OP-18": "補充包（第18彈）", "EB-06": "額外補充包（第6彈）", "OP-19": "補充包（第19彈）", "PEB-01": "Premium Extra Booster（新系列第1彈）"},
              "theme_v": {"EB-06": "東海（East Blue）", "OP-19": "蛋頭島（Egghead）"}, "pack_short": "每包{pack}日圓"},
    "ko": {"h_about": "세트 소개", "h_facts": "핵심 정보", "h_faq": "자주 묻는 질문", "h_links": "곧 발매되는 일판 원피스 카드 신규 세트 (2026.11.6 공식 발표)",
           "rel": "일본 발매일", "type": "상품 종류", "price": "일본 정가", "box": "박스", "per_pack": "팩당 카드 수", "theme": "테마",
           "ann": "발표", "ann_v": "2026년 11월 6일 원피스 카드 게임 공식 특별 방송", "en": "영문판", "tba": "미정(미발표)",
           "jp": "일본어 페이지", "jp_link": "이 세트의 일본어 페이지 (일본 예약·추첨 정보) →", "per_pack_v": "{n}장, 전부 홀로 카드",
           "pack_v": "1팩 {pack}엔 ({packl})", "box_v": "{n}팩 · {box}엔 ({boxl})", "list": "세트 목록", "tbd_en": "미발표",
           "kind": {"OP-18": "부스터 팩 (18탄)", "EB-06": "엑스트라 부스터 (6탄)", "OP-19": "부스터 팩 (19탄)", "PEB-01": "프리미엄 엑스트라 부스터 (신규 시리즈 1탄)"},
           "theme_v": {"EB-06": "이스트 블루", "OP-19": "에그헤드"}, "pack_short": "1팩 {pack}엔"},
}
# 弾ごとの文章。{rel}=日本の発売日、{pack}/{packl}=1パックの値段（円／現地通貨）、{box}/{boxl}=1BOX、{enrel}=英語版の発売日、{en_line}=英語版の一文
OP_NEW_T = {
    "en": {
        "神の支配": {
            "title": "OP-18 The Dominance of God Japanese Release Date (Nov 21, 2026), Price & Pre-order | ONE PIECE Card Game",
            "h1": "OP-18 The Dominance of God (Japanese) — release date, price & pre-order",
            "desc": "The Japanese ONE PIECE Card Game booster OP-18 \"The Dominance of God\" (神の支配) releases in Japan on Saturday, November 21, 2026 at ¥240 per pack (24-pack box ¥5,760). Revealed cards, key facts, FAQ and where to buy the Japanese box.",
            "about": [
                "The Dominance of God (OP-18, Japanese title 神の支配) is the 18th booster pack of the Japanese ONE PIECE Card Game. It releases in Japan on {rel} at ¥{pack} per pack ({packl}); a sealed box holds 24 packs for ¥{box} ({boxl}).",
                "In the official special broadcast on November 6, 2026, Bandai showed parallel-art versions of the leader cards Carue, Miss All Sunday, Monkey D. Luffy and Spandam, as well as Saint Shamrock and Loki cards illustrated by Yoshitaka Amano.",
                "{en_line}Once the set is on sale, this page shows what a sealed Japanese box actually sells for in Japan, updated daily.",
            ],
            "faq": [
                ("When does OP-18 The Dominance of God come out in Japan?", "{rel}. Japanese ONE PIECE Card Game boosters are released on Saturdays."),
                ("How much is a pack and a box of OP-18 in Japan?", "The Japanese MSRP is ¥{pack} per pack ({packl}) and ¥{box} for a 24-pack box ({boxl}). Popular sets often trade above MSRP after release; the current Japanese market price appears on this page once sales begin."),
                ("Which OP-18 cards have been revealed?", "Parallel-art leader cards of Carue, Miss All Sunday, Monkey D. Luffy and Spandam, and Saint Shamrock and Loki cards drawn by Yoshitaka Amano were shown in the November 6, 2026 special broadcast. The full card list is published on the official Japanese site."),
            ],
        },
        "EAST BLUE": {
            "title": "EB-06 EAST BLUE Japanese Release Date (Jan 30, 2027), Price & Pre-order | ONE PIECE Card Game Extra Booster",
            "h1": "EB-06 EAST BLUE (Japanese Extra Booster) — release date, price & pre-order",
            "desc": "ONE PIECE Card Game Extra Booster EB-06 \"EAST BLUE\" (Japanese edition) releases in Japan on Saturday, January 30, 2027 at ¥240 per pack, themed on the East Blue. Key facts, revealed artwork, FAQ and where to buy the Japanese version.",
            "about": [
                "EAST BLUE (EB-06) is the sixth Extra Booster of the Japanese ONE PIECE Card Game, themed on the East Blue, the sea where the story begins. It releases in Japan on {rel} at ¥{pack} per pack ({packl}).",
                "It was announced in the official special broadcast on November 6, 2026 together with OP-18, OP-19 and PEB-01. The package design and two new illustrations have been revealed; the card list, box configuration and an English release have not been announced yet.",
                "Pre-orders at Japanese retailers usually open one to two months before release. Japanese box prices will appear on this page automatically once the set is on sale.",
            ],
            "faq": [
                ("When does EB-06 EAST BLUE come out in Japan?", "{rel}."),
                ("What is the theme of EB-06?", "The East Blue — the starting point of the story. Two new illustrations and the package were shown in the November 6, 2026 special broadcast; the card list is not out yet."),
                ("How much is EB-06 in Japan?", "¥{pack} per pack ({packl}) at Japanese MSRP. The box configuration has not been announced yet."),
                ("Will EB-06 EAST BLUE get an English release?", "Not announced yet. Every previous Extra Booster (EB-01 to EB-05) received an English edition, so one is likely, but check the official ONE PIECE Card Game site for confirmation."),
            ],
        },
        "応答せよ、世界": {
            "title": "OP-19 Japanese Release Date (Feb 27, 2027), Price & Pre-order | ONE PIECE Card Game Booster 応答せよ、世界",
            "h1": "OP-19 応答せよ、世界 (Japanese) — release date, price & pre-order",
            "desc": "ONE PIECE Card Game booster OP-19 \"応答せよ、世界\" (Japanese edition; the English title is not yet announced) releases in Japan on Saturday, February 27, 2027 at ¥240 per pack, themed on Egghead. Key facts, FAQ and where to buy the Japanese version.",
            "about": [
                "OP-19 is the 19th booster pack of the Japanese ONE PIECE Card Game. Its Japanese title is 応答せよ、世界, roughly \"Respond, World\" (unofficial translation; the official English title has not been announced). It releases in Japan on {rel} at ¥{pack} per pack ({packl}).",
                "The theme is Egghead. The set was announced in the official special broadcast on November 6, 2026, where the package design and two new illustrations were revealed. The card list and box configuration have not been announced yet.",
                "Recent Japanese OP boosters and their English editions have launched within days of each other (OP-18, for example, is November 21 in Japan and November 20 in English), but no English release date for OP-19 has been announced. Japanese box prices will appear here once the set is on sale.",
            ],
            "faq": [
                ("When does OP-19 come out in Japan?", "{rel}."),
                ("What is the English name of OP-19?", "Not announced yet. The Japanese title is 応答せよ、世界 (roughly \"Respond, World\"). Until Bandai announces the English title, search by the set code OP-19."),
                ("What is the theme of OP-19?", "Egghead, according to the November 6, 2026 special broadcast. Two new illustrations and the package have been revealed."),
                ("How much is OP-19 in Japan?", "¥{pack} per pack ({packl}) at Japanese MSRP. The box configuration has not been announced yet."),
            ],
        },
        "夢の一枚": {
            "title": "PEB-01 Premium Extra Booster 夢の一枚 Japanese Release Date (Apr 24, 2027), Price & What's Inside | ONE PIECE Card Game",
            "h1": "PEB-01 Premium Extra Booster 夢の一枚 (Japanese) — release date, price & contents",
            "desc": "ONE PIECE Card Game PEB-01 \"夢の一枚\" (The Card of Dreams, unofficial translation) is the first Premium Extra Booster: 8 cards per pack, every card foil, ¥440 per pack, releasing in Japan on Saturday, April 24, 2027. Key facts, FAQ and where to buy.",
            "about": [
                "夢の一枚 (PEB-01, roughly \"The Card of Dreams\", unofficial translation) is the first set of Premium Extra Booster, a brand-new product line of the Japanese ONE PIECE Card Game. It releases in Japan on {rel}.",
                "Each pack costs ¥{pack} ({packl}), more than a regular ¥240 booster, and contains {per_pack} cards, all of them foil (holo). The number of packs per box and the card list have not been announced yet.",
                "It was announced in the official special broadcast on November 6, 2026 together with OP-18, EB-06 and OP-19. This page is updated as soon as the box configuration, card list and Japanese market prices are available.",
            ],
            "faq": [
                ("What is PEB-01 / Premium Extra Booster?", "A new ONE PIECE Card Game product line announced on November 6, 2026. PEB-01 夢の一枚 is its first set: a premium pack in which every card is foil."),
                ("How many cards are in a PEB-01 pack, and are they all foil?", "{per_pack} cards per pack, and yes, every card is foil (holo), according to the official announcement."),
                ("How much does PEB-01 cost and how many packs are in a box?", "¥{pack} per pack ({packl}) at Japanese MSRP. The number of packs per box has not been announced yet."),
                ("When does PEB-01 come out in Japan?", "{rel}. An English edition has not been announced."),
            ],
        },
    },
    "zh-tw": {
        "神の支配": {
            "title": "OP-18 神の支配 日版發售日（2026/11/21）、定價與預購｜航海王卡牌",
            "h1": "OP-18「神の支配」日版 發售日、定價與預購",
            "desc": "日版航海王卡牌補充包 OP-18「神の支配」（暫譯：神之支配）2026年11月21日（六）在日本發售，每包240日圓、一盒24包5,760日圓。已公開卡片、重點整理、常見問題與日版購買方式。",
            "about": [
                "「神の支配」（OP-18，暫譯「神之支配」，英文版名 The Dominance of God）是日版航海王卡牌（ONE PIECE CARD GAME）的第18彈補充包，{rel}在日本發售，每包{pack}日圓（{packl}），一盒24包{box}日圓（{boxl}）。",
                "在2026年11月6日的官方特別節目中，公開了領航員卡「卡魯（Carue）」「Miss All Sunday」「蒙其·D·魯夫」「斯潘達姆（Spandam）」的異圖版本，以及由天野喜孝繪製的「Saint Shamrock（シャムロック聖）」與「洛基（Loki）」實體卡。",
                "{en_line}開賣之後，這一頁會每天更新日版未拆封卡盒在日本的實際成交價。",
            ],
            "faq": [
                ("OP-18「神の支配」日版什麼時候發售？", "{rel}在日本發售。日版航海王卡牌的補充包通常在星期六發售。"),
                ("OP-18 日版一包、一盒多少錢？", "日本建議售價每包{pack}日圓（{packl}），一盒24包{box}日圓（{boxl}）。熱門系列開賣後市價常高於定價，開賣後這一頁會顯示日本的實際成交價。"),
                ("OP-18 已經公開了哪些卡？", "2026年11月6日的官方特別節目公開了卡魯、Miss All Sunday、蒙其·D·魯夫、斯潘達姆的異圖領航員卡，以及天野喜孝繪製的 Saint Shamrock 與洛基。完整卡表請見日本官方網站。"),
            ],
        },
        "EAST BLUE": {
            "title": "EB-06 EAST BLUE 日版發售日（2027/1/30）、定價與預購｜航海王卡牌額外補充包",
            "h1": "EB-06「EAST BLUE」日版額外補充包 發售日、定價與預購",
            "desc": "日版航海王卡牌額外補充包 EB-06「EAST BLUE」2027年1月30日（六）在日本發售，每包240日圓，主題是東海（East Blue）。重點整理、已公開插畫、常見問題與日版購買方式。",
            "about": [
                "「EAST BLUE」（EB-06）是日版航海王卡牌的第6彈額外補充包（Extra Booster），主題是故事起點的東海（East Blue），{rel}在日本發售，每包{pack}日圓（{packl}）。",
                "本彈在2026年11月6日的官方特別節目中與 OP-18、OP-19、PEB-01 一起發表，目前公開了包裝與2張新插畫；卡表、整盒的包數與英文版發售日都還沒有公布。",
                "日本的網購預購通常在發售前1～2個月開放。開賣後，這一頁會自動顯示日本的卡盒成交價。",
            ],
            "faq": [
                ("EB-06「EAST BLUE」日版什麼時候發售？", "{rel}在日本發售。"),
                ("EB-06 的主題是什麼？", "東海（East Blue），也就是故事的起點。2026年11月6日的官方特別節目公開了包裝與2張新插畫，卡表尚未公布。"),
                ("EB-06 日版一包多少錢？", "日本建議售價每包{pack}日圓（{packl}）。整盒的包數尚未公布。"),
                ("EB-06 會出英文版嗎？", "尚未公布。之前的額外補充包 EB-01～EB-05 都有英文版，所以很有機會，請以航海王卡牌官方網站的公告為準。"),
            ],
        },
        "応答せよ、世界": {
            "title": "OP-19 応答せよ、世界 日版發售日（2027/2/27）、定價與預購｜航海王卡牌",
            "h1": "OP-19「応答せよ、世界」日版 發售日、定價與預購",
            "desc": "日版航海王卡牌補充包 OP-19「応答せよ、世界」（暫譯：回應吧，世界；英文版名稱尚未公布）2027年2月27日（六）在日本發售，每包240日圓，主題是蛋頭島（Egghead）。重點整理、常見問題與日版購買方式。",
            "about": [
                "OP-19 是日版航海王卡牌的第19彈補充包，日文名稱「応答せよ、世界」（暫譯「回應吧，世界」，英文版名稱尚未公布），{rel}在日本發售，每包{pack}日圓（{packl}）。",
                "主題是蛋頭島（Egghead）。本彈在2026年11月6日的官方特別節目中發表，公開了包裝與2張新插畫；卡表與整盒的包數尚未公布。",
                "近期日版 OP 補充包與英文版幾乎同步發售（例如 OP-18 日版是11月21日、英文版是11月20日），但 OP-19 的英文版發售日還沒有公布。開賣後，這一頁會顯示日本的卡盒成交價。",
            ],
            "faq": [
                ("OP-19 日版什麼時候發售？", "{rel}在日本發售。"),
                ("OP-19 的英文版名稱是什麼？", "尚未公布。日文名稱是「応答せよ、世界」（暫譯「回應吧，世界」）。在官方公布之前，請用系列代碼 OP-19 搜尋。"),
                ("OP-19 的主題是什麼？", "根據2026年11月6日的官方特別節目，主題是蛋頭島（Egghead），已公開包裝與2張新插畫。"),
                ("OP-19 日版一包多少錢？", "日本建議售價每包{pack}日圓（{packl}）。整盒的包數尚未公布。"),
            ],
        },
        "夢の一枚": {
            "title": "PEB-01 夢の一枚 日版發售日（2027/4/24）、定價與內容｜航海王卡牌 Premium Extra Booster",
            "h1": "PEB-01「夢の一枚」Premium Extra Booster 日版 發售日、定價與內容",
            "desc": "日版航海王卡牌 PEB-01「夢の一枚」（暫譯：夢想的一張）是新系列 Premium Extra Booster 的第1彈：每包8張、全部閃卡、每包440日圓，2027年4月24日（六）在日本發售。重點整理、常見問題與購買方式。",
            "about": [
                "「夢の一枚」（PEB-01，暫譯「夢想的一張」）是日版航海王卡牌全新產品線 Premium Extra Booster（高級額外補充包）的第1彈，{rel}在日本發售。",
                "每包{pack}日圓（{packl}），比一般的240日圓補充包貴，每包{per_pack}張、而且全部都是閃卡。整盒的包數與卡表尚未公布。",
                "本彈在2026年11月6日的官方特別節目中與 OP-18、EB-06、OP-19 一起發表。整盒規格、卡表與日本市價一公布，這一頁就會更新。",
            ],
            "faq": [
                ("PEB-01／Premium Extra Booster 是什麼？", "2026年11月6日發表的航海王卡牌全新產品線。PEB-01「夢の一枚」是第1彈，是每一張卡都是閃卡的高級補充包。"),
                ("PEB-01 一包幾張？全部都是閃卡嗎？", "根據官方發表，每包{per_pack}張，而且全部都是閃卡。"),
                ("PEB-01 多少錢？一盒幾包？", "日本建議售價每包{pack}日圓（{packl}）。一盒的包數尚未公布。"),
                ("PEB-01 日版什麼時候發售？", "{rel}在日本發售。英文版尚未公布。"),
            ],
        },
    },
    "ko": {
        "神の支配": {
            "title": "OP-18 신의 지배 일판 발매일(2026.11.21)·정가·예약 | 원피스 카드",
            "h1": "OP-18 '신의 지배' 일판 발매일·정가·예약",
            "desc": "일판 원피스 카드 게임 부스터 OP-18 '신의 지배'(神の支配, 비공식 번역)는 2026년 11월 21일(토) 일본 발매, 1팩 240엔·1박스(24팩) 5,760엔. 공개 카드, 핵심 정보, FAQ, 일판 구매 방법.",
            "about": [
                "'신의 지배'(OP-18, 일본어 원제 神の支配·비공식 번역, 영문판명 The Dominance of God)는 일판 원피스 카드 게임의 18번째 부스터 팩으로, {rel} 일본에서 발매됩니다. 정가는 1팩 {pack}엔({packl}), 1박스 24팩 {box}엔({boxl})입니다.",
                "2026년 11월 6일 공식 특별 방송에서는 리더 카드 '카루', '미스 올 선데이', '몽키 D. 루피', '스팬덤'의 패러렐 일러스트 버전과, 아마노 요시타카가 그린 '샴록 성'(シャムロック聖)·'로키' 실물 카드가 공개되었습니다.",
                "{en_line}발매 후에는 일판 미개봉 박스의 일본 실거래가를 이 페이지에서 매일 업데이트합니다.",
            ],
            "faq": [
                ("OP-18 '신의 지배' 일판은 언제 발매되나요?", "{rel} 일본에서 발매됩니다. 일판 원피스 카드 부스터는 보통 토요일에 발매됩니다."),
                ("OP-18 일판 1팩·1박스 가격은 얼마인가요?", "일본 정가는 1팩 {pack}엔({packl}), 1박스 24팩 {box}엔({boxl})입니다. 인기 세트는 발매 후 정가보다 비싸게 거래되는 경우가 많으며, 발매 후 일본 실거래가를 이 페이지에 표시합니다."),
                ("OP-18에서 공개된 카드는 무엇인가요?", "2026년 11월 6일 공식 특별 방송에서 카루·미스 올 선데이·몽키 D. 루피·스팬덤의 패러렐 리더 카드와, 아마노 요시타카가 그린 샴록 성·로키 카드가 공개되었습니다. 전체 카드 리스트는 일본 공식 사이트를 확인하세요."),
            ],
        },
        "EAST BLUE": {
            "title": "EB-06 EAST BLUE 일판 발매일(2027.1.30)·정가·예약 | 원피스 카드 엑스트라 부스터",
            "h1": "EB-06 'EAST BLUE' 일판 엑스트라 부스터 발매일·정가·예약",
            "desc": "일판 원피스 카드 게임 엑스트라 부스터 EB-06 'EAST BLUE'는 2027년 1월 30일(토) 일본 발매, 1팩 240엔, 테마는 이스트 블루. 핵심 정보, 공개 일러스트, FAQ, 일판 구매 방법.",
            "about": [
                "'EAST BLUE'(EB-06)는 일판 원피스 카드 게임의 6번째 엑스트라 부스터로, 이야기가 시작되는 바다 '이스트 블루'가 테마입니다. {rel} 일본에서 발매되며 정가는 1팩 {pack}엔({packl})입니다.",
                "2026년 11월 6일 공식 특별 방송에서 OP-18, OP-19, PEB-01과 함께 발표되었고, 패키지와 새 일러스트 2종이 공개되었습니다. 카드 리스트, 박스 구성, 영문판 발매일은 아직 발표되지 않았습니다.",
                "일본 온라인 쇼핑몰의 예약은 보통 발매 1~2개월 전에 시작됩니다. 발매 후에는 일본 박스 실거래가가 이 페이지에 자동으로 표시됩니다.",
            ],
            "faq": [
                ("EB-06 'EAST BLUE' 일판은 언제 발매되나요?", "{rel} 일본에서 발매됩니다."),
                ("EB-06의 테마는 무엇인가요?", "이야기의 출발점인 이스트 블루입니다. 2026년 11월 6일 공식 특별 방송에서 패키지와 새 일러스트 2종이 공개되었고, 카드 리스트는 아직입니다."),
                ("EB-06 일판 1팩 가격은 얼마인가요?", "일본 정가 1팩 {pack}엔({packl})입니다. 박스 구성은 아직 발표되지 않았습니다."),
                ("EB-06 EAST BLUE 영문판도 나오나요?", "아직 발표되지 않았습니다. 이전 엑스트라 부스터 EB-01~EB-05는 모두 영문판이 나왔기 때문에 가능성은 높지만, 원피스 카드 게임 공식 사이트의 발표를 확인하세요."),
            ],
        },
        "応答せよ、世界": {
            "title": "OP-19 応答せよ、世界 일판 발매일(2027.2.27)·정가·예약 | 원피스 카드",
            "h1": "OP-19 '応答せよ、世界' 일판 발매일·정가·예약",
            "desc": "일판 원피스 카드 게임 부스터 OP-19 '応答せよ、世界'(응답하라, 세계·비공식 번역, 영문판명 미발표)는 2027년 2월 27일(토) 일본 발매, 1팩 240엔, 테마는 에그헤드. 핵심 정보, FAQ, 일판 구매 방법.",
            "about": [
                "OP-19는 일판 원피스 카드 게임의 19번째 부스터 팩입니다. 일본어 제목은 '応答せよ、世界'(대략 '응답하라, 세계'·비공식 번역)이며 영문판 제목은 아직 발표되지 않았습니다. {rel} 일본에서 발매되며 정가는 1팩 {pack}엔({packl})입니다.",
                "테마는 에그헤드입니다. 2026년 11월 6일 공식 특별 방송에서 발표되었고 패키지와 새 일러스트 2종이 공개되었습니다. 카드 리스트와 박스 구성은 아직 발표되지 않았습니다.",
                "최근 일판 OP 부스터와 영문판은 며칠 차이로 발매되고 있지만(예: OP-18은 일판 11월 21일, 영문판 11월 20일), OP-19의 영문판 발매일은 아직 발표되지 않았습니다. 발매 후에는 일본 박스 실거래가가 여기에 표시됩니다.",
            ],
            "faq": [
                ("OP-19 일판은 언제 발매되나요?", "{rel} 일본에서 발매됩니다."),
                ("OP-19의 영문판 이름은 무엇인가요?", "아직 발표되지 않았습니다. 일본어 제목은 '応答せよ、世界'(대략 '응답하라, 세계')입니다. 공식 발표 전까지는 세트 코드 OP-19로 검색하세요."),
                ("OP-19의 테마는 무엇인가요?", "2026년 11월 6일 공식 특별 방송에 따르면 에그헤드입니다. 패키지와 새 일러스트 2종이 공개되었습니다."),
                ("OP-19 일판 1팩 가격은 얼마인가요?", "일본 정가 1팩 {pack}엔({packl})입니다. 박스 구성은 아직 발표되지 않았습니다."),
            ],
        },
        "夢の一枚": {
            "title": "PEB-01 夢の一枚 일판 발매일(2027.4.24)·정가·구성 | 원피스 카드 프리미엄 엑스트라 부스터",
            "h1": "PEB-01 '夢の一枚' 프리미엄 엑스트라 부스터 일판 발매일·정가·구성",
            "desc": "일판 원피스 카드 게임 PEB-01 '夢の一枚'(꿈의 한 장·비공식 번역)는 신규 시리즈 '프리미엄 엑스트라 부스터' 1탄. 1팩 8장 전부 홀로 카드, 1팩 440엔, 2027년 4월 24일(토) 일본 발매. 핵심 정보, FAQ, 구매 방법.",
            "about": [
                "'夢の一枚'(PEB-01, 대략 '꿈의 한 장'·비공식 번역)는 일판 원피스 카드 게임의 새 상품 라인 '프리미엄 엑스트라 부스터(Premium Extra Booster)'의 첫 번째 세트로, {rel} 일본에서 발매됩니다.",
                "1팩 {pack}엔({packl})으로 일반 부스터(240엔)보다 비싸고, 1팩에 {per_pack}장이 들어 있으며 모든 카드가 홀로(반짝이) 카드입니다. 1박스의 팩 수와 카드 리스트는 아직 발표되지 않았습니다.",
                "2026년 11월 6일 공식 특별 방송에서 OP-18, EB-06, OP-19와 함께 발표되었습니다. 박스 구성, 카드 리스트, 일본 시세가 나오는 대로 이 페이지를 업데이트합니다.",
            ],
            "faq": [
                ("PEB-01 / 프리미엄 엑스트라 부스터는 무엇인가요?", "2026년 11월 6일 발표된 원피스 카드 게임의 새 상품 라인입니다. PEB-01 '夢の一枚'가 첫 세트로, 모든 카드가 홀로 카드인 프리미엄 팩입니다."),
                ("PEB-01은 1팩에 몇 장이고 전부 홀로 카드인가요?", "공식 발표 기준 1팩 {per_pack}장이며, 모든 카드가 홀로(반짝이) 카드입니다."),
                ("PEB-01 가격과 1박스 팩 수는요?", "일본 정가 1팩 {pack}엔({packl})입니다. 1박스의 팩 수는 아직 발표되지 않았습니다."),
                ("PEB-01 일판은 언제 발매되나요?", "{rel} 일본에서 발매됩니다. 영문판은 발표되지 않았습니다."),
            ],
        },
    },
}

BUY = {  # 日本での買い方ガイド（固定の文章）。2026/11/1 からの免税制度の変更も反映
    "en": [
        ("When do new Japanese sets come out?", "Japanese Pokémon sets are usually released on a Friday, and ONE PIECE sets on a Saturday. Check the release calendar on this site — Japanese Pokémon sets usually come out 2–4 months before the English set with the same cards, while ONE PIECE sets now release in Japan and English within days of each other."),
        ("Pokémon Center stores", "The official Pokémon Center stores (Tokyo, Osaka, Kyoto and more) sell new sets on release day, but popular sets often sell out within hours or are sold only by lottery (抽選) to members with a Japanese address and phone number. Check the store's official X account the day before."),
        ("Electronics stores, convenience stores and bookstores", "Yodobashi, Bic Camera, Yamada and bookstores sell new sets at MSRP, but in-demand products are mostly sold by lottery. Convenience stores (7-Eleven, FamilyMart, Lawson) sometimes have packs on release day, usually limited to a few packs per person."),
        ("Card shops in Akihabara, Nipponbashi and Nakano", "Specialist card shops sell singles and sealed boxes, usually above MSRP for popular sets. Compare shops — the box price table on this site shows what boxes actually sell for in Japan, so you can tell a fair price."),
        ("Tax-free shopping changed on November 1, 2026", "Japan switched to a refund system: you pay the full price including tax in the store, and the tax is refunded when you leave Japan after customs confirms your purchases (scan your passport at the tax-free terminal before check-in). You need to spend at least ¥5,000 (before tax) per store per day, keep the items unopened, and complete it within 90 days."),
        ("Watch out for resealed boxes", "Only buy sealed boxes from reputable shops. Japanese boxes have shrink wrap printed with the official logo; avoid boxes with loose or unbranded wrap."),
        ("Buying from the US", "If you can't visit Japan, Japanese sealed boxes and singles are sold on eBay, Amazon and TCGplayer by importers, or you can order from Japanese shops that ship abroad. Since August 29, 2025 the US no longer waives duties on low-value packages (the $800 de minimis exemption ended), so goods shipped from Japan can be charged import duty and carrier fees on top of shipping — compare the all-in cost with the Japan price on this site."),
    ],
    "zh-tw": [
        ("日版新彈什麼時候發售？", "日版寶可夢卡牌新彈通常在星期五發售，航海王卡牌通常在星期六。繁中版通常晚日版1～2週。請參考本站的發售日曆。"),
        ("寶可夢中心", "官方寶可夢中心（東京、大阪、京都等）會在發售日販售新彈，但熱門系列常在幾小時內售完，或只以抽選方式賣給有日本地址與電話的會員。建議前一天先看各店的官方X帳號。"),
        ("電器行、超商、書店", "Yodobashi、Bic Camera、Yamada等電器行與書店以原價販售新彈，但熱門商品大多是抽選。7-ELEVEN、全家、LAWSON等超商發售日偶爾會有卡包，通常每人限購數包。"),
        ("秋葉原、日本橋、中野的卡牌專賣店", "專賣店有單卡與未拆封卡盒，熱門系列多半高於建議售價。可以多比較幾家，本站的卡盒價格表是日本的實際成交價，可以判斷價格是否合理。"),
        ("2026年11月1日起免稅改為「退稅制」", "日本的免稅制度改為先付含稅價格、出境時退稅：在店裡照含稅價付款，離境時在機場報到前用護照在免稅手續機器完成海關確認後退還消費稅。同一家店同一天需購買稅前5,000日圓以上，商品不可拆封使用，並須在購買後90天內辦理。"),
        ("小心重新封膜的卡盒", "請在可信賴的店家購買未拆封卡盒。日版卡盒的收縮膜上印有官方標誌，封膜鬆弛或沒有標誌的請避免購買。"),
        ("從台灣、香港購買日版", "除了代購，蝦皮、露天與卡店也常有日版卡盒；eBay、日本亞馬遜（可海外配送的商品）也能直購。台灣進口完稅價格 NT$2,000 以下免稅（半年內以6次為限），超過要課關稅與營業稅。注意繁中版卡盒比日版便宜很多，下單前請確認封膜上是日文版標示。請用本站的日本市價加上運費與稅金，判斷價格是否合理。"),
    ],
    "ko": [
        ("일판 신규 세트는 언제 나오나요?", "일판 포켓몬 카드는 보통 금요일, 원피스 카드는 보통 토요일에 발매됩니다. 한글판은 보통 일판보다 3주~2개월 뒤에 나옵니다. 이 사이트의 발매일 캘린더를 확인하세요."),
        ("포켓몬센터", "공식 포켓몬센터(도쿄, 오사카, 교토 등)에서 발매일에 신규 세트를 판매하지만, 인기 세트는 몇 시간 만에 품절되거나 일본 주소와 전화번호가 있는 회원 대상 추첨으로만 판매되는 경우가 많습니다. 전날 각 매장의 공식 X 계정을 확인하세요."),
        ("가전 양판점·편의점·서점", "요도바시, 빅카메라, 야마다 등 가전 양판점과 서점은 정가로 판매하지만, 인기 상품은 대부분 추첨입니다. 세븐일레븐, 패밀리마트, 로손 등 편의점에도 발매일에 팩이 들어오기도 하며, 보통 1인당 몇 팩으로 제한됩니다."),
        ("아키하바라·닛폰바시·나카노의 카드 전문점", "전문점에서는 싱글 카드와 미개봉 박스를 판매하며, 인기 세트는 보통 정가보다 비쌉니다. 여러 매장을 비교해 보세요. 이 사이트의 박스 시세표는 일본 실거래가라서 적정 가격을 판단할 수 있습니다."),
        ("2026년 11월 1일부터 면세가 '환급 방식'으로 변경", "일본의 면세 제도가 바뀌어, 매장에서는 세금 포함 가격을 내고 출국할 때 환급받습니다. 공항에서 체크인 전에 면세 절차 단말기에 여권을 스캔해 세관 확인을 받으면 소비세가 환급됩니다. 같은 매장에서 하루 5,000엔(세전) 이상 구매해야 하며, 상품은 개봉하지 말고 구매 후 90일 이내에 절차를 마쳐야 합니다."),
        ("재포장 박스 주의", "미개봉 박스는 신뢰할 수 있는 매장에서만 구매하세요. 일판 박스의 수축 포장에는 공식 로고가 인쇄되어 있으며, 포장이 헐겁거나 로고가 없는 박스는 피하세요."),
        ("한국에서 일판 사는 곳 (직구·구매대행)", "크림(KREAM)·번개장터·카드샵에서 일판 박스가 거래되며, 아마존재팬 직구나 구매대행, eBay도 많이 씁니다. 해외직구는 물품가격 미화 150달러(미국발은 200달러)를 넘으면 관세·부가세가 붙으니, 이 사이트의 일본 시세에 배송비와 세금을 더해 가격이 적당한지 판단하세요."),
    ],
}

PARENT_PATH = {"box": "box-prices/", "cards": "card-prices/", "releases": "releases/"}
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
.ym{font-size:14px;margin:14px 0 2px;color:var(--ink2)}.ym:first-child{margin-top:0}
.faq h3{font-size:15px;margin:12px 0 4px}.faq h3:first-child{margin-top:0}.faq p{margin:0 0 8px}.kv th{width:36%;font-size:13px;color:var(--ink)}
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
    s = re.sub(r"([a-zXY])ex\b", r"\1 ex", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s if not re.search(r"[぀-ヿ]", s) else ""


def _josa(w):
    """韓国語の助詞「은/는」（最後の文字にパッチムがあるか）"""
    c = (w or " ")[-1]
    if "가" <= c <= "힣":
        return "은" if (ord(c) - 0xAC00) % 28 else "는"
    return "은(는)"


def fmt_date(L, iso):
    d = _dt.date.fromisoformat(iso)
    w = WEEK[L][d.weekday()]
    if L == "en":
        return f"{w}, {d.strftime('%b')} {d.day}, {d.year}"
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
            return f"약 {w / 10000:,.0f}만원" if w >= 1_000_000 else f"약 {round(w, -3 if w >= 10000 else -1):,.0f}원"
        return f"약 ${yen / fx:,.0f}"

    def ebay_url(q):
        u = f"https://www.ebay.com/sch/i.html?_nkw={quote(q)}"
        if ebay:
            u += f"&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={quote(ebay)}&customid=tcgchusen&toolid=10001&mkevt=1"
        return u

    jp_tag = (s.get("amazon_tag") or "").strip()

    def amz_url(L, q, g="", x=""):
        """英語はアメリカのAmazon。韓国・台湾は「アマゾンジャパン直購」が定着しているので日本のAmazon（日本語の弾名で検索）"""
        if L in ("ko", "zh-tw"):
            jq = f"{'ポケモンカード' if g == 'pokemon' else 'ワンピースカード'} {x} BOX"
            return f"https://www.amazon.co.jp/s?k={quote(jq)}&language=en_US" + (f"&tag={quote(jp_tag)}" if jp_tag else "")
        return f"https://www.amazon.com/s?k={quote(q)}" + (f"&tag={quote(az_tag)}" if az_tag else "")

    def kind_word(g, x):
        """検索語の最後に付ける商品の種類（デッキに「booster box」を付けない）"""
        ty = str(((info.get(g) or {}).get(x) or {}).get("type") or "")
        nm = f"{x} {set_name(g, x)}"
        if "BOX" in nm.upper() or "カードセット" in ty:
            return ""
        if "デッキ" in ty or "スターター" in ty or "デッキ" in x:
            return "deck"
        return "booster box"

    def buy_btns(g, x, t, L="en"):
        code = set_info(g, x)[0]
        nm = set_name(g, x)
        q = " ".join(w for w in ("Japanese", "Pokemon" if g == "pokemon" else "One Piece", nm,
                                  code if code and code.lower() not in nm.lower() else "", kind_word(g, x)) if w)
        return (f'<span class="buy"><a class="b-eb" href="{escape(ebay_url(q))}" {rel_a}>{t["ebay"]}</a>'
                f'<a class="b-az" href="{escape(amz_url(L, q, g, x))}" {rel_a}>{t["amazon"]}</a></span>')

    def names_html(L, g, x, t, with_jp=True):
        """弾の名前（日本版の英語名＋コード）と、その下に日本語名・現地の公式名・英語版の弾"""
        code, en, ctp, zh, ko = set_info(g, x)
        top = f'<b>{escape(en)}</b>' + (f'<span class="code">{escape(code)}</span>' if code and code.lower() != en.lower() else "")
        sub = []
        if with_jp and x != en:
            sub.append(x)
        loc = zh if L == "zh-tw" else ko if L == "ko" else ""
        if loc:
            sub.append(f"{t['local']} '{loc}'" if L == "ko" else f'{t["local"]}「{loc}」')
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
        return f'<span class="rl">{escape(SEP[L].join(parts))}</span>' if parts else ""

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
            cards.append({"g": g, "x": x, "label": v.get("label") or "", "num": v.get("num") or "", "p": p,
                          "ser": v.get("jp") or {}, "old": _ago(v.get("jp") or {}, 30)})
    cards.sort(key=lambda c: -c["p"])

    d0 = (today - _dt.timedelta(days=365)).isoformat()  # 11/8：75日→365日（過去の弾の「発売日」検索も拾う）
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
        h = [(f'<p class="note">{t["affnote"]}</p>' if t["affnote"] else "") + f'<div class="tw"><table><tr><th>{t["set"]}</th><th class="n">{t["price"]}</th><th class="n hide-s">{t["msrp"]}</th>'
             f'<th class="n">{t["x"]}</th><th class="n hide-s">{t["chg"]}</th></tr>']
        for r in rs:
            top, sub = names_html(L, game, r["x"], t)
            top = f'<a href="/{L}/sets/{set_slug(game, r["x"])}/" style="color:inherit">{top}</a>'
            mult = f'×{r["p"] / r["teika"]:.1f}' if r.get("teika") else "–"
            us = f'<span class="jp">{t["us"]}: ${r["us"]:,.0f}</span>' if (r["us"] and game == "pokemon") else ""
            h.append(f'<tr><td>{top}<span class="jp">{escape(sub)}</span>{rel_line(L, game, r["x"], t, r["rel"])}{buy_btns(game, r["x"], t, L)}</td>'
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
            gw = "Pokemon" if c["g"] == "pokemon" else "One Piece"
            q = " ".join(w for w in ((en or gw), c["num"], "Japanese" if en else f"Japanese {gw}") if w)
            cu = card_url.get((c["label"], c["num"]))
            nm_ = f'<a href="/{L}/{cu}" style="color:inherit">{escape(en or c["label"])}</a>' if cu else escape(en or c["label"])
            h.append(f'<tr><td><b>{nm_}</b><span class="jp">{escape(c["num"])}'
                     + (f' · {escape(c["label"])}' if en else "")
                     + f'</span><span class="buy"><a class="b-eb" href="{escape(ebay_url(q))}" {rel_a}>{t["ebay"]}</a></span></td>'
                     f'<td class="hide-s">{escape(set_name(c["g"], c["x"]))}' + (f'<span class="code">{escape(code)}</span>' if code else "") + '</td>'
                     f'<td class="n"><b>¥{c["p"]:,}</b><span class="jp">{money(L, c["p"])}</span></td></tr>')
        h.append("</table></div>")
        return "".join(h)

    def rel_list(L, t, only_future=False, limit=None):
        rs = (fut if only_future else rels)[:limit]
        h, ym = [], ""
        for r, g, x, inf in rs:
            if not only_future and r[:7] != ym:
                ym = r[:7]
                y_, m_ = int(r[:4]), int(r[5:7])
                lab = (f"{_dt.date(y_, m_, 1).strftime('%B')} {y_}" if L == "en" else f"{y_}年{m_}月" if L == "zh-tw" else f"{y_}년 {m_}월")
                h.append(f'<h3 class="ym">{lab}</h3>')
            ty = TYPE_T.get(re.sub(r"【.*?】", "", inf.get("type") or ""), {}).get(L) or ""
            yen = re.findall(r"([\d,]+)円", inf.get("price") or "")
            top, sub = names_html(L, g, x, t)
            if (g, x) in row_of or any(p_[1] == g and p_[2] == x for p_ in pre_sets):  # 11/8 弾のページへ
                top = f'<a href="/{L}/sets/{set_slug(g, x)}/" style="color:inherit">{top}</a>'
            msrp_ = f'{t["msrp"]} ¥{yen[-1]} ({money(L, int(yen[-1].replace(",", "")))})' if yen else ""
            if g == "onepiece" and x in OP_NEW:  # 11/8 新弾4つは「1パックの値段」と、公式に出ていれば1BOXも（PEB-01 は1BOXが未発表なので誤解がないように）
                d_ = OP_NEW[x]
                msrp_ = OP_NEW_LBL[L]["pack_short"].format(pack=f"{d_['pack']:,}") + (f' · {OP_NEW_LBL[L]["box_v"].format(n=d_["box"][0], box=f"{d_['box'][1]:,}", boxl=money(L, d_["box"][1]))}' if d_["box"] else "")
            extra = [e for e in (sub, ty, msrp_) if e]
            h.append(f'<div class="rel"><time datetime="{r}">{fmt_date(L, r)}</time><div><span class="g">{"Pokémon" if g == "pokemon" else "ONE PIECE"}</span>'
                     f'{top}' + (f'<span class="soon">{t["unreleased"]}</span>' if r > tdy else "")
                     + f'<span class="jp">{escape(" · ".join(extra))}</span>{rel_line(L, g, x, t, r).replace(escape(t["jprel"] + " " + fmt_date(L, r) + SEP[L]), "").replace(escape(t["jprel"] + " " + fmt_date(L, r)), "")}</div></div>')
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
            return f"{v / 10000:,.0f}만원" if v >= 1_000_000 else f"{v:,.0f}원"
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

    def loc_usd(L, usd):
        """ドルの値段を、韓国・台湾のページではその国の通貨でも"""
        if L == "en" or not usd:
            return ""
        v, unit = to_cur(L, usd * fx)
        return ("약 " if unit == "원" else "約") + cur_fmt(L, v, unit)

    def set_text(L, t, r):
        """弾ページの説明文（持っているデータから3〜4文を作る。無い値の文は省く）"""
        g, x = r["g"], r["x"]
        code, en, ctp, zh, ko = set_info(g, x)
        nm = (zh if L == "zh-tw" else ko if L == "ko" else "") or en
        cd = code if code and code.lower() != nm.lower() else ""
        inf = (info.get(g) or {}).get(x) or {}
        ty = TYPE_T.get(re.sub(r"【.*?】", "", inf.get("type") or ""), {}).get(L) or ""
        lr = (LOCAL_REL.get(g) or {}).get(x) or {}
        jp, msrp = f'¥{r["p"]:,}', (f'¥{r["teika"]:,}' if r.get("teika") else "")
        mult = f'{r["p"] / r["teika"]:.1f}' if r.get("teika") else ""
        c30 = ""
        if r["old"]:
            c = (r["p"] - r["old"]) / r["old"] * 100
            c30 = f'{"+" if c >= 0 else ""}{c:.0f}%'
        rel = fmt_date(L, r["rel"]) if r["rel"] else ""
        enrel = fmt_date(L, lr["en"]) if lr.get("en") else ""
        out_ = []
        if L == "en":
            ty_ = ty.lower() if ty else "set"
            out_.append(f"{nm}{f' ({cd})' if cd else ''} is a Japanese {'Pokémon TCG' if g == 'pokemon' else 'ONE PIECE Card Game'} {ty_}"
                        + (f" released in Japan on {rel}" if rel else "") + (f" at an MSRP of {msrp}" if msrp else "") + ".")
            out_.append(f"A sealed Japanese box currently sells for about {jp} ({money(L, r['p'])}) on the Japanese market"
                        + (f" — {mult}× MSRP" if mult else "") + (f", {c30} over the last 30 days" if c30 else "") + ".")
            if ctp and ctp != en:
                out_.append(f"The English set with the same cards is {ctp}" + (f", released on {enrel}" if enrel else "") + ".")
        elif L == "zh-tw":
            out_.append(f"{nm}{f'（{cd}）' if cd else ''}是" + (f"{rel}在日本發售的" if rel else "") + f"日版{'寶可夢卡牌' if g == 'pokemon' else '航海王卡牌'}{ty or '商品'}"
                        + (f"，建議售價{msrp}" if msrp else "") + "。")
            out_.append(f"目前日版未拆封卡盒在日本的成交價約{jp}（{money(L, r['p'])}）" + (f"，為定價的{mult}倍" if mult else "")
                        + (f"，近30日{c30}" if c30 else "") + "。")
            if zh and lr.get("tw"):
                out_.append(f"繁中版「{zh}」於{fmt_date(L, lr['tw'])}發售。")
            if ctp and ctp != en:
                out_.append(f"收錄相同卡片的英文版為 {ctp}" + (f"（{enrel}）" if enrel else "") + "。")
        else:
            out_.append(f"{nm}{f'({cd})' if cd else ''}" + _josa(nm) + (f" {rel} 일본에서 발매된" if rel else "")
                        + f" 일판 {'포켓몬 카드' if g == 'pokemon' else '원피스 카드'} {ty or '상품'}" + (f"으로 정가는 {msrp}입니다." if msrp else "입니다."))
            out_.append(f"현재 일판 미개봉 박스의 일본 실거래가는 {jp}({money(L, r['p'])})" + (f", 정가의 {mult}배" if mult else "")
                        + (f"이며 최근 30일 변동은 {c30}입니다." if c30 else "입니다."))
            if ko and lr.get("kr"):
                out_.append(f"한글판 '{ko}'은(는) {fmt_date(L, lr['kr'])}에 발매되었습니다.")
            if ctp and ctp != en:
                out_.append(f"같은 카드가 수록된 영문판은 {ctp}" + (f"({enrel})" if enrel else "") + "입니다.")
        return ("" if L == "zh-tw" else " ").join(out_)

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
            stats.append((t["ln_us"], f'${us_now:,.0f}', loc_usd(L, us_now)))
        if en_now:
            stats.append((t["ln_en"], f'${en_now:,.0f}', " ".join(w for w in (loc_usd(L, en_now), "" if r["en_kind"] == "box" else t["etb"]) if w)))
        kr_now, _ = _last(r["krser"])
        if kr_now:
            stats.append((t["ln_kr"], f'${kr_now:,.0f}', "eBay"))
        tw_now, _ = _last(r["twser"])
        if tw_now:
            stats.append((t["ln_tw"], f'${tw_now:,.0f}', "eBay"))
        st_html = "".join(f'<div class="stat"><small>{escape(a)}</small><b>{b}</b><span>{escape(c)}</span></div>' for a, b, c in stats)
        extra, ld = "", []
        if g == "onepiece" and x in OP_NEW:  # 11/8 新弾4つは、相場が出たあとも説明・表・FAQを残す。発売前のうちは発売日の入った題名に
            o = op_new_parts(L, t, x, full=True)
            extra, ld = o["body"], o["ld"]
            if r["rel"] and r["rel"] > tdy:
                title, h1, desc = o["title"], o["h1"], o["desc"]
        body = (f'<p class="lead">{escape(set_text(L, t, r))}</p><div class="card">{top}<span class="jp">{escape(sub)}</span>{rel_line(L, g, x, t, r["rel"])}{buy_btns(g, x, t, L)}</div>'
                f'<div class="stats">{st_html}</div><h2>{escape(t["chart"])}</h2>{chart_svg(L, t, r)}'
                + (f'<p class="note">{escape(t["no_local"])}</p>' if (L == "zh-tw" and r["twser"]) or (L == "ko" and r["krser"]) else "")
                + extra
                + f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/releases/">{t["releases"]} →</a></p>')
        return (f"sets/{set_slug(g, x)}/", "set", title, h1, desc, "", body, "box", ld)

    # ===== 11/8 細かい検索語の受け皿ページ =====
    # (1) カードごとのページ：「Mew ex 205/165 japanese price」「Mega Charizard X ex SAR M2 japanese」など
    seen_cs = set()
    card_pages = []
    for c in cards:
        en_ = card_name(c["label"])
        if not en_ or not c["ser"]:
            continue
        sl = re.sub(r"[^a-z0-9]+", "-", f'{en_} {c["num"]}'.lower().replace("é", "e")).strip("-")[:70]
        sl = f'{"pokemon" if c["g"] == "pokemon" else "one-piece"}-{sl}'
        if sl in seen_cs:
            continue
        seen_cs.add(sl)
        card_pages.append(dict(c, en=en_, slug=sl))
    card_url = {(c["label"], c["num"]): f'cards/{c["slug"]}/' for c in card_pages}

    CT = {
        "en": {"title": "{name} {num} Japanese Card Price & Chart ({set})", "h1": "{name} {num} — Japanese card price",
               "desc": "What the Japanese {name} ({num}) from {set} sells for in Japan right now: {jp} ({local}), {chg} in 30 days. Ungraded sold prices with a price chart.",
               "lead": "{name} ({num}) is a card from the Japanese {game} set {set}. The latest ungraded sold price in Japan is {jp} ({local}){chg2}. Prices are recent SNKRDUNK sales in Japan, not asking prices.",
               "ebay": "Find the Japanese {name} on eBay", "set": "Japanese box price of {set}", "chart": "Japan price chart (ungraded)",
               "pre_title": "{name} ({code}) Japanese Release Date, MSRP & Pre-order", "pre_h1": "{name} ({code}) — Japanese release date",
               "pre_desc": "{name} {code} releases in Japan on {rel}. MSRP {msrp}{en_}. Release info for the Japanese {game} set, updated daily.",
               "pre_lead": "{name}{code2} is a Japanese {game} {type} releasing in Japan on {rel}{msrp2}.{en2} Box prices in Japan will appear here once it starts selling.",
               "idx_title": "All Japanese Pokémon & One Piece Sets: Codes, English Names & Box Prices", "idx_h1": "Japanese set list",
               "idx_desc": "Every Japanese Pokémon TCG and One Piece Card Game set with its set code, English name, English counterpart, Japan release date and current box price.",
               "idx_lead": "Japanese sets with their code, the English name we use, the matching English set and the latest sealed box price in Japan.",
               "rel": "Release", "price": "Box price"},
        "zh-tw": {"title": "{name} {num} 日版卡價格與走勢｜{set}", "h1": "{name} {num} 日版單卡價格",
                  "desc": "日版 {name}（{num}，收錄於{set}）目前在日本的成交價{jp}（{local}），近30日{chg}。未鑑定裸卡的實際成交價與走勢圖。",
                  "lead": "{name}（{num}）是日版{game}「{set}」收錄的卡片。日本最新的未鑑定成交價為{jp}（{local}）{chg2}。價格為日本 SNKRDUNK 的實際成交價，非掛牌價。",
                  "ebay": "在 eBay 找日版 {name}", "set": "{set} 日版卡盒價格", "chart": "日本價格走勢（未鑑定）",
                  "pre_title": "{name}（{code}）日版發售日、定價與預購", "pre_h1": "{name}（{code}）日版發售日",
                  "pre_desc": "日版 {name} {code} 將於{rel}在日本發售，建議售價{msrp}{en_}。日版{game}新彈資訊，每日更新。",
                  "pre_lead": "{name}{code2}是{rel}在日本發售的日版{game}{type}{msrp2}。{en2}開賣後這裡會顯示日本的卡盒成交價。",
                  "idx_title": "日版寶可夢卡牌、航海王卡牌 全系列一覽｜代碼、英文名、卡盒價格", "idx_h1": "日版系列一覽",
                  "idx_desc": "日版寶可夢卡牌與航海王卡牌的所有系列：系列代碼、英文名稱、對應英文版、日本發售日與目前卡盒價格。",
                  "idx_lead": "日版各系列的代碼、英文名稱、對應的英文版系列，以及日本最新的未拆封卡盒價格。",
                  "rel": "發售日", "price": "卡盒價格"},
        "ko": {"title": "{name} {num} 일판 카드 시세·차트 | {set}", "h1": "{name} {num} 일판 카드 시세",
               "desc": "일판 {name}({num}, {set} 수록)의 일본 실거래가 {jp}({local}), 최근 30일 {chg}. 미감정 카드 실거래가와 시세 차트.",
               "lead": "{name}({num})은(는) 일판 {game} '{set}'에 수록된 카드입니다. 일본 최근 미감정 실거래가는 {jp}({local}){chg2}. 가격은 일본 SNKRDUNK의 실제 거래가이며 호가가 아닙니다.",
               "ebay": "eBay에서 일판 {name} 찾기", "set": "{set} 일판 박스 시세", "chart": "일본 시세 차트(미감정)",
               "pre_title": "{name} ({code}) 일판 발매일·정가·예약", "pre_h1": "{name} ({code}) 일판 발매일",
               "pre_desc": "일판 {name} {code} 일본 발매일 {rel}, 정가 {msrp}{en_}. 일판 {game} 신규 세트 정보를 매일 업데이트합니다.",
               "pre_lead": "{name}{code2}은(는) {rel} 일본에서 발매되는 일판 {game} {type}입니다.{msrp2}{en2} 발매 후에는 일본 박스 실거래가가 여기에 표시됩니다.",
               "idx_title": "일판 포켓몬카드·원피스 카드 전체 세트 목록 | 코드·영문명·박스 시세", "idx_h1": "일판 세트 목록",
               "idx_desc": "일판 포켓몬 카드 게임·원피스 카드 게임 전체 세트의 세트 코드, 영문명, 대응 영문판, 일본 발매일과 현재 박스 시세.",
               "idx_lead": "일판 세트별 코드, 영문명, 대응 영문판 세트, 그리고 일본 최신 미개봉 박스 시세입니다.",
               "rel": "발매일", "price": "박스 시세"},
    }
    GAME_L = {"en": {"pokemon": "Pokémon TCG", "onepiece": "ONE PIECE Card Game"},
              "zh-tw": {"pokemon": "寶可夢卡牌", "onepiece": "航海王卡牌"},
              "ko": {"pokemon": "포켓몬 카드", "onepiece": "원피스 카드"}}
    row_of = {(r["g"], r["x"]): r for r in rows}

    def _chg(ser, old, now_):
        if not old:
            return "–"
        c_ = (now_ - old) / old * 100
        return f'{"+" if c_ >= 0 else ""}{c_:.0f}%'

    def card_page(L, t, c):
        ct, g = CT[L], c["g"]
        sname = set_name(g, c["x"])
        ch = _chg(c["ser"], c["old"], c["p"])
        f = dict(name=c["en"], num=c["num"], set=sname, jp=f'¥{c["p"]:,}', local=money(L, c["p"]), chg=ch,
                 chg2=(f" ({ch} in 30 days)" if L == "en" else f"，近30日{ch}" if L == "zh-tw" else f", 최근 30일 {ch}") if ch != "–" else "",
                 game=GAME_L[L][g])
        title, h1, desc, lead = (ct["title"].format(**f), ct["h1"].format(**f), ct["desc"].format(**f), ct["lead"].format(**f))
        if ch == "–":
            desc = re.sub(r"[,，、]?\s*(\{chg\}|–)[^.。]*", "", desc)
        q = " ".join(w for w in (c["en"], c["num"], "Japanese") if w)
        r_ = {"g": g, "jpser": c["ser"], "usser": {}, "enser": {}, "krser": {}, "twser": {}, "en_kind": "box"}
        rr = row_of.get((g, c["x"]))
        body = (f'<div class="stats"><div class="stat"><small>{escape(t["price"])}</small><b>¥{c["p"]:,}</b><span>{escape(money(L, c["p"]))}</span></div>'
                f'<div class="stat"><small>{escape(t["chg"])}</small><b>{escape(ch)}</b><span></span></div></div>'
                f'<p><span class="buy"><a class="b-eb" href="{escape(ebay_url(q))}" {rel_a}>{escape(ct["ebay"].format(**f))}</a></span></p>'
                + (f'<p class="note">{t["affnote"]}</p>' if t["affnote"] else "")
                + f'<h2>{escape(ct["chart"])}</h2>{chart_svg(L, t, r_)}'
                + (f'<p><a href="/{L}/sets/{set_slug(g, c["x"])}/">{escape(ct["set"].format(**f))} →</a></p>' if rr else "")
                + f'<p><a href="/{L}/card-prices/">{t["cards"]} →</a></p>')
        return (f'cards/{c["slug"]}/', "card", title, h1, desc, lead, body, "cards")

    # (2) 発売前・相場がまだの弾（「Aura Seeker japanese release date」「M7 japanese」など）
    have = set(row_of)
    pre_sets = []
    for r_, g_, x_, inf_ in rels:
        if (g_, x_) in have or r_ < (today - _dt.timedelta(days=30)).isoformat():
            continue
        code_, en_ = set_info(g_, x_)[:2]
        if not code_ and en_ == x_:  # 英語名もコードもわからない弾は作らない（日本語のままのページになる）
            continue
        pre_sets.append((r_, g_, x_, inf_))

    # ---- 11/8 ワンピースの新弾4つ（OP-18・EB-06・OP-19・PEB-01）：説明・重点の表・FAQ（FAQPage の構造化データ付き）・4弾の相互リンク ----
    jp_slugs = ((s.get("series_slugs") or {}).get("onepiece") or {})

    def op_new_links(L, t, cur=None):
        """4弾を互いにリンクする小さな一覧（発売日順）。cur＝いま見ている弾（リンクしない）"""
        lb = OP_NEW_LBL[L]
        h = []
        for x in OP_NEW_ORDER:
            d = OP_NEW[x]
            code, en = set_info("onepiece", x)[:2]
            nm = f'<b>{escape(en)}</b>' + (f'<span class="code">{escape(code)}</span>' if code.lower() not in en.lower() else "")
            if x != cur:
                nm = f'<a href="/{L}/sets/{set_slug("onepiece", x)}/" style="color:inherit">{nm}</a>'
            sub = [x if x != en else "", lb["kind"].get(code, ""), lb["pack_short"].format(pack=f"{d['pack']:,}")]
            h.append(f'<div class="rel"><time datetime="{d["rel"]}">{fmt_date(L, d["rel"])}</time><div>{nm}'
                     + (f'<span class="soon">{t["unreleased"]}</span>' if d["rel"] > tdy else "")
                     + f'<span class="jp">{escape(" · ".join(w for w in sub if w))}</span></div></div>')
        return f'<h2>{escape(lb["h_links"])}</h2><div class="card">{"".join(h)}</div>'

    def op_new_parts(L, t, x, full=False):
        """弾ページに足す部分：title/h1/desc/lead の差し替え、本文のHTML、FAQPage の構造化データ
        full=True（相場のあるページ）は説明の1文目も本文に入れる（lead は相場の文章が使うため）"""
        d, lb, tx = OP_NEW[x], OP_NEW_LBL[L], OP_NEW_T[L][x]
        code, en, ctp, zh, ko = set_info("onepiece", x)
        lr = (LOCAL_REL.get("onepiece") or {}).get(x) or {}
        enrel = fmt_date(L, lr["en"]) if lr.get("en") else ""
        en_line = ""
        if enrel and ctp:
            en_line = {"en": f"The English edition, {ctp}, launches on {enrel}, so the Japanese box is mainly for collectors who want Japanese-text cards. ",
                       "zh-tw": f"英文版 {ctp} 於{enrel}發售，想收日文卡的人再買日版即可。",
                       "ko": f"영문판 {ctp}{_josa(ctp)} {enrel} 발매이므로, 일판 박스는 일본어 카드를 모으는 분께 적합합니다. "}[L]
        f = dict(rel=fmt_date(L, d["rel"]), pack=f"{d['pack']:,}", packl=money(L, d["pack"]),
                 box=f"{d['box'][1]:,}" if d["box"] else "", boxl=money(L, d["box"][1]) if d["box"] else "",
                 per_pack=d["per_pack"] or "", enrel=enrel, en_line=en_line)
        about = [a.format(**f) for a in tx["about"]]
        faq = [(q.format(**f), a.format(**f)) for q, a in tx["faq"]]
        rows_ = [(lb["rel"], fmt_date(L, d["rel"])), (lb["type"], lb["kind"].get(code, "")), (lb["price"], lb["pack_v"].format(**f))]
        if d["box"]:
            rows_.append((lb["box"], lb["box_v"].format(n=d["box"][0], **f)))
        elif code == "PEB-01":
            rows_.append((lb["box"], lb["tba"]))
        if d["per_pack"]:
            rows_.append((lb["per_pack"], lb["per_pack_v"].format(n=d["per_pack"])))
        if lb["theme_v"].get(code):
            rows_.append((lb["theme"], lb["theme_v"][code]))
        rows_.append((lb["ann"], lb["ann_v"]))
        rows_.append((lb["en"], (f"{ctp} · {enrel}" if ctp and ctp != en else enrel) if enrel else lb["tbd_en"]))
        jp_url = f'/onepiece/{jp_slugs.get(x) or d["jp_slug"]}/'
        rows_.append((lb["jp"], f'<a href="{jp_url}" hreflang="ja">{escape(x)}</a>'))
        tbl = "".join(f'<tr><th>{escape(k)}</th><td>{v if k == lb["jp"] else escape(v)}</td></tr>' for k, v in rows_)
        body = (f'<h2>{escape(lb["h_about"])}</h2>' + "".join(f"<p>{escape(a)}</p>" for a in (about if full else about[1:]))
                + f'<h2>{escape(lb["h_facts"])}</h2><div class="tw"><table class="kv">{tbl}</table></div>'
                + f'<h2>{escape(lb["h_faq"])}</h2><div class="card faq">' + "".join(f"<h3>{escape(q)}</h3><p>{escape(a)}</p>" for q, a in faq) + "</div>"
                + op_new_links(L, t, x)
                + f'<p><a href="{jp_url}" hreflang="ja">{escape(lb["jp_link"])}</a></p>')
        ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        return {"title": tx["title"], "h1": tx["h1"], "desc": tx["desc"], "lead": about[0], "body": body, "ld": [ld]}

    def pre_page(L, t, r_, g, x, inf):
        ct = CT[L]
        code, en, ctp, zh, ko = set_info(g, x)
        nm = (zh if L == "zh-tw" else ko if L == "ko" else "") or en
        cd = code if code and code.lower() != nm.lower() else ""
        ty = TYPE_T.get(re.sub(r"【.*?】", "", inf.get("type") or ""), {}).get(L) or ("set" if L == "en" else "")
        yen = re.findall(r"([\d,]+)円", inf.get("price") or "")
        msrp = f'¥{yen[-1]} ({money(L, int(yen[-1].replace(",", "")))})' if yen else ""
        lr = (LOCAL_REL.get(g) or {}).get(x) or {}
        en_line = ""
        if ctp and ctp != en:
            en_line = {"en": f" The English set with the same cards is {ctp}" + (f" ({fmt_date(L, lr['en'])})" if lr.get("en") else "") + ".",
                       "zh-tw": f"收錄相同卡片的英文版為 {ctp}" + (f"（{fmt_date(L, lr['en'])}）" if lr.get("en") else "") + "。",
                       "ko": f" 같은 카드가 수록된 영문판은 {ctp}" + (f"({fmt_date(L, lr['en'])})" if lr.get("en") else "") + "입니다."}[L]
        f = dict(name=nm, code=cd or code, code2=(f" ({cd})" if L == "en" else f"（{cd}）" if L == "zh-tw" else f"({cd})") if cd else "",
                 rel=fmt_date(L, r_), msrp=msrp or "–", game=GAME_L[L][g], type=(ty.lower() if L == "en" else ty) or "",
                 msrp2=({"en": f" with an MSRP of {msrp}", "zh-tw": f"，建議售價{msrp}", "ko": f" 정가는 {msrp}입니다."}[L] if msrp else ""),
                 en_=({"en": f", English counterpart {ctp}", "zh-tw": f"，英文版為 {ctp}", "ko": f", 영문판 {ctp}"}[L] if ctp and ctp != en else ""),
                 en2=en_line)
        title = ct["pre_title"].format(**f).replace(" ()", "").replace("（）", "")
        h1 = ct["pre_h1"].format(**f).replace(" ()", "").replace("（）", "")
        top, sub = names_html(L, g, x, t)
        body = (f'<div class="card">{top}<span class="jp">{escape(sub)}</span>{rel_line(L, g, x, t, r_)}{buy_btns(g, x, t, L)}</div>'
                + (f'<p class="note">{t["affnote"]}</p>' if t["affnote"] else ""))
        tail = f'<p><a href="/{L}/releases/">{t["releases"]} →</a> · <a href="/{L}/box-prices/">{t["box"]} →</a></p>'
        if g == "onepiece" and x in OP_NEW:  # 11/8 新弾4つは説明・表・FAQ付きの厚いページに
            o = op_new_parts(L, t, x)
            return (f"sets/{set_slug(g, x)}/", "set", o["title"], o["h1"], o["desc"], o["lead"], body + o["body"] + tail, "releases", o["ld"])
        return (f"sets/{set_slug(g, x)}/", "set", title, h1, ct["pre_desc"].format(**f), ct["pre_lead"].format(**f), body + tail, "releases")

    # (3) 弾の一覧（「japanese pokemon set list」「japanese set codes」）
    def sets_index(L, t):
        ct = CT[L]
        h = []
        for g in ("pokemon", "onepiece"):
            lst = []
            for x, (code, en, ctp, zh, ko) in SETS.get(g, {}).items():
                rel = str(((info.get(g) or {}).get(x) or {}).get("release") or "")
                lst.append((rel, x, code, en, ctp, zh, ko))
            lst.sort(reverse=True)
            h.append(f'<h2>{t[g]}</h2><div class="tw"><table><tr><th>{t["set"]}</th><th class="hide-s">{t["counterpart"]}</th>'
                     f'<th class="n">{ct["rel"]}</th><th class="n">{ct["price"]}</th></tr>')
            for rel, x, code, en, ctp, zh, ko in lst:
                loc = zh if L == "zh-tw" else ko if L == "ko" else ""
                rr = row_of.get((g, x))
                linked = rr or any(p_[1] == g and p_[2] == x for p_ in pre_sets)
                nm = escape(en) + (f'<span class="code">{escape(code)}</span>' if code and code.lower() != en.lower() else "")
                nm = f'<a href="/{L}/sets/{set_slug(g, x)}/" style="color:inherit"><b>{nm}</b></a>' if linked else f"<b>{nm}</b>"
                h.append(f'<tr><td>{nm}<span class="jp">{escape(" · ".join(w for w in (x if x != en else "", loc) if w))}</span></td>'
                         f'<td class="hide-s">{escape(ctp if ctp and ctp != en else "–")}</td>'
                         f'<td class="n">{escape(fmt_date(L, rel)) if rel else "–"}</td>'
                         f'<td class="n">' + (f'¥{rr["p"]:,}<span class="jp">{escape(money(L, rr["p"]))}</span>' if rr else "–") + '</td></tr>')
            h.append("</table></div>")
        h.append(op_new_links(L, t))  # 11/8 ワンピースの新弾4つ
        return ("sets/", "setsidx", ct["idx_title"], ct["idx_h1"], ct["idx_desc"], ct["idx_lead"], "".join(h), None)

    ex_rel = ", ".join(" ".join(w for w in (set_name(g, x), set_info(g, x)[0] if set_info(g, x)[0].lower() != set_name(g, x).lower() else "") if w)
                       + f' ({r[5:7].lstrip("0")}/{r[8:]})' for r, g, x, _ in fut[:3])

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
                        f'<h2>{t["pokemon"]}{HSEP[L]}{t["movers"]}</h2>{price_table(L, t, "pokemon", 8)}'
                        f'<h2>{t["onepiece"]}{HSEP[L]}{t["movers"]}</h2>{price_table(L, t, "onepiece", 6)}'
                        f'<p><a href="/{L}/box-prices/">{t["box"]} →</a></p>'
                        f'<h2>{t["hot"]}</h2>{card_table(L, t, 10)}<p><a href="/{L}/card-prices/">{t["cards"]} →</a></p>'
                        f'<p><a href="/{L}/buy-in-japan/">{t["buy"]} →</a></p>')
            elif key == "releases":
                body = (f'<div class="card">{rel_list(L, t)}</div>{op_new_links(L, t)}'
                        f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/sets/">{t["setsidx"]} →</a></p>')
            elif key == "box":
                body = (f'<h2>{t["pokemon"]}</h2>{price_table(L, t, "pokemon")}<h2>{t["onepiece"]}</h2>{price_table(L, t, "onepiece")}'
                        f'<p><a href="/{L}/releases/">{t["releases"]} →</a> · <a href="/{L}/sets/">{t["setsidx"]} →</a></p>')
            elif key == "cards":
                body = card_table(L, t, 300) + f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/sets/">{t["setsidx"]} →</a></p>'
            else:
                body = "".join(f'<div class="card"><h2 style="margin-top:0">{escape(a)}</h2><p>{escape(b)}</p></div>' for a, b in BUY[L])
                body += f'<p><a href="/{L}/box-prices/">{t["box"]} →</a> · <a href="/{L}/releases/">{t["releases"]} →</a></p>'
            specs.append((path, key, title, h1, desc, lead, body, None))
        for r in rows:  # 弾ごとのページ（チャート付き）
            specs.append(set_page(L, t, r))
        # 11/8 細かい検索語の受け皿：発売前・相場がまだの弾、カードごと、弾の一覧
        for r_, g_, x_, inf_ in pre_sets:
            specs.append(pre_page(L, t, r_, g_, x_, inf_))
        for c in card_pages:
            specs.append(card_page(L, t, c))
        specs.append(sets_index(L, t))
        for path, key, title, h1, desc, lead, body, parent, *extra_ld in specs:  # 9つ目（あれば）＝ページ固有の構造化データ（FAQPage など）
            url = f"{site}/{L}/{path}"
            # hreflang：自分を含む全言語。中国語は zh-Hant・zh-TW・zh-HK を同じページに
            alt = "".join(f'<link rel="alternate" hreflang="{hl}" href="{site}/{l}/{path}">' for l, m in LANGS.items() for hl in m["hreflang"])
            alt += f'<link rel="alternate" hreflang="x-default" href="{site}/en/{path}">'
            # 構造化データ：パンくず・ページ（更新日）・一覧
            crumbs = [{"@type": "ListItem", "position": 1, "name": t["home"], "item": f"{site}/{L}/"}]
            if parent:
                crumbs.append({"@type": "ListItem", "position": 2, "name": t[parent], "item": f"{site}/{L}/{PARENT_PATH[parent]}"})
            if path:
                crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": h1 if parent else t[key], "item": url})
            ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs},
                  {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc, "url": url,
                   "inLanguage": meta["html"], "dateModified": tdy, "isPartOf": {"@type": "WebSite", "name": t["site"], "url": f"{site}/{L}/"}}]
            if key in ("box", "releases"):
                lst = [r for r in rows] if key == "box" else [{"g": g, "x": x} for _, g, x, _ in rels]
                items = []
                for i, r in enumerate(lst[:50]):
                    it = {"@type": "ListItem", "position": i + 1,
                          "name": f'{set_name(r["g"], r["x"])} {set_info(r["g"], r["x"])[0]}'.strip()}
                    # 弾のページが存在するものだけ url を付ける（相場あり or 発売前ページ）
                    if (r["g"], r["x"]) in row_of or any(p_[1] == r["g"] and p_[2] == r["x"] for p_ in pre_sets):
                        it["url"] = f'{site}/{L}/sets/{set_slug(r["g"], r["x"])}/'
                    items.append(it)
                ld.append({"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items})
            for x_ in extra_ld:
                ld.extend(x_ or [])
            ld_html ="".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
            og_img = f"{site}/og-{L}.png"
            ogalt = '<meta property="og:locale:alternate" content="zh_HK">' if L == "zh-tw" else ""
            cur = parent or key
            tabs = "".join(f'<a href="/{L}/{p}"{" aria-current=\"page\"" if k == cur else ""}>{t[k]}</a>' for p, k in PAGES)
            langs = "".join(f'<a href="/{l}/{path}" hreflang="{m["html"]}"{" aria-current=\"true\"" if l == L else ""}>{m["name"]}</a>' for l, m in LANGS.items())
            crumb_html = ""
            if parent:
                crumb_html = f'<p class="crumb"><a href="/{L}/">{t["home"]}</a> › <a href="/{L}/{PARENT_PATH[parent]}">{escape(t[parent])}</a> › {escape(h1)}</p>'
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
                    f'<footer><div class="w"><p>© {escape(t["site"])} (tcg-chusen.com) · <a href="/privacy.html">{t["privacy"]}</a></p></div></footer></body></html>')
            p = Path(out) / L / path / "index.html"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf-8")
            urls.append((url, tdy))
    return urls
