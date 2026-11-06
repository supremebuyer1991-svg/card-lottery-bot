"""海外向けページ（英語・中国語繁体字・韓国語）
日本のポケカ・ワンピースカードの発売日・BOX相場・高額カード・日本での買い方を、/en/ /zh-tw/ /ko/ に書き出す。
抽選情報は載せない（海外の人は応募できないため。2026/11/7 ユーザー指示）。
データは日本語サイトと同じもの（souba.json＝スニダンの取引相場、souba_cards.json、弾の発売日情報）を使う。
"""
import re
import datetime as _dt
from html import escape
from pathlib import Path
from urllib.parse import quote

LANGS = {
    "en": {"html": "en", "name": "English"},
    "zh-tw": {"html": "zh-Hant", "name": "繁體中文"},
    "ko": {"html": "ko", "name": "한국어"},
}

# ---- 弾の英語名（公式の英語名がある弾はそれ、ない弾はローマ字・意味の訳。ページに「非公式の訳」と書く）----
SET_EN = {
    "pokemon": {
        "ハドウシーカー": "Hadou Seeker", "スペシャルデッキセットMEGA": "Special Deck Set MEGA", "30周年御三家カードセット": "30th Anniversary Starter Card Set",
        "30th CELEBRATION": "30th CELEBRATION", "30周年 FUTURISTIC BOX": "30th CELEBRATION FUTURISTIC BOX",
        "30周年エーフィ・ブラッキーデッキ": "30th Premium Deck Set Espeon & Umbreon", "ストームエメラルダ": "Storm Emeralda",
        "スターターセットex": "Starter Set ex", "アビスアイ": "Abyss Eye", "ニンジャスピナー": "Ninja Spinner", "ムニキスゼロ": "Munikis Zero",
        "MEGAドリームex": "MEGA Dream ex", "インフェルノX": "Inferno X", "メガブレイブ": "Mega Brave", "メガシンフォニア": "Mega Symphonia",
        "ブラックボルト": "Black Bolt", "ホワイトフレア": "White Flare", "ロケット団の栄光": "Glory of Team Rocket", "熱風のアリーナ": "Heat Wave Arena",
        "バトルパートナーズ": "Battle Partners", "テラスタルフェスex": "Terastal Festival ex", "超電ブレイカー": "Super Electric Breaker",
        "楽園ドラゴーナ": "Paradise Dragona", "ステラミラクル": "Stellar Miracle", "ナイトワンダラー": "Night Wanderer", "変幻の仮面": "Mask of Change",
        "クリムゾンヘイズ": "Crimson Haze", "ワイルドフォース": "Wild Force", "サイバージャッジ": "Cyber Judge", "シャイニートレジャーex": "Shiny Treasure ex",
        "古代の咆哮": "Ancient Roar", "未来の一閃": "Future Flash", "レイジングサーフ": "Raging Surf", "黒炎の支配者": "Ruler of the Black Flame",
        "ポケモンカード151": "Pokémon Card 151", "スノーハザード": "Snow Hazard", "クレイバースト": "Clay Burst", "トリプレットビート": "Triplet Beat",
        "スカーレットex": "Scarlet ex", "バイオレットex": "Violet ex", "VSTARユニバース": "VSTAR Universe", "パラダイムトリガー": "Paradigm Trigger",
        "白熱のアルカナ": "Incandescent Arcana", "ロストアビス": "Lost Abyss", "ダークファンタズマ": "Dark Phantasma", "スペースジャグラー": "Space Juggler",
        "タイムゲイザー": "Time Gazer", "ポケモンGO": "Pokémon GO", "バトルリージョン": "Battle Region", "スターバース": "Star Birth",
        "VMAXクライマックス": "VMAX Climax", "25th ANNIVERSARY COLLECTION": "25th ANNIVERSARY COLLECTION", "フュージョンアーツ": "Fusion Arts",
        "蒼空ストリーム": "Blue Sky Stream", "摩天パーフェクト": "Skyscraping Perfection", "イーブイヒーローズ": "Eevee Heroes",
        "一撃マスター": "Single Strike Master", "連撃マスター": "Rapid Strike Master", "双璧のファイター": "Matchless Fighters",
        "漆黒のガイスト": "Jet-Black Spirit", "白銀のランス": "Silver Lance", "シャイニースターV": "Shiny Star V", "仰天のボルテッカー": "Amazing Volt Tackle",
        "伝説の鼓動": "Legendary Heartbeat", "爆炎ウォーカー": "Explosive Walker", "ムゲンゾーン": "Infinity Zone", "反逆クラッシュ": "Rebellion Crash",
        "タッグオールスターズ": "Tag Team GX All Stars", "ドリームリーグ": "Dream League", "リミックスバウト": "Remix Bout", "ダブルブレイズ": "Double Blaze",
        "タッグボルト": "Tag Bolt", "裂空のカリスマ": "Sky-Splitting Charisma", "20th Anniversary": "20th Anniversary",
    },
    "onepiece": {
        "神の支配": "OP-18", "ヒロインズエディション vol.2": "Heroines Edition vol.2 (EB-05)", "応答せよ、世界": "OP-19",
        "EAST BLUE": "EAST BLUE (EB-06)", "HEROINES PRECIOUS BOX": "HEROINES PRECIOUS BOX", "世界最強の戦士": "OP-17",
        "決戦の刻": "OP-16", "神の島の冒険": "Adventure on Kami's Island (OP-15)", "蒼海の七傑": "The Azure Sea's Seven (OP-14)",
        "受け継がれる意志": "Carrying On His Will (OP-13)", "師弟の絆": "Legacy of the Master (OP-12)", "神速の拳": "A Fist of Divine Speed (OP-11)",
        "王族の血統": "Royal Blood (OP-10)", "新たなる皇帝": "Emperors in the New World (OP-09)", "二つの伝説": "Two Legends (OP-08)",
        "500年後の未来": "500 Years in the Future (OP-07)", "双璧の覇者": "Wings of the Captain (OP-06)", "新時代の主役": "Awakening of the New Era (OP-05)",
        "謀略の王国": "Kingdoms of Intrigue (OP-04)", "強大な敵": "Pillars of Strength (OP-03)", "頂上決戦": "Paramount War (OP-02)",
        "ロマンスドーン": "Romance Dawn (OP-01)", "メモリアルコレクション": "Memorial Collection (EB-01)", "アニメ25thコレクション": "Anime 25th Collection (EB-02)",
        "ヒロインズエディション": "Heroines Edition (EB-03)", "EGGHEAD CRISIS": "EGGHEAD CRISIS (EB-04)",
        "ONE PIECE CARD THE BEST": "ONE PIECE CARD THE BEST (PRB-01)", "ONE PIECE CARD THE BEST vol.2": "ONE PIECE CARD THE BEST vol.2 (PRB-02)",
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
    "レッドコミパラ": "Red Manga Alt Art", "コミパラ": "Manga Alt Art", "海賊団スーパーパラレル": "Pirates Super Parallel",
    "3周年スペシャルカード": "3rd Anniversary Special", "金背景": "Gold", "銀背景": "Silver", "サインルフィ": "Signed Luffy",
    "レッド": "Red", "ブルー": "Blue", "グリーン": "Green", "（": " (", "）": ")",
}

T = {
    "en": {
        "site": "Japan TCG Navi", "tag": "Japanese Pokémon TCG & ONE PIECE Card Game: release dates and market prices from Japan",
        "home": "Home", "releases": "Japanese Release Calendar", "box": "Japanese Booster Box Prices", "cards": "Top Card Prices in Japan",
        "buy": "How to Buy Pokémon Cards in Japan", "pokemon": "Pokémon TCG (Japanese)", "onepiece": "ONE PIECE Card Game (Japanese)",
        "release": "Release", "msrp": "MSRP", "price": "Market price in Japan", "usd": "approx.", "x": "vs MSRP", "chg": "30-day change",
        "us": "US market (TCGplayer)", "set": "Set", "card": "Card", "no": "No.", "upcoming": "Upcoming Japanese releases",
        "movers": "Japanese booster box prices", "hot": "Most expensive cards in Japan right now", "more": "See all",
        "ebay": "eBay", "amazon": "Amazon", "find": "Find it", "updated": "Updated", "unreleased": "Coming soon",
        "src": "Prices are the latest sale prices of sealed boxes on SNKRDUNK, a major Japanese marketplace. USD values use the rate of ¥{fx} = $1 and are approximate.",
        "names": "English set names in brackets are unofficial translations unless an official English name exists.",
        "aff": "This site contains affiliate links (Amazon Associates, eBay Partner Network). We may earn a commission at no extra cost to you.",
        "jp_site": "Japanese version", "rel_lead": "Release dates and MSRP of upcoming and recent Japanese Pokémon TCG and ONE PIECE Card Game products, from the official Japanese websites.",
        "box_lead": "How much Japanese sealed booster boxes are selling for in Japan right now, compared with the official retail price (MSRP).",
        "card_lead": "The highest recent sale prices of single cards in Japan (ungraded, SNKRDUNK).",
        "home_lead": "Japan gets new Pokémon TCG and ONE PIECE Card Game sets first. Track Japanese release dates and what boxes and cards actually sell for in Japan — updated every day.",
        "faq": "FAQ",
    },
    "zh-tw": {
        "site": "日本卡牌導航", "tag": "日本寶可夢卡牌・航海王卡牌的發售日與日本市場行情",
        "home": "首頁", "releases": "日版發售日曆", "box": "日版補充包整盒行情", "cards": "日本高價卡排行",
        "buy": "在日本購買寶可夢卡的方法", "pokemon": "寶可夢卡牌（日版）", "onepiece": "航海王卡牌（日版）",
        "release": "發售日", "msrp": "建議售價", "price": "日本市場價", "usd": "約", "x": "相對建議售價", "chg": "30天漲跌",
        "us": "美國行情（TCGplayer）", "set": "系列", "card": "卡片", "no": "編號", "upcoming": "即將發售的日版商品",
        "movers": "日版整盒行情", "hot": "目前日本最高價的卡片", "more": "查看全部",
        "ebay": "eBay", "amazon": "Amazon", "find": "購買", "updated": "更新", "unreleased": "即將發售",
        "src": "價格為日本大型交易平台 SNKRDUNK 上未拆封整盒的最新成交價。美元換算以 ¥{fx} = $1 計算，僅供參考。",
        "names": "系列名稱的英文為非官方翻譯（有官方英文名稱者除外）。",
        "aff": "本站含有聯盟行銷連結（Amazon Associates、eBay Partner Network），我們可能會因此獲得佣金，您不需支付額外費用。",
        "jp_site": "日文版", "rel_lead": "根據日本官方網站整理的日版寶可夢卡牌・航海王卡牌新商品發售日與建議售價。",
        "box_lead": "日版未拆封整盒目前在日本的實際成交價，以及與建議售價的比較。",
        "card_lead": "日本近期單卡最高成交價（未鑑定・SNKRDUNK）。",
        "home_lead": "寶可夢卡牌與航海王卡牌的新系列都在日本最先發售。每天更新日版發售日，以及整盒與單卡在日本的實際成交行情。",
        "faq": "常見問題",
    },
    "ko": {
        "site": "재팬 TCG 내비", "tag": "일본판 포켓몬 카드・원피스 카드 게임의 발매일과 일본 시세",
        "home": "홈", "releases": "일본판 발매 캘린더", "box": "일본판 부스터 박스 시세", "cards": "일본 고가 카드 순위",
        "buy": "일본에서 포켓몬 카드 사는 방법", "pokemon": "포켓몬 카드 게임 (일본판)", "onepiece": "원피스 카드 게임 (일본판)",
        "release": "발매일", "msrp": "정가", "price": "일본 시세", "usd": "약", "x": "정가 대비", "chg": "30일 변동",
        "us": "미국 시세 (TCGplayer)", "set": "세트", "card": "카드", "no": "번호", "upcoming": "곧 발매되는 일본판 상품",
        "movers": "일본판 박스 시세", "hot": "지금 일본에서 가장 비싼 카드", "more": "전체 보기",
        "ebay": "eBay", "amazon": "Amazon", "find": "구매", "updated": "업데이트", "unreleased": "발매 예정",
        "src": "가격은 일본 대형 거래 플랫폼 SNKRDUNK의 미개봉 박스 최근 거래가입니다. 달러 환산은 ¥{fx} = $1 기준이며 참고용입니다.",
        "names": "세트 이름의 영어 표기는 공식 영어 이름이 없는 경우 비공식 번역입니다.",
        "aff": "이 사이트에는 제휴 링크(Amazon Associates, eBay Partner Network)가 포함되어 있으며, 추가 비용 없이 수수료를 받을 수 있습니다.",
        "jp_site": "일본어판", "rel_lead": "일본 공식 사이트 정보를 바탕으로 정리한 일본판 포켓몬 카드・원피스 카드 게임 신상품 발매일과 정가입니다.",
        "box_lead": "일본판 미개봉 부스터 박스가 지금 일본에서 실제로 거래되는 가격과 정가 비교입니다.",
        "card_lead": "최근 일본에서 거래된 싱글 카드 최고가입니다 (미감정・SNKRDUNK).",
        "home_lead": "포켓몬 카드와 원피스 카드 게임의 신규 세트는 일본에서 가장 먼저 발매됩니다. 일본판 발매일과 박스・카드의 실제 일본 시세를 매일 업데이트합니다.",
        "faq": "자주 묻는 질문",
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
}

BUY = {  # 日本での買い方ガイド（固定の文章）
    "en": [
        ("Pokémon Center stores", "The official Pokémon Center stores (Tokyo, Osaka, Kyoto and more) sell new sets on release day, but popular sets often sell out within hours or are limited to lottery sales for Japanese residents. Check the store's official X account the day before."),
        ("Card shops in Akihabara, Nipponbashi and Nakano", "Specialist card shops sell singles and sealed boxes, usually above MSRP for popular sets. Compare prices between shops — the market price table on this site shows what boxes typically sell for in Japan."),
        ("Electronics stores and bookstores", "Yodobashi, Bic Camera, Yamada and bookstores like TSUTAYA sell new sets, but in-demand products are mostly sold by lottery to members with a Japanese address and phone number, so they are hard to buy as a tourist."),
        ("Bring your passport and check limits", "Many shops limit purchases to a few packs or one box per person and some ask for ID. Tax-free shopping may be available in large stores if you show your passport."),
        ("Watch out for resealed boxes", "Only buy sealed boxes from reputable shops. Japanese boxes have shrink wrap with the official logo; avoid boxes with loose or unbranded wrap."),
        ("Buying from overseas", "If you can't visit Japan, Japanese sealed boxes are widely sold on eBay and Amazon by importers. Use the prices on this site to judge whether an import price is fair."),
    ],
    "zh-tw": [
        ("寶可夢中心", "官方的寶可夢中心（東京、大阪、京都等）會在發售日販售新系列，但熱門系列常在幾小時內售完，或只以抽選方式販售給日本居民。建議前一天先確認各店的官方 X 帳號。"),
        ("秋葉原・日本橋・中野的卡牌專賣店", "專賣店有販售單卡與未拆封整盒，熱門系列通常高於建議售價。可以多比較幾家店，本站的行情表可以參考日本的實際成交價。"),
        ("家電量販店與書店", "Yodobashi、Bic Camera、Yamada 以及 TSUTAYA 等書店也有販售新系列，但熱門商品大多以抽選方式賣給有日本地址與電話的會員，觀光客較難買到。"),
        ("攜帶護照並注意限購", "許多店家每人限購數包或一盒，部分會要求出示證件。大型商店出示護照可能可以免稅購買。"),
        ("小心重新封膜的整盒", "請在可信賴的店家購買未拆封整盒。日版整盒的收縮膜上有官方標誌，封膜鬆弛或沒有標誌的請避免購買。"),
        ("從海外購買", "無法到日本時，eBay 與 Amazon 上也有許多代購賣家販售日版整盒。可以用本站的行情判斷價格是否合理。"),
    ],
    "ko": [
        ("포켓몬 센터", "공식 포켓몬 센터(도쿄, 오사카, 교토 등)에서 발매일에 신규 세트를 판매하지만, 인기 세트는 몇 시간 만에 품절되거나 일본 거주자 대상 추첨 판매만 하는 경우가 많습니다. 전날 각 매장의 공식 X 계정을 확인하세요."),
        ("아키하바라・닛폰바시・나카노의 카드 전문점", "전문점에서는 싱글 카드와 미개봉 박스를 판매하며, 인기 세트는 보통 정가보다 비쌉니다. 여러 매장을 비교해 보세요. 이 사이트의 시세표로 일본의 실제 거래가를 확인할 수 있습니다."),
        ("가전 양판점과 서점", "요도바시, 빅카메라, 야마다, TSUTAYA 같은 서점에서도 신규 세트를 판매하지만, 인기 상품은 대부분 일본 주소와 전화번호가 있는 회원 대상 추첨 판매라 관광객이 사기는 어렵습니다."),
        ("여권 지참과 구매 제한 확인", "많은 매장이 1인당 몇 팩 또는 1박스로 구매를 제한하며, 신분증을 요구하기도 합니다. 대형 매장에서는 여권을 제시하면 면세가 가능한 경우가 있습니다."),
        ("재포장 박스 주의", "미개봉 박스는 신뢰할 수 있는 매장에서만 구매하세요. 일본판 박스의 수축 포장에는 공식 로고가 있으며, 포장이 헐겁거나 로고가 없는 박스는 피하세요."),
        ("해외에서 구매하기", "일본에 갈 수 없다면 eBay와 Amazon에서 수입 판매자가 일본판 박스를 판매합니다. 이 사이트의 시세로 가격이 적당한지 판단해 보세요."),
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
main{padding:20px 0 40px}h1{font-size:26px;line-height:1.3;margin:6px 0 8px}h2{font-size:19px;margin:28px 0 10px;border-left:4px solid var(--acc);padding-left:10px}
.lead{color:var(--ink2);margin:0 0 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--ink2);background:var(--bg)}
td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.jp{display:block;font-size:12px;color:var(--ink2)}
.up{color:var(--up);font-weight:700}.dn{color:var(--dn);font-weight:700}.buy a{display:inline-block;font-size:12px;font-weight:700;margin:2px 4px 2px 0;padding:3px 8px;border-radius:6px;text-decoration:none}
.b-eb{background:#0064d2;color:#fff}.b-az{background:#ffd814;color:#111}.tw{overflow-x:auto}.note{font-size:12px;color:var(--ink2)}
.rel{display:flex;gap:12px;align-items:baseline;border-bottom:1px solid var(--line);padding:10px 0}.rel time{font-weight:800;min-width:96px}.rel .g{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--bg);color:var(--ink2);margin-right:6px}
.soon{font-size:11px;font-weight:700;color:#fff;background:var(--acc);border-radius:4px;padding:1px 6px;margin-left:6px}
footer{border-top:1px solid var(--line);padding:20px 0 40px;font-size:12px;color:var(--ink2)}
@media (max-width:600px){.hide-s{display:none}h1{font-size:22px}}"""


def _last(d):
    """{"日付": 値} の最新の値と日付"""
    if not d:
        return None, None
    k = max(d)
    return d[k], k


def _ago(d, days):
    """days日前（それ以前で一番近い日）の値"""
    if not d:
        return None
    k = max(d)
    lim = (_dt.date.fromisoformat(k) - _dt.timedelta(days=days)).isoformat()
    ks = [x for x in d if x <= lim]
    return d[max(ks)] if ks else None


def set_name(g, x):
    return SET_EN.get(g, {}).get(x) or x


def card_name(label):
    s = label
    for k in sorted(CARD_EN, key=len, reverse=True):
        s = s.replace(k, CARD_EN[k])
    s = re.sub(r"\s*:\s*", " · ", s).strip()
    s = re.sub(r"([a-z])(VMAX|VSTAR|GX|EX|V)\b", r"\1 \2", s)  # RayquazaVMAX → Rayquaza VMAX
    return s if not re.search(r"[぀-ヿ]", s) else ""  # 訳しきれない時は空（日本語の名前だけ出す）


def build_intl(out, s, souba_raw, card_raw, info, site, today):
    """海外向けページを書き出して、サイトマップ用の [(URL, 日付)] を返す"""
    fx = souba_raw.get("fx") or 150
    items = souba_raw.get("items") or {}
    az_tag = (s.get("intl_amazon_tag") or "").strip()
    ebay = (s.get("ebay_campid") or "").strip()
    urls = []

    def ebay_url(q):
        u = f"https://www.ebay.com/sch/i.html?_nkw={quote(q)}"
        if ebay:
            u += f"&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={quote(ebay)}&toolid=10001&mkevt=1"
        return u

    def amz_url(q):
        return f"https://www.amazon.com/s?k={quote(q)}" + (f"&tag={quote(az_tag)}" if az_tag else "")

    def buy_btns(g, x, t):
        q = f"Japanese {'Pokemon' if g == 'pokemon' else 'One Piece'} {set_name(g, x)} booster box"
        rel = 'target="_blank" rel="nofollow sponsored noopener"'
        return (f'<span class="buy"><a class="b-eb" href="{escape(ebay_url(q))}" {rel}>{t["ebay"]}</a>'
                f'<a class="b-az" href="{escape(amz_url(q))}" {rel}>{t["amazon"]}</a></span>')

    # 弾ごとの相場
    rows = []
    for k, v in items.items():
        g, x = k.split("|", 1)
        p, day = _last(v.get("jp") or {})
        if not p:
            continue
        old = _ago(v.get("jp") or {}, 30)
        us, _ = _last(v.get("us") or {})
        rel = str(((info.get(g) or {}).get(x) or {}).get("release") or "")
        rows.append({"g": g, "x": x, "p": p, "day": day, "teika": v.get("teika"), "old": old, "us": us, "rel": rel})
    rows.sort(key=lambda r: (r["rel"] or "0000"), reverse=True)

    # 高額カード
    cards = []
    for v in (card_raw or {}).values():
        p, day = _last(v.get("jp") or {})
        if p:
            g, x = (v.get("key") or "|").split("|", 1)
            cards.append({"g": g, "x": x, "label": v.get("label") or "", "num": v.get("num") or "", "p": p})
    cards.sort(key=lambda c: -c["p"])

    # 発売日
    d0 = (today - _dt.timedelta(days=75)).isoformat()
    rels = []
    for g in ("pokemon", "onepiece"):
        for x, inf in (info.get(g) or {}).items():
            r = str(inf.get("release") or "")
            if r >= d0:
                rels.append((r, g, x, inf))
    rels.sort()
    tdy = today.isoformat()

    def usd(yen):
        return f"${yen / fx:,.0f}"

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
            mult = f'×{r["p"] / r["teika"]:.1f}' if r.get("teika") else "–"
            us = f'<span class="jp">{t["us"]}: ${r["us"]:,.0f}</span>' if (r["us"] and game == "pokemon") else ""
            en_ = set_name(game, r["x"])
            sub_ = " · ".join(([r["x"]] if r["x"] not in en_ else []) + ([f'{t["release"]} {r["rel"]}'] if r["rel"] else []))
            h.append(f'<tr><td><b>{escape(en_)}</b><span class="jp">{escape(sub_)}</span>{buy_btns(game, r["x"], t)}</td>'
                     f'<td class="n"><b>¥{r["p"]:,}</b><span class="jp">{t["usd"]} {usd(r["p"])}</span>{us}</td>'
                     f'<td class="n hide-s">' + (f'¥{r["teika"]:,}' if r.get("teika") else "–") + f'</td><td class="n">{mult}</td>'
                     f'<td class="n hide-s">{chg(r)}</td></tr>')
        h.append("</table></div>")
        return "".join(h)

    def card_table(L, t, limit):
        h = [f'<div class="tw"><table><tr><th>{t["card"]}</th><th class="hide-s">{t["set"]}</th><th class="n">{t["price"]}</th></tr>']
        for c in cards[:limit]:
            en = card_name(c["label"])
            h.append(f'<tr><td><b>{escape(en or c["label"])}</b><span class="jp">{escape(c["num"])}'
                     + (f' · {escape(c["label"])}' if en else "") + f'</span></td>'
                     f'<td class="hide-s">{escape(set_name(c["g"], c["x"]))}</td>'
                     f'<td class="n"><b>¥{c["p"]:,}</b><span class="jp">{t["usd"]} {usd(c["p"])}</span></td></tr>')
        h.append("</table></div>")
        return "".join(h)

    def rel_list(L, t, only_future=False, limit=None):
        rs = [r for r in rels if (r[0] > tdy if only_future else True)][:limit]
        h = []
        for r, g, x, inf in rs:
            ty = TYPE_T.get(re.sub(r"【.*?】", "", inf.get("type") or ""), {}).get(L) or re.sub(r"[^A-Za-z0-9\-【】 ]", "", inf.get("type") or "").strip("【】 ")
            code = re.search(r"【(.+?)】", inf.get("type") or "")
            yen = re.findall(r"([\d,]+)円", inf.get("price") or "")
            pr = f' · {t["msrp"]} ¥{yen[-1]}' if yen else ""
            h.append(f'<div class="rel"><time datetime="{r}">{r}</time><div><span class="g">{"Pokémon" if g == "pokemon" else "ONE PIECE"}</span>'
                     f'<b>{escape(set_name(g, x))}</b>' + (f'<span class="soon">{t["unreleased"]}</span>' if r > tdy else "")
                     + f'<span class="jp">' + (escape(x) if x not in set_name(g, x) else "") + (f' · {escape(code.group(1))}' if code and code.group(1) not in set_name(g, x) else "")
                     + (f' · {escape(ty)}' if ty else "") + pr + '</span></div></div>')
        return "".join(h)

    for L, meta in LANGS.items():
        t = T[L]
        foot_note = f'<p>{t["src"].format(fx=round(fx, 1))}</p><p>{t["names"]}</p><p>{t["aff"]}</p>'
        for path, key in PAGES:
            if key == "home":
                title = f'{t["site"]} — {t["tag"]}'
                h1, lead = t["tag"], t["home_lead"]
                body = (f'<h2>{t["upcoming"]}</h2><div class="card">{rel_list(L, t, True, 6) or "–"}</div>'
                        f'<p><a href="/{L}/releases/">{t["more"]} →</a></p>'
                        f'<h2>{t["movers"]} · {t["pokemon"]}</h2>{price_table(L, t, "pokemon", 8)}'
                        f'<h2>{t["movers"]} · {t["onepiece"]}</h2>{price_table(L, t, "onepiece", 6)}'
                        f'<p><a href="/{L}/box-prices/">{t["more"]} →</a></p>'
                        f'<h2>{t["hot"]}</h2>{card_table(L, t, 10)}<p><a href="/{L}/card-prices/">{t["more"]} →</a></p>')
            elif key == "releases":
                title, h1, lead = f'{t["releases"]} {today.year} | {t["site"]}', t["releases"], t["rel_lead"]
                body = f'<div class="card">{rel_list(L, t)}</div>'
            elif key == "box":
                title, h1, lead = f'{t["box"]} ({today.year}) | {t["site"]}', t["box"], t["box_lead"]
                body = f'<h2>{t["pokemon"]}</h2>{price_table(L, t, "pokemon")}<h2>{t["onepiece"]}</h2>{price_table(L, t, "onepiece")}'
            elif key == "cards":
                title, h1, lead = f'{t["cards"]} | {t["site"]}', t["cards"], t["card_lead"]
                body = card_table(L, t, 60)
            else:
                title, h1, lead = f'{t["buy"]} | {t["site"]}', t["buy"], ""
                body = "".join(f'<div class="card"><h2 style="margin-top:0">{escape(a)}</h2><p>{escape(b)}</p></div>' for a, b in BUY[L])
                body += f'<p><a href="/{L}/box-prices/">{t["box"]} →</a></p>'
            alt = "".join(f'<link rel="alternate" hreflang="{LANGS[l]["html"]}" href="{site}/{l}/{path}">' for l in LANGS)
            alt += f'<link rel="alternate" hreflang="x-default" href="{site}/en/{path}">'
            tabs = "".join(f'<a href="/{L}/{p}"{" aria-current=\"page\"" if p == path else ""}>{t[k]}</a>' for p, k in PAGES)
            langs = "".join(f'<a href="/{l}/{path}"{" aria-current=\"true\"" if l == L else ""}>{m["name"]}</a>' for l, m in LANGS.items())
            html = (f'<!doctype html><html lang="{meta["html"]}"><head><meta charset="utf-8">'
                    f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>'
                    f'<meta name="description" content="{escape(lead or t["tag"])}"><link rel="canonical" href="{site}/{L}/{path}">{alt}'
                    f'<style>{CSS}</style></head><body><header><div class="w"><div class="top"><a class="logo" href="/{L}/">{t["site"]}</a>'
                    f'<div class="lang">{langs}<a href="/">日本語</a></div></div><nav class="tabs">{tabs}</nav></div></header>'
                    f'<main class="w"><h1>{escape(h1)}</h1>' + (f'<p class="lead">{escape(lead)}</p>' if lead else "")
                    + f'<p class="note">{t["updated"]}: {today.isoformat()}</p>{body}</main>'
                    f'<footer><div class="w">{foot_note}<p>© Japan TCG Navi (tcg-chusen.com)</p></div></footer></body></html>')
            p = Path(out) / L / path / "index.html"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf-8")
            urls.append((f"{site}/{L}/{path}", today.isoformat()))
    return urls
