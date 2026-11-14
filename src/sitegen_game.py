"""ゲーム・ホビー入荷速報（game-nyuka.com）のサイト書き出し → site_game/

ページ：
  /                         すべて（受付中／予告／結果待ち／再入荷・先着／発売・再販／終了 のタブ。絞り込みはブラウザで）
  /now/                     お店 × 商品の「いま」の表（ブラウザで計算）
  /<カテゴリ>/               カテゴリごと（/ps5/ など。config/game/categories.yaml から）
  /<カテゴリ>/<モデル>/       機種・モデルごと（/ps5/ps5-pro/ など）
  /chain/<お店>/<カテゴリ>/   お店 × カテゴリ
  /l/<id>/                  1件ずつの個別ページ（detail.render を使う）
  /today/                   今日締切・今日開始
  /calendar/                予約開始・発売日・再販日のカレンダー
  /guide/ /guide/<slug>/    解説（config/game/guides.yaml）
  /x-draft.html             Xの下書き（noindex）
  sitemap.xml robots.txt 404.html privacy.html llms.txt
受付状況（受付中・締切まで・終了）は全部ブラウザのJSが「今」の時刻で計算する。
"""
import json
import os
import re
from html import escape
from pathlib import Path

from common import ROOT, load_json, save_json, now, parse_dt, sha, normalize, log
import detail
import game_affi
import gamecats
import sitegen as sg

TEMPLATE = Path(__file__).with_name("game_template.html")
SHELL_CSS = Path(__file__).with_name("game_shell.css")  # 全ページ共通（色・文字・左のメニュー）
BG = "#0b0d12"  # 画面の地の色（ブラウザの上のバーの色にも使う）
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@500;700;900&family=Chakra+Petch:wght@600;700&display=swap">')
# 左のメニューの「受付状況」（一覧のあるページでは押すとその場で切り替わる）
STAT_NAV = (("open", "受付中"), ("upcoming", "予告"), ("waiting", "結果待ち"), ("restock", "再入荷・先着"), ("announced", "発売・再販"))
BELL_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
            '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>')
ACTIVE = ("approved", "posted", "listed")
VERIFY_FROM = "2026-11-10T12:00"   # この時刻より後に見つけたものは、元の記事で確かめてから出す（11/10 精度上げて）



def _notice_html(text):
    """カテゴリの注意書き（例：お酒は20歳になってから）。無ければ空"""
    if not text:
        return ""
    return ('<p class="cat-notice" style="margin:8px 0;padding:8px 12px;border:1px solid #e0b4b4;background:#fff5f5;'
            f'color:#7a1f1f;border-radius:8px;font-size:13px">🔞 {escape(text)}</p>')

def shown_ok(i):
    if i.get("verified") is False:
        return False
    if i.get("verified") is None and not i.get("manual") and (i.get("found_at") or "") > VERIFY_FROM:
        return False
    return True
# 終了したものも「終了」タブと結果待ちのために少しのあいだ残す
KEEP_ENDED_DAYS = 7
FIELDS = ("key", "game", "store", "product", "series", "start", "end", "announce", "buy", "conditions", "tags", "url",
          "channel", "area", "found_at", "id_check", "member", "method", "kind", "price", "round", "manual", "products")

# ゲーム・ホビー向けのお店（チェーン）。トレカ側の CHAINS を変えずに、こちらだけで持つ
GAME_CHAINS = [
    ("sonystore", "ソニーストア", r"ソニーストア|Sony ?Store", True),
    ("mynintendostore", "マイニンテンドーストア", r"マイニンテンドーストア|My ?Nintendo ?Store|任天堂", True),
    ("amazon", "Amazon", r"Amazon|アマゾン", True),
    ("rakutenbooks", "楽天ブックス", r"楽天ブックス|楽天", True),
    ("yodobashi", "ヨドバシカメラ", r"ヨドバシ", True),
    ("biccamera", "ビックカメラ", r"ビックカメラ|BicCamera|コジマ|ソフマップ|Sofmap", True),
    ("joshin", "ジョーシン", r"ジョーシン|Joshin", True),
    ("yamada", "ヤマダデンキ", r"ヤマダ(電機|デンキ)|YAMADA|LABI", True),
    ("edion", "エディオン", r"エディオン|EDION", True),
    ("ksdenki", "ケーズデンキ", r"ケーズデンキ", False),
    ("nojima", "ノジマ", r"ノジマ", False),
    ("geo", "ゲオ", r"ゲオ|\bGEO\b", True),
    ("tsutaya", "TSUTAYA", r"TSUTAYA|ツタヤ|蔦屋", False),
    ("toysrus", "トイザらス", r"トイザらス|Toys\s*R\s*Us", True),
    ("aeon", "イオン", r"イオン|AEON", False),
    ("furuichi", "古本市場・ふるいち", r"古本市場|ふるいち", False),
    ("sevennet", "セブンネット", r"セブンネット|セブン-?イレブン", False),
    ("pbandai", "プレミアムバンダイ", r"プレミアムバンダイ|プレバン|p-bandai|魂ウェブ", True),
    ("gundambase", "ガンダムベース", r"ガンダムベース|GUNDAM ?BASE", False),
    ("amiami", "あみあみ", r"あみあみ|amiami", False),
    ("surugaya", "駿河屋", r"駿河屋", False),
    ("pokemoncenter", "ポケモンセンター", r"ポケモンセンター", True),
    ("takaratomymall", "タカラトミーモール", r"タカラトミーモール|タカラトミー", False),
    ("ichibankuji", "一番くじONLINE", r"一番くじ ?ONLINE|一番くじオンライン", False),
    ("steam", "Steam（Valve）", r"\bSteam\b|Valve", False),
]


def chain_of(store):
    for slug, name, pat, big in GAME_CHAINS:
        if re.search(pat, store or "", re.I):
            return slug
    return None


CHAIN = {c[0]: c for c in GAME_CHAINS}
WEEK = "月火水木金土日"


# いちばん上の「商品名・JANコードで検索」（どのページにも出す。/search/ で探す）
SEARCH_FORM = ('<form class="qsearch" action="/search/" method="get" role="search">'
               '<input type="search" name="q" placeholder="商品名・JANコードで検索" aria-label="商品名・JANコードで検索" enterkeyhint="search">'
               '<button type="submit">検索</button></form>'
               '<style>.qsearch{display:flex;gap:8px;margin:0 0 14px}.qsearch input{flex:1;min-width:0;padding:11px 14px;border-radius:8px;border:1px solid #3a4152;'
               'background:#0f121a;color:#e9edf5;font-size:16px}.qsearch button{padding:11px 18px;border-radius:8px;border:0;background:#ffd23f;color:#0b0d12;'
               'font-weight:900;font-size:15px;cursor:pointer}</style>')

PCOUNTS = {}   # カテゴリごとの商品の数（build の最初に入れる。左メニューの数）


def side_html(cats, cur_game=None, cur=None, counts=True):
    """左のメニュー：いちばん上にカテゴリ（横に商品の数）→ 定価以上で売れる・買取相場・カレンダー → 下に抽選・受付の状況。スマホでは本文の上に横並び"""
    here = ' aria-current="page"'
    cats = sorted(cats, key=lambda c: -PCOUNTS.get(c["id"], 0))   # 商品の多いカテゴリから（11/9 ユーザーの指示）
    cl = "".join(f'<a href="/{escape(c["slug"])}/"{here if cur_game == c["id"] else ""}>{escape(c["short"])}'
                 + (f'<span class="n">{PCOUNTS[c["id"]]}</span>' if PCOUNTS.get(c["id"]) else "") + "</a>" for c in cats)
    pages = (f'<a href="/premium/"{here if cur == "premium" else ""}>プレミア商品一覧</a>'
             f'<a href="/souba/"{here if cur == "souba" else ""}>買取相場</a>'
             f'<a href="/calendar/"{here if cur == "calendar" else ""}>発売カレンダー</a>'
             f'<a href="/new/"{here if cur == "new" else ""}>発売予定・予約</a>')
    stat = "".join(f'<a href="/chusen/#{k}" data-t="{k}">{n}<span class="n" data-n="{k}"></span></a>' for k, n in STAT_NAV)
    return ('<aside class="side" aria-label="メニュー">'
            '<a class="brand" href="/"><img src="/rinrin.png" alt="" width="36" height="36"><span>ゲーム・ホビー<br><em>入荷速報</em></span></a>'
            f'<nav class="cats" aria-label="カテゴリ"><p class="cats-h">カテゴリ（商品数）</p>{cl}</nav>'
            f'<nav class="stat" aria-label="ページ">{pages}</nav>'
            f'<nav class="stat stat-sub" aria-label="抽選・受付の状況"><p class="cats-h">抽選・受付</p>{stat}</nav>'
            f'<a class="notify" href="https://x.com/a9994aaa" target="_blank" rel="noopener"><span>{BELL_SVG}Xで発売の通知を受け取る</span><small>販売開始・再販をすぐお知らせ</small></a>'
            '</aside>')


_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06]\uFE0F?[ ]?")  # 絵文字のアイコンは使わない


def _theme_detail(html, side):
    """個別ページ（detail.render の出力。トレカと共通の部品）を、このサイトの見た目にそろえる。
    detail.py 自体は変えない（トレカ抽選ナビのページは今までどおり）"""
    css = SHELL_CSS.read_text(encoding="utf-8") + DETAIL_CSS
    # トレカ側の文字（IBM Plex）の読み込みは外す。読み込み方が「preload＋noscript」でも「stylesheet」でも外れるように
    html = re.sub(r'<link rel="preload" as="style" href="https://fonts\.googleapis\.com/css2\?family=Zen\+Kaku[^"]*"[^>]*>(<noscript>.*?</noscript>)?', lambda m: "", html, count=1, flags=re.S)
    html = re.sub(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/css2\?family=Zen\+Kaku[^"]*">', lambda m: "", html, count=1)
    html = html.replace('<link rel="preconnect" href="https://fonts.googleapis.com">', FONTS, 1)
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    html = re.sub(r"<body><header>.*?</header><main class=\"wrap\">",
                  lambda m: f'<body><div class="shell">{side}<div class="main"><p class="promo">本ページはプロモーションを含みます</p>{SEARCH_FORM}<main class="wrap">', html, count=1, flags=re.S)
    html = html.replace("</main><script>", "</main></div></div><script>", 1)
    head, body = html.split("<body>", 1)
    return head + "<body>" + _EMOJI.sub("", body)


# 個別ページ用：detail.CSS の色を暗い色に置きかえる（:root:not(#_) で detail のダークモード指定より強くする）
DETAIL_CSS = """
:root:not(#_){--paper:#0b0d12;--card:#141823;--ink:#e9edf5;--ink-2:#a3abbd;--rule:#262c3a;--red:#ffd23f;--red-soft:#1d1b10;
 --amber:#ff8a95;--amber-soft:#2a1519;--done:#5ee0ff;--done-soft:#0f2630;--navy-soft:#1c2130;
 --font-body:"Zen Kaku Gothic New","Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;
 --font-num:"Chakra Petch","Zen Kaku Gothic New",ui-monospace,monospace;color-scheme:dark}
.main>.wrap{max-width:760px;margin:0}
.crumbs a{color:var(--ink-2)}
.tk,.more{border-radius:16px}
h1{font-weight:900}
.chip{background:#1c2130;color:var(--ink-2)}
.chip.st{background:var(--y);color:var(--y-ink)}.chip.st.soon{background:var(--pink);color:var(--y-ink)}
.chip.st.pre{background:var(--cyan);color:var(--y-ink)}.chip.st.end{background:#262c3a;color:var(--ink-2)}
.cd b{font-family:var(--num);font-weight:700;color:var(--y)}.cd.soon b{color:var(--pink)}.cd.pre b{color:var(--cyan)}
.go,.nextgo{background:var(--y);color:var(--y-ink);font-weight:900}.go:hover,.nextgo:hover{background:var(--y-2);color:var(--y-ink)}
.go.off{background:#262c3a;color:var(--ink-2)}
.more a,.sub-acts a,.calbtns a{color:var(--ink)}.more a:hover{color:var(--y)}
.calbox .calsub-l{color:var(--y)}
.ad.lose{background:#1a1710;border-color:#4a3d1c}.lose-l li{border-top-color:#3a3020}
.followbox{background:#1c2130}
footer a{color:var(--ink-2)}
.shopb{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.shopb .btn{flex:1 1 160px;display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 16px;border-radius:8px;font-weight:900;font-size:15px;text-decoration:none}
.btn-rk{background:#bf0000;color:#fff}.btn-rk:hover{background:#d61a1a;color:#fff}
.btn-az{background:#ff9900;color:#0b0d12}.btn-az:hover{background:#ffad33;color:#0b0d12}
.btn-yh{background:#ff0033;color:#fff}.btn-yh:hover{background:#ff3355;color:#fff}.btn-mc{background:#fff;color:#ea352d;border:1px solid #ea352d}.btn-mc:hover{background:#ffecea;color:#ea352d}
.credit{display:block;margin-top:6px}
"""


CREDIT = '<p>商品の写真は楽天ブックス（楽天市場）の商品の写真です。写真・「楽天で見る」「Amazonで見る」のリンクは広告（PR）です。</p>'
SHOP_REL = "nofollow sponsored noopener"


def shop_buttons(rk, az, name="", yh="", mc=""):
    """「楽天で見る」「Amazonで見る」（その商品そのもののページ）・Yahoo!ショッピング・メルカリ（商品名で探すページ）"""
    who = f'<span class="sr">：{escape(name)}</span>' if name else ""
    return ((f'<a class="btn btn-rk" href="{escape(rk["u"])}" target="_blank" rel="{SHOP_REL}">楽天で見る{who}</a>' if (rk or {}).get("u") else "")
            + (f'<a class="btn btn-az" href="{escape(az)}" target="_blank" rel="{SHOP_REL}">Amazonで見る{who}</a>' if az else "")
            + (f'<a class="btn btn-yh" href="{escape(yh)}" target="_blank" rel="{SHOP_REL}">Yahoo!で見る{who}</a>' if yh else "")
            + (f'<a class="btn btn-mc" href="{escape(mc)}" target="_blank" rel="nofollow noopener">メルカリで探す{who}</a>' if mc else ""))


AV_LABEL = {"pre": "予約受付中", "buy": "販売中", "invite": "招待リクエスト受付中"}


def avail_of(row, status):
    """楽天・Amazonのいまの状態（見張り worker/game-watch が見たもの）→ [{"shop","s","u","p"}]（予約受付中・販売中だけ）"""
    from urllib.parse import unquote
    out = []
    m = re.search(r"/dp/([A-Z0-9]{10})", row.get("az") or "")
    if m and (status.get(m.group(1)) or {}).get("s") in AV_LABEL:
        x = status[m.group(1)]
        out.append({"shop": "Amazon", "s": x["s"], "u": x.get("u") or row["az"], "p": x.get("p") or 0})
    u = unquote((row.get("rk") or {}).get("u") or "")
    m = re.search(r"item\.rakuten\.co\.jp/([^/]+)/([^/?#&]+)", u)
    if m and (status.get(f"{m.group(1)}:{m.group(2)}") or {}).get("s") in AV_LABEL:
        x = status[f"{m.group(1)}:{m.group(2)}"]
        out.append({"shop": "楽天ブックス", "s": x["s"], "u": row["rk"]["u"], "p": x.get("p") or 0})
    return out


def avail_html(av, name=""):
    """「🛒 いまAmazonで予約受付中（63,980円）［予約する］」の枠"""
    if not av:
        return ""
    rows = "".join(
        f'<a class="av-go" href="{escape(a["u"])}" target="_blank" rel="nofollow sponsored noopener"><b>{escape(a["shop"])}で{AV_LABEL[a["s"]]}</b>'
        f'{(" " + format(int(a["p"]), ",") + "円") if a.get("p") else ""}<span>{"予約する" if a["s"] == "pre" else "申し込む" if a["s"] == "invite" else "買う"} →</span></a>' for a in av)
    return f'<div class="av"><p>🛒 いま定価で買える・予約できるお店（PR）</p>{rows}</div>'


AV_CSS = (".av{background:#1d1a0b;border:2px solid #ffd23f;border-radius:12px;padding:12px 14px;margin:12px 0}.av p{margin:0 0 8px;font-weight:900;color:#ffd23f}"
          ".av-go{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;background:#ffd23f;color:#0b0d12;border-radius:8px;padding:10px 14px;"
          "margin:6px 0;text-decoration:none;font-weight:700}.av-go span{font-weight:900}")


def _release_detail(html, snap):
    """発売日の情報（kind=release）は抽選ではないので、「締切」「応募」の言葉を「発売」に直す（detail.py はトレカと共通なので変えない）"""
    if snap.get("kind") != "release":
        return html
    for a, b in (('big="締切まであと"', 'big="発売まであと"'), ('"本日締切"', '"本日発売"'), ('"まもなく締切"', '"まもなく発売"'),
                 ('lab=same(E,N)?"本日発売":soon?"まもなく発売":"受付中"', 'lab=same(E,N)?"本日発売":soon?"まもなく発売":"発売前"'),
                 ("<dt>応募締切</dt>", "<dt>発売日</dt>"), ("<dt>応募期間</dt>", "<dt>発売日</dt>"),
                 ("<b>受付中</b>", "<b>発売前</b>"), ("この抽選の受付は終了しました", "発売されました"), ("受付は終了しました", "発売されました"),
                 ("応募ページを開く →", "公式の発表を見る →"), ("<b>締切をカレンダーに入れる</b>", "<b>発売日をカレンダーに入れる</b>"), ("応募先は店舗の告知でご確認ください", "発売の情報は公式の発表で確認してください")):
        html = html.replace(a, b)
    html = re.sub(r"締切 (\d{1,2}/\d{1,2}\([^)]\))(?: \d{1,2}:\d{2})?", r"発売日 \1", html)          # 説明文
    html = re.sub(r"(\d{1,2}/\d{1,2}\([^)]\))(?: \d{1,2}:\d{2})?締切", r"\1発売", html)          # タイトル
    html = html.replace("受付方法・条件・対象商品をまとめています", "発売日・定価・販売店をまとめています")
    html = re.sub(r'<div><dt>必要なもの</dt><dd>[^<]*</dd></div>', "", html)
    html = re.sub(r'<div><dt>受け取り</dt><dd>[^<]*</dd></div>', "", html)
    html = re.sub(r"(<dt>発売日</dt><dd>[^<]*?)\s*\d{1,2}:\d{2}(まで)?(</dd>)", r"\1\3", html)   # 発売日に時刻は出さない
    return html


KIND_JA = {"lottery": "抽選", "invite": "招待販売", "preorder": "予約", "restock": "再入荷", "first_come": "先着販売",
           "release": "発売", "fukubukuro": "福袋"}


def _nm_key(s):
    """同じ商品かどうかを見るための名前（かっこ・空白・記号を外す）"""
    s = re.sub(r"[（(【\[][^）)】\]]*[）)】\]]", "", s or "")
    return re.sub(r"[\s　・\-‐ー/／!！?？、。,.「」『』]", "", s).lower()[:40]


def _md_range(snap):
    from detail import fmt
    a, b = snap.get("start"), snap.get("end")
    if a and b:
        return f"{fmt(a)}〜{fmt(b)}"
    return f"〜{fmt(b)}" if b else (f"{fmt(a)}〜" if a else "日時未定")


def _price_sec(product, name, s):
    """この商品の買取相場と定価の欄（買取店の価格が分かるときだけ）→ (HTML, よくある質問)"""
    try:
        import game_premium
        x = game_premium.price_match(product, s)
    except Exception:
        return "", []
    if not x:
        return "", []
    faq = []
    ratio = f"（定価の{round(x['ratio'] * 100)}%）" if x.get("ratio") else ""
    top = "".join(f"<tr><td>{escape(st)}</td><td>{v:,}円</td></tr>" for st, v in (x.get("prices") or [])[:5])
    info = []
    if x.get("sales_date"):
        info.append(f"発売日：{escape(x['sales_date'])}")
    if x.get("maker"):
        info.append(f"メーカー：{escape(x['maker'])}")
    if x.get("teika"):
        info.append(f"定価：{x['teika']:,}円（税込）")
    info.append(f"JANコード：{escape(x['jan'])}")
    sec = (f'<section class="xsec"><h2>「{escape(name)}」の買取相場と定価</h2>'
                f'<p>買取店の新品の最高買取価格は<b>{x["max"]:,}円</b>（{escape(x["store"])}）{ratio}です。'
                f'{escape(game_premium.CHANGE_NOTE)}</p>'
                + (f'<div class="xtbl"><table><thead><tr><th>買取店</th><th>新品の買取価格</th></tr></thead><tbody>{top}</tbody></table></div>' if top else "")
                + f'<p class="note">{"・".join(info)}</p>'
                f'<p><a href="/premium/{escape(x["jan"])}/">買取価格の推移・お店ごとの比較を見る →</a></p></section>')
    faq.append((f"{name}の買取価格は？", f"買取店の新品の最高買取価格は{x['max']:,}円（{x['store']}）{ratio}です。{game_premium.CHANGE_NOTE}"))
    if x.get("teika"):
        faq.append((f"{name}の定価は？", f"{x['teika']:,}円（税込）です。"))
    return sec, faq


def _hubs_cfg():
    import yaml
    pth = ROOT / "config" / "game" / "models.yaml"
    y = (yaml.safe_load(pth.read_text(encoding="utf-8")) or {}) if pth.exists() else {}
    out = []
    for h in y.get("hubs") or []:
        try:
            h = dict(h, _m=re.compile(h["match"], re.I), _r=re.compile(h["require"], re.I) if h.get("require") else None,
                     _x=re.compile(h["exclude"], re.I) if h.get("exclude") else None)
        except (re.error, KeyError):
            continue
        h["path"] = h["path"].strip("/") + "/"
        out.append(h)
    return out


def _hub_hit(h, text):
    text = text or ""
    return bool(h["_m"].search(text) and (not h["_r"] or h["_r"].search(text)) and not (h["_x"] and h["_x"].search(text)))


_CAT_ALL = {}


def _hub_extra(h, pages, live_keys, s):
    """モデルの常設まとめに足す欄 → (HTML, よくある質問, 当てはまる商品の数, 記録の数)。
    当てはまる商品（買取相場のJAN）の最高買取・定価・楽天/Amazon、これまでの受付の記録（終わったものも）"""
    import game_premium
    if "x" not in _CAT_ALL:
        try:
            _CAT_ALL["x"] = game_premium.catalog(s, game_premium.watch_map_cached())
        except Exception:
            _CAT_ALL["x"] = []
    prods = [x for x in _CAT_ALL["x"] if _hub_hit(h, " ".join([x["name"]] + x.get("names", [])[:3]))]
    prods.sort(key=lambda x: -(x["max"] or 0))
    recs = [(rec.get("snap") or {}, rec) for k, rec in pages.items() if k not in live_keys
            and _hub_hit(h, f'{(rec.get("snap") or {}).get("product") or ""} {(rec.get("snap") or {}).get("series") or ""}')]
    recs.sort(key=lambda r: (r[0].get("end") or ""), reverse=True)
    secs, faq = [], []
    nm = h["name"]
    if prods:
        rows = "".join(
            f'<tr><td><a href="/premium/{escape(x["jan"])}/">{escape(x["name"])}</a></td><td>{x["max"]:,}円</td>'
            f'<td>{(game_premium.tword(x, True) + " " + format(x["teika"], ",") + "円") if x.get("teika") else "—"}</td>'
            f'<td>{"<a href=\"" + escape(x["itemUrl"]) + "\" rel=\"nofollow sponsored noopener\" target=\"_blank\">楽天</a>" if x.get("itemUrl") else ""}'
            f'{" " if x.get("itemUrl") and x.get("azUrl") else ""}{"<a href=\"" + escape(x["azUrl"]) + "\" rel=\"nofollow sponsored noopener\" target=\"_blank\">Amazon</a>" if x.get("azUrl") else ""}</td></tr>'
            for x in prods[:15])
        secs.append(f'<section class="xsec"><h2>{escape(nm)}の商品と買取相場（{len(prods)}件）</h2>'
                    '<p>買取店の新品の最高買取価格と、楽天ブックス・Amazonの商品ページです。販売が始まったら X（@a9994aaa）でお知らせします。'
                    f'{escape(game_premium.CHANGE_NOTE)}</p>'
                    f'<div class="xtbl"><table><thead><tr><th>商品</th><th>最高買取</th><th>定価・販売価格</th><th>販売ページ</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
        top = prods[0]
        faq.append((f"{nm}の買取価格は？", f"いちばん高いのは「{top['name']}」の{top['max']:,}円（{top['store']}）です。商品ごとの買取価格は上の表のとおりです。{game_premium.CHANGE_NOTE}"))
    if recs:
        rows = "".join(f'<tr><td>{escape(o.get("store") or "")}</td><td>{escape((o.get("series") or o.get("product") or "")[:40])}</td>'
                       f'<td>{escape(KIND_JA.get(o.get("kind") or "lottery", "受付"))}</td><td>{escape(_md_range(o))}</td></tr>' for o, rec in recs[:20])
        secs.append(f'<section class="xsec"><h2>{escape(nm)}のこれまでの抽選・予約・販売</h2>'
                    f'<p>受付が終わったものも含めて、このサイトで見つけた{escape(nm)}の受付の記録です（{len(recs)}件）。どのお店で、どんな種類の受付があったかの参考にしてください。</p>'
                    f'<div class="xtbl"><table><thead><tr><th>お店</th><th>商品</th><th>種類</th><th>期間</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
        stores = list(dict.fromkeys(o.get("store") for o, _ in recs if o.get("store")))
        faq.append((f"{nm}はこれまでどこで抽選・販売がありましたか？", "・".join(stores[:10]) + "などで受付がありました（受付が終わったものを含む）。"))
    faq.append((f"{nm}の再販・在庫の情報はどうやって知れますか？",
                "楽天ブックス・Amazonの販売状況を数分おきに確かめていて、販売が始まったら X（@a9994aaa）でお知らせします。新しい抽選・予約もこのページに載せます。"))
    css = ('<style>.xsec{margin:18px 0}.xsec h2{font-size:17px;margin:0 0 8px}.xsec p{font-size:14px;line-height:1.75}'
           '.xtbl{overflow-x:auto}.xtbl table{border-collapse:collapse;width:100%;font-size:13px}.xtbl th,.xtbl td{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left}</style>')
    return (css + "".join(secs)) if secs else "", faq, len(prods), len(recs)


def _series_extra(x, path, lst, pages, s):
    """商品ごとのまとめページ（/<ジャンル>/<商品>/）に足す欄 → (HTML, よくある質問)。
    これまでの受付の記録（終わったものも）・買取相場と定価・お店の数などデータから作る質問"""
    from detail import fmt
    secs, faq = [], []
    live_keys = {i.get("key") for i in lst}
    past = [(rec.get("snap") or {}, rec) for k, rec in pages.items() if (rec.get("snap") or {}).get("spath") == path and k not in live_keys]
    past.sort(key=lambda r: (r[0].get("end") or ""), reverse=True)
    if past:
        rows = "".join(f'<tr><td>{escape(o.get("store") or "")}</td><td>{escape(KIND_JA.get(o.get("kind") or "lottery", "受付"))}</td><td>{escape(_md_range(o))}</td></tr>'
                       for o, rec in past[:15])
        secs.append(f'<section class="xsec"><h2>「{escape(x)}」のこれまでの受付</h2>'
                    f'<p>受付が終わったものも含めて、これまでに見つけた「{escape(x)}」の抽選・予約・販売の記録です（{len(past)}件）。'
                    'お店や時期の傾向を見ておくと、次の受付を見つけやすくなります。</p>'
                    f'<div class="xtbl"><table><thead><tr><th>お店</th><th>種類</th><th>期間</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
        stores = list(dict.fromkeys(o.get("store") for o, _ in past if o.get("store")))
        faq.append((f"{x}はこれまでどこで受付がありましたか？", "・".join(stores[:10]) + "などで受付がありました（受付が終わったものを含む）。"))
    kinds = [KIND_JA.get(i.get("kind") or "lottery", "受付") for i in lst]
    if kinds:
        from collections import Counter
        cnt = "・".join(f"{k}{n}件" for k, n in Counter(kinds).most_common())
        faq.append((f"{x}の受付はどんな種類がありますか？", f"いま載せている{len(lst)}件の内訳は {cnt} です。"))
    ends = sorted(i["end"] for i in lst if i.get("end") and i.get("ph") == "open" and i.get("kind") != "release")
    if ends:
        faq.append((f"{x}でいちばん早く締め切る受付は？", f"{fmt(ends[0])}締切のものです（一覧の上から締切の早い順）。"))
    ph, pf = _price_sec(x, x, s)
    if ph:
        secs.append(ph)
        faq += pf
    css = ('<style>.xsec{margin:18px 0}.xsec h2{font-size:17px;margin:0 0 8px}.xsec p{font-size:14px;line-height:1.75}'
           '.xtbl{overflow-x:auto}.xtbl table{border-collapse:collapse;width:100%;font-size:13px}.xtbl th,.xtbl td{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left}</style>')
    return (css + "".join(secs)) if secs else "", faq


def _extra_detail(html, snap, me_key, recs, live, cat_by, s, t):
    """抽選の個別ページの中身を、手元にある事実のデータで増やす（11/14 ユーザー：1ページあたりのボリュームを増やしてSEOを強く）。
    ・この商品の受付の記録（ほかのお店・前の回。終わったものも45日分）
    ・このお店でいま受付中のほかの商品
    ・この商品の買取相場と定価（買取店の価格が分かるときだけ）
    ・よくある質問（データから作る。分からないことは書かない）"""
    from detail import fmt, short_name
    name = short_name(snap)
    store = snap.get("store") or ""
    g = snap.get("game")
    cshort = (cat_by.get(g) or {}).get("short", "")
    key_n = _nm_key(snap.get("series") or snap.get("product"))
    sp = snap.get("spath")
    secs = []
    # 0) 告知の要点（元の記事から取って、自分の言葉で書き直したもの。出典つき）
    if snap.get("facts"):
        from urllib.parse import urlparse
        src = snap.get("facts_src") or ""
        host = urlparse(src).netloc if src else ""
        secs.append(f'<section class="xsec"><h2>告知の要点</h2><ul>' + "".join(f"<li>{escape(f)}</li>" for f in snap["facts"]) + "</ul>"
                    + (f'<p class="note">出典：<a href="{escape(src)}" target="_blank" rel="nofollow noopener">{escape(host)}</a>（お店の告知をもとに要約しています。最新の内容は告知でご確認ください）</p>' if src else "")
                    + "</section>")
    # 1) 同じ商品の受付の記録
    same = []
    for k, rec in recs.items():
        if k == me_key:
            continue
        o = rec.get("snap") or {}
        if o.get("game") != g:
            continue
        if (sp and o.get("spath") == sp) or (key_n and len(key_n) >= 4 and _nm_key(o.get("series") or o.get("product")) == key_n):
            same.append((o, rec))
    if same:
        same.sort(key=lambda x: (x[1].get("ended", False), x[0].get("end") or "9999"))
        rows = "".join(
            f'<tr><td><a href="/{escape(rec["path"])}">{escape(o.get("store") or "")}</a></td><td>{escape(KIND_JA.get(o.get("kind") or "lottery", "受付"))}</td>'
            f'<td>{escape(_md_range(o))}</td><td>{"終了" if rec.get("ended") else "<b>受付中</b>"}</td></tr>' for o, rec in same[:12])
        n_open = sum(1 for o, r in same if not r.get("ended") and o.get("kind") != "release")
        tip = "お店ごとに期間や条件がちがうので、いくつか応募すると当たる機会が増えます。" if n_open else "いま受付中のものが無くても、再販や次の抽選が始まることがあります。"
        secs.append(f'<section class="xsec"><h2>「{escape(name)}」のほかの受付・これまでの記録</h2>'
                    f'<p>このページのほかに、「{escape(name)}」の情報を{len(same)}件見つけています（いま受付中の抽選・販売 {n_open}件）。{tip}</p>'
                    f'<div class="xtbl"><table><thead><tr><th>お店</th><th>種類</th><th>期間</th><th>状態</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
    # 2) このお店のほかの受付中
    others = [i for i in live if (i.get("store") == store) and i.get("key") != me_key and _nm_key(i.get("series") or i.get("product")) != key_n][:8]
    if others:
        secs.append(f'<section class="xsec"><h2>{escape(store)}でいま受付中のほかの商品</h2><ul>' + "".join(
            f'<li><a href="/{escape(i["lpath"])}">{escape(short_name(i))}</a>（{escape(KIND_JA.get(i.get("kind") or "lottery", "受付"))}・{escape(_md_range(i))}）</li>'
            for i in others if i.get("lpath")) + "</ul></section>")
    # 3) 買取相場と定価
    ph, faq = _price_sec(snap.get("product") or name, name, s)
    if ph:
        secs.append(ph)
    # 4) よくある質問（データから）
    kind = KIND_JA.get(snap.get("kind") or "lottery", "受付")
    if snap.get("end") and snap.get("kind") != "release":
        faq.insert(0, (f"{store}の「{name}」の{kind}の締切はいつ？", f"{fmt(snap['end'])}までです（{_md_range(snap)}）。締切は早まることがあるので、応募ページでご確認ください。"))
    if snap.get("announce"):
        faq.append((f"当選発表はいつ？", f"{snap['announce']}の予定です（お店の告知より）。"))
    ch = snap.get("channel")
    if snap.get("kind") == "release":
        pass
    elif ch == "store":
        faq.append(("応募はどこでする？", f"{store}の店頭での受付です" + (f"（{snap['area']}）" if snap.get("area") else "") + "。対象の店舗はお店の告知でご確認ください。"))
    elif snap.get("url"):
        from urllib.parse import urlparse
        faq.append(("応募はどこでする？", f"ネットで受け付けています（{urlparse(snap['url']).netloc}）。このページの「応募ページを開く」から進めます。"))
    if snap.get("conditions"):
        faq.append(("応募の条件は？", re.sub(r"\s+", " ", str(snap["conditions"]))[:200]))
    if same:
        stores_ = list(dict.fromkeys(o.get("store") for o, r in same if not r.get("ended") and o.get("store") and o.get("kind") != "release"))
        if stores_:
            faq.append((f"ほかに「{name}」を受け付けているお店は？", "・".join(stores_[:8]) + "でも受け付けています（上の表）。"))
    if faq:
        secs.append('<section class="xsec"><h2>よくある質問</h2><dl class="xfaq">' + "".join(
            f"<dt>{escape(q)}</dt><dd>{escape(a)}</dd>" for q, a in faq) + "</dl></section>")
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        html = html.replace("</head>", '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script></head>", 1)
    try:   # AIの解説（受付のデータだけから作ったもの。game_aitext）を、いちばん上に
        import game_aitext
        ai_h = game_aitext.html_for("l:" + me_key)
        if ai_h:
            secs.insert(0, f'<section class="xsec xai">{ai_h}</section>')
    except Exception:
        pass
    if not secs:
        return html
    css = ('<style>.xai h2{font-size:16px;margin:14px 0 6px}.xai .note{font-size:12px;color:#666}.xsec{margin:18px 0}.xsec h2{font-size:17px;margin:0 0 8px}.xsec p{font-size:14px;line-height:1.75}'
           '.xtbl{overflow-x:auto}.xtbl table{border-collapse:collapse;width:100%;font-size:13px}.xtbl th,.xtbl td{border-bottom:1px solid var(--rule,#ddd);padding:6px 4px;text-align:left}'
           '.xsec ul{padding-left:1.2em;font-size:14px;line-height:1.8}.xfaq dt{font-weight:700;margin-top:10px;font-size:14px}.xfaq dd{margin:4px 0 0;font-size:14px;line-height:1.7}</style>')
    block = css + "".join(secs)
    if '<nav class="more"' in html:
        return html.replace('<nav class="more"', block + '<nav class="more"', 1)
    return html.replace("<footer>", block + "<footer>", 1)


_UPC = {}


def _photo_for(product, s):
    """商品名に当たる楽天ブックスの商品の写真と商品ページ（アフィリエイト）→ {"u", "img"} か None。
    買取相場の商品（楽天ブックスの商品ページと写真が分かるもの）→ 発売予定のゲーム（楽天ブックス）の順に探す。名前がよく合うものだけ"""
    import game_affi
    import game_premium
    import official_link as ol
    if not product:
        return None
    x = game_premium.price_match(product, s)
    if x and x.get("img") and x.get("itemUrl"):
        return {"u": game_affi.rakuten_link(x["itemUrl"], game_affi.affiliate_id(s)), "img": game_affi.thumb(x["img"])}
    if "u" not in _UPC:
        import game_upcoming
        _UPC["u"] = [v for v in ((load_json(game_upcoming.STATE, {}) or {}).get("items") or {}).values() if v.get("img") and v.get("url")]
    best = None
    for v in _UPC["u"]:
        sc = ol.same_item_score(product, v.get("title") or "")
        if sc >= 0.75 and (best is None or sc > best[0]):
            best = (sc, v)
    if best:
        return {"u": game_affi.rakuten_link(best[1]["url"], game_affi.affiliate_id(s)), "img": game_affi.thumb(best[1]["img"])}
    return None


def _shop_detail(html, snap):
    """個別ページ：応募ボタンの下に「楽天で見る」「Amazonで見る」、写真に大きさ、下に写真の出どころ（detail.py は変えない）"""
    sh = snap.get("shop") or {}
    if snap.get("avail"):   # いま予約・販売しているお店をいちばん目立つところ（見出しのすぐ下）に
        html = html.replace("</style>", AV_CSS + "</style>", 1)
        html = re.sub(r"(</h1>)", lambda m: m.group(1) + avail_html(snap["avail"]), html, count=1)
    b = shop_buttons(sh.get("rk"), sh.get("az"), yh=game_affi.yahoo_link(sh.get("yh", "")), mc=sh.get("mc", ""))   # 前に保存したリンクもアフィリンクに
    if b:
        html = html.replace('<div class="sub-acts">', f'<div class="shopb">{b}</div><div class="sub-acts">', 1)
    if snap.get("image"):
        html = re.sub(r'(<div class="pics n1"><a [^>]*><img )', r'\1width="150" height="150" ', html, count=1)
        html = html.replace("</footer>", f'<span class="credit">{CREDIT[3:-4]}</span></footer>', 1)
    return html


def _fmt(s):
    dt = parse_dt(s)
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}) {dt:%H:%M}" if dt else "要確認"


def _brand(s):
    name = s.get("site_name") or "ゲーム・ホビー入荷速報"
    site = (s.get("site_public_url") or "").rstrip("/")
    dom = re.sub(r"^https?://", "", site) or "game-nyuka.com"
    color = s.get("theme_color") or "#1b3a5c"
    kinds = dict(gamecats.KINDS, **(s.get("kind_names") or {}))
    return {
        "name": name, "domain": dom, "color": color, "kinds": kinds,
        "logo": f'<small>{escape(s.get("site_name_en") or "GAME &amp; HOBBY RESTOCK NEWS")}</small><span class="w">{escape(name)}</span>',
        "logo_font": "",
        "footer": f"{name}は抽選・予約・再入荷の情報をまとめているサイトです。申し込み・購入は各店舗のページで行われます。記載の社名・製品名は各社の商標です。当サイトは各社と関係ありません。",
        "online": "ネット（当選・予約後に発送）", "store": "店頭受取",
        "chip_online": "ネット", "chip_store": "店頭受取", "others": "ほかの情報を見る", "mylist": False,
    }


def _series_cfg():
    import yaml
    p = ROOT / "config" / "game" / "models.yaml"
    y = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    alias = {g: {normalize(k): v for k, v in (m or {}).items()} for g, m in (y.get("series_aliases") or {}).items()}
    return {"alias": alias, "slug": y.get("series_slugs") or {}, "info": y.get("series_info") or {}}


_CFG = {}


def canon_series(game, series):
    if not series:
        return None
    if not _CFG:
        _CFG.update(_series_cfg())
    al = _CFG["alias"].get(game, {})
    x = series.strip()
    return al.get(normalize(x), x) if normalize(x) in al else x


def series_slug(game, series):
    if not _CFG:
        _CFG.update(_series_cfg())
    x = canon_series(game, series) or series
    slug = (_CFG["slug"].get(game) or {}).get(x)
    if not slug and re.fullmatch(r"[A-Za-z0-9 .\-]+", x or ""):
        slug = re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-")
    if not slug:
        slug = (sg.romaji(x)[:30].strip("-") or "m") + "-" + sha(normalize(x))[:5]
    return slug


def _store_slug(store):
    return chain_of(store) or (sg.romaji(re.sub(r"[（(【［\[].*?[）)】］\]]", "", store or ""))[:30].strip("-") or "shop") + "-" + sha(normalize(store or ""))[:5]


def _x_draft(out, items, s, site, updated, cats):
    """Xの下書きページ（手で投稿する用・noindex）。テンプレ：予約開始/抽選開始速報・PS5 Pro申込・本日締切・結果発表・朝のまとめ"""
    kinds = dict(gamecats.KINDS, **(s.get("kind_names") or {}))
    data = [{k: i.get(k) for k in ("game", "store", "product", "series", "kind", "start", "end", "announce", "price", "lpath", "tags", "channel", "found_at")} for i in items]
    tags = {c["id"]: c.get("hashtags") or "" for c in cats}
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Xの下書き｜{escape(s.get("site_name") or "")}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px;line-height:1.6;color:#111}}
h1{{font-size:20px}}h2{{font-size:16px;margin:24px 0 6px}}.d{{border:1px solid #ccc;border-radius:8px;padding:10px;margin:8px 0;background:#fafafa}}
textarea{{width:100%;min-height:150px;font:14px/1.5 system-ui;border:1px solid #bbb;border-radius:6px;padding:8px}}
button{{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #888;background:#fff;cursor:pointer}}
small{{color:#666}}.sel{{margin:6px 0}}</style></head><body>
<h1>Xの下書き（{escape(s.get("site_name") or "")}）</h1>
<p><small>更新 {escape(_fmt(updated))}。このページは検索に載せていません。文はブラウザで「今」の時刻から作っています。コピーして手で投稿してください。</small></p>
<div id="app"></div>
<script type="application/json" id="d">{json.dumps({"items": data, "site": site, "kinds": kinds, "tags": tags, "cats": {c["id"]: c.get("short") for c in cats}}, ensure_ascii=False).replace("</", "<\\/")}</script>
<script>
(function(){{var D=JSON.parse(document.getElementById("d").textContent),I=D.items,W="月火水木金土日",N=new Date();
function f(iso){{var d=new Date(iso);if(isNaN(d))return"";return(d.getMonth()+1)+"/"+d.getDate()+"("+W[(d.getDay()+6)%7]+") "+("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2)}}
function same(a,b){{a=new Date(a);return a.getFullYear()==b.getFullYear()&&a.getMonth()==b.getMonth()&&a.getDate()==b.getDate()}}
function url(i){{return i.lpath?D.site+"/"+i.lpath:D.site+"/"}}
function nm(i){{return (i.series&&i.product&&i.product.indexOf(i.series)<0)?i.series+" "+i.product:(i.product||i.series)}}
function tg(i){{return D.tags[i.game]||""}}
var open=I.filter(function(i){{return i.kind!="release"&&(!i.end||Date.parse(i.end)>N)&&(!i.start||Date.parse(i.start)<=N)}});
var today=I.filter(function(i){{return i.end&&same(i.end,N)&&Date.parse(i.end)>N&&i.kind!="release"}});
var starts=I.filter(function(i){{return i.start&&Date.parse(i.start)>N-864e5}}).sort(function(a,b){{return a.start>b.start?1:-1}});
var ann=I.filter(function(i){{return i.announce&&/^\\d{{4}}-/.test(i.announce)&&same(i.announce,N)}});
var ps5pro=I.filter(function(i){{return /PS5 ?Pro/i.test((i.series||"")+(i.product||""))&&i.kind=="lottery"&&(!i.end||Date.parse(i.end)>N)}});
var H=[];
function sec(t,txt){{H.push("<h2>"+t+"</h2><div class=d><textarea>"+txt.replace(/</g,"&lt;")+"</textarea><br><button onclick=\\"navigator.clipboard.writeText(this.parentNode.querySelector('textarea').value);this.textContent='コピーしました'\\">コピー</button> <small>"+(txt.length)+"文字</small></div>")}}
if(starts.length){{var i=starts[0];sec("速報：予約開始・抽選開始",("【"+(D.kinds[i.kind]||"")+"開始】"+i.store+"\\n"+nm(i)+(i.price?"（定価 "+i.price+"）":"")+"\\n"+(i.start?"開始 "+f(i.start)+"\\n":"")+(i.end?"締切 "+f(i.end)+"\\n":"")+url(i)+"\\n"+tg(i)))}}
if(ps5pro.length){{var p=ps5pro[0];sec("PS5 Pro の申込",("PS5 Pro の"+(D.kinds[p.kind]||"抽選")+"受付中（"+p.store+"）\\n"+(p.end?"締切 "+f(p.end)+"\\n":"")+((p.tags||[]).length?"条件："+p.tags.join("・")+"\\n":"")+"条件は公式で確認してください\\n"+url(p)+"\\n#PS5Pro #PS5抽選 #PS5"))}}
if(today.length){{sec("本日締切",("【本日締切】"+(today.length)+"件\\n"+today.slice(0,6).map(function(i){{return "・"+i.store+" "+nm(i)+" "+f(i.end).split(" ")[1]+"まで"}}).join("\\n")+"\\n"+D.site+"/today/\\n"+(tg(today[0])||"")))}}
if(ann.length){{sec("結果発表",("【本日 結果発表】\\n"+ann.slice(0,6).map(function(i){{return "・"+i.store+" "+nm(i)}}).join("\\n")+"\\n当選メール・マイページをご確認ください\\n"+D.site+"/\\n"+(tg(ann[0])||"")))}}
var byc={{}};open.forEach(function(i){{(byc[i.game]=byc[i.game]||[]).push(i)}});
sec("朝のまとめ",("【"+(N.getMonth()+1)+"/"+N.getDate()+" いま受付中】\\n"+Object.keys(byc).map(function(g){{return (D.cats[g]||g)+" "+byc[g].length+"件"}}).join(" / ")+"\\n"+open.sort(function(a,b){{return (a.end||"9")>(b.end||"9")?1:-1}}).slice(0,5).map(function(i){{return "・"+i.store+" "+nm(i)+(i.end?"（"+f(i.end)+"まで）":"")}}).join("\\n")+"\\n"+D.site+"/\\n#PS5 #Switch2 #ガンプラ #入荷速報"));
if(!H.length)H.push("<p>いま下書きにできる情報がありません。</p>");document.getElementById("app").innerHTML=H.join("")}})();
</script></body></html>"""
    (out / "x-draft.html").write_text(html, encoding="utf-8")


def _privacy(s):
    name = s.get("site_name") or "ゲーム・ホビー入荷速報"
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>プライバシーポリシー｜{escape(name)}</title><meta name="robots" content="noindex,follow">'
            '<style>body{font-family:system-ui,sans-serif;max-width:680px;margin:0 auto;padding:24px 16px;line-height:1.8;color:#222}h1{font-size:20px}h2{font-size:16px}</style></head><body>'
            f'<h1>プライバシーポリシー</h1><p>{escape(name)}（以下「当サイト」）は、ゲーム機・ホビーの抽選販売・予約・再入荷の情報をまとめて掲載する個人運営のサイトです。</p>'
            '<h2>広告について</h2><p>当サイトはアフィリエイトプログラム（Amazonアソシエイト・楽天アフィリエイトなど）に参加しており、リンク先での購入により収入を得ることがあります。'
            'Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。</p>'
            '<h2>アクセス解析について</h2><p>当サイトはGoogleアナリティクスを利用する場合があります。データはCookieを使って匿名で集められ、個人を特定するものではありません。</p>'
            '<h2>掲載情報について</h2><p>掲載している受付期間・条件・価格は各店舗・各メーカーの公式発表を元に自動で収集したものです。内容は変わることがあるため、申し込み前に必ず公式ページでご確認ください。'
            '当サイトはフリマ・転売の価格を掲載しません。記載の社名・製品名は各社の商標です。当サイトは各社と関係ありません。</p>'
            '<p><a href="/">トップへ戻る</a></p></body></html>')


def _n_stores():
    """買取価格を読んでいる店の数（設定の有効な店）"""
    try:
        import game_kaitori
        return len(game_kaitori.stores())
    except Exception:
        return 10


def _write_x_queue(out, items, site, t=None):
    """11/10 ユーザーの指示：大手のポケカ・ワンピースカードの抽選は、ゲーム垢（@a9994aaa）に「このサイトの抽選ページ」のリンク付きでXの予約投稿をする。
    予約の作業（ユーザーのパソコンの予定作業）がこの /x-queue.json を読む。キー：g|抽選のキー|pre（見つけた→3分後）・|start（受付開始の時刻）
    1日に予告は6本まで（締切が近い順）"""
    import json as _json
    from datetime import timedelta as _td
    t = t or now()
    q = []
    pk = [i for i in items if i.get("game") in ("pokemon", "onepiece") and i.get("ph") != "ended" and i.get("lpath")
          and i.get("verified") is True and not i.get("from_tcg")]   # 元の記事で確かめたものだけ予約投稿する（トレカ抽選ナビから載せたものは投稿しない 11/14）
    fresh = sorted([i for i in pk if parse_dt(i.get("found_at")) and parse_dt(i["found_at"]) > t - _td(hours=12)],
                   key=lambda i: i.get("end") or "9999")[:6]
    for i in fresh:
        st, en = parse_dt(i.get("start")), parse_dt(i.get("end"))
        if st and st < t - _td(hours=12):
            continue   # 受付が始まって半日以上たっている抽選は、このサイトが遅れて見つけただけ＝ニュースではないので出さない（11/10 ポケセンのハドウシーカー）
        kind = {"lottery": "抽選", "preorder": "予約", "restock": "再販", "first_come": "先着販売", "invite": "招待販売"}.get(i.get("kind"), "抽選")
        url = f"{site}/{i['lpath']}"
        nm = "ポケカ" if i["game"] == "pokemon" else "ワンピースカード"
        def text(head, when):
            ls = [head, "", f"【{i.get('store')}】{i.get('product')}", f"▶{kind}"]
            if when:
                ls.append(when)
            if en:
                ls.append(f"▶締切 {_fmt(i['end'])}")
            ls += ["", "応募の条件・方法はこちら👇", url, "", "#ポケモンカード #ポケカ抽選" if i["game"] == "pokemon" else "#ワンピースカード #ワンピカード"]
            return "\n".join(ls)
        if st and st > t:
            q.append({"k": f"g|{i['key']}|pre", "at": i["found_at"], "text": text(f"🔔{nm}の抽選が決まったよ！", f"▶受付開始 {_fmt(i['start'])}〜")})
            q.append({"k": f"g|{i['key']}|start", "at": st.isoformat(), "text": text(f"🔔{nm}の抽選、受付スタート！", "")})
        else:
            q.append({"k": f"g|{i['key']}|pre", "at": i["found_at"], "text": text(f"🔔{nm}の抽選、受付中だよ！", "")})
    (out / "x-queue.json").write_text(_json.dumps(sorted(q, key=lambda x: x["at"]), ensure_ascii=False), encoding="utf-8")
    return q


TOP_CSS = (".tp-sec{margin:18px 0 22px}.tp-sec h2{display:flex;align-items:center;gap:8px;font-size:19px;margin:0 0 10px;padding-left:10px;border-left:4px solid #ffd23f}"
           ".tp-sec h2 small{font-size:12px;font-weight:700;color:#8a93a6}.tp-more{display:inline-block;margin-top:10px;font-weight:800;color:#ffd23f}"
           ".sk{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}"
           ".sk-i{display:flex;gap:10px;align-items:center;padding:10px;border:1px solid #262c3a;border-radius:12px;background:#141823;color:#e9edf5;text-decoration:none}"
           ".sk-i:hover{border-color:#ffd23f}.sk-i img,.sk-i .ni{flex:0 0 64px;width:64px;height:64px;border-radius:8px;object-fit:contain;background:#fff}"
           ".sk-i b{display:block;font-size:14px;line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}"
           ".sk-tag{display:inline-block;margin:4px 6px 0 0;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:800;background:#ffd23f;color:#0b0d12}"
           ".sk-tag.pre{background:#5ee0ff}.sk-tag.off{background:#3a4152;color:#c3c9d6}.sk-m{font-size:12px;color:#8a93a6}.sk-i.off{opacity:.6}")
TOP_JS = ("<script>(function(){var n=Date.now();document.querySelectorAll('[data-ago]').forEach(function(e){var m=Math.max(0,Math.round((n-Date.parse(e.dataset.ago))/60000));"
          "e.textContent=m<60?m+'分前':m<1440?Math.round(m/60)+'時間前':Math.round(m/1440)+'日前';});})();</script>")


def _sokuhou(wmap, allx, limit=8):
    """トップの「最新の速報」：見張り（楽天・Amazon）が「売り切れ→販売・予約・招待」になったのを見つけた商品。新しい順。
    いまも売っているものは「販売中」、もう売り切れたものは薄く「終了」"""
    by_jan = {x["jan"]: x for x in allx}
    hist, st2 = (wmap or {}).get("_hist") or {}, (wmap or {}).get("_st2") or {}
    ev = []
    for shop in ("rk", "az"):
        for k, lst in (hist.get(shop) or {}).items():
            if not k.startswith("j") or k[1:] not in by_jan:
                continue
            lst = lst or []
            for n_, e in enumerate(lst):   # 新しい順。「売り切れ→販売・予約・招待」に変わった時だけ（いつも売っている商品は速報ではない）
                if e.get("s") in ("buy", "pre", "invite") and n_ + 1 < len(lst) and lst[n_ + 1].get("s") == "none":
                    ev.append((e.get("t") or "", shop, k, e))
                    break   # 一番新しいものだけ
    ev.sort(key=lambda v: v[0], reverse=True)
    out, seen = [], set()
    lab = {"buy": "販売中", "pre": "予約受付中", "invite": "招待受付中"}
    for t, shop, k, e in ev:
        if k in seen:
            continue
        seen.add(k)
        x = by_jan[k[1:]]
        cur = ((st2.get(shop) or {}).get(k) or {})
        live = cur.get("s") in ("buy", "pre", "invite")
        where = "楽天ブックス" if shop == "rk" else "Amazon"
        tag = (f'<span class="sk-tag{" pre" if cur.get("s") != "buy" else ""}">{lab[cur["s"]]}</span>' if live else '<span class="sk-tag off">いまは売り切れ</span>')
        price = e.get("p") or cur.get("p")
        img = f'<img src="{escape(x["img"])}" alt="" loading="lazy" width="64" height="64">' if x.get("img") else '<span class="ni"></span>'
        out.append(f'<a class="sk-i{"" if live else " off"}" href="/premium/{escape(x["jan"])}/">{img}<span><b>{escape(x["name"])}</b>'
                   f'{tag}<span class="sk-m">{where}{f" {int(price):,}円" if price else ""} ・ <span data-ago="{escape(t)}"></span></span></span></a>')
        if len(out) >= limit:
            break
    return "".join(out)


def _top_blocks(allx, wmap, cats, counts, s):
    """トップ（11/14 ユーザー「1いこ」）：最新の速報 → 定価より高く売れるTOP10 →（締切が近い抽選は一覧の部分）→ ジャンル"""
    import game_premium
    import game_affi
    aff = game_affi.affiliate_id(s)
    sk = _sokuhou(wmap, allx)
    top = f"<style>{TOP_CSS}</style><style>{game_premium.CSS}</style>"
    if sk:
        top += ('<section class="tp-sec"><h2>最新の速報<small>楽天ブックス・Amazonで定価販売・予約が始まった商品</small></h2>'
                f'<div class="sk">{sk}</div><p class="note">見張りが2分ごとに確かめています。始まったらXですぐお知らせします。</p></section>')
    prem = [x for x in allx if x.get("ratio") and x["ratio"] >= float(s.get("premium_min_ratio", 1.03))]
    prem.sort(key=lambda x: -x["ratio"])
    if prem:
        cards = [{"name": x["name"], "jan": x["jan"], "url": f"/premium/{x['jan']}/", "img": x.get("img", ""), "teika": x["teika"], "max": x["max"],
                  "tn": x.get("teika_note", ""), "store": x["store"], "ratio": x["ratio"],
                  "rk": game_affi.rakuten_link(x["itemUrl"], aff) if x.get("itemUrl") else "", "az": x.get("azUrl", ""),
                  "imgu": x.get("azUrl", "") if x.get("img_az") else ""} for x in prem[:10]]
        top += ('<section class="tp-sec"><h2>定価より高く売れる TOP10<small>買取店の新品の最高買取 ÷ 定価</small></h2>'
                f'{game_premium.plist_html(cards)}<a class="tp-more" href="/premium/">プレミア商品一覧をすべて見る（{len(prem)}件）→</a></section>')
    chips = "".join(f'<li><a href="/{escape(c["slug"])}/">{escape(c["short"])}<small>{counts.get(c["id"], 0)}</small></a></li>'
                    for c in sorted(cats, key=lambda c: -counts.get(c["id"], 0)) if counts.get(c["id"]))
    bottom = (f'<style>{game_premium.SG_CSS}</style><section class="tp-sec"><h2>ジャンルから探す</h2><ul class="sgmenu">{chips}</ul>'
              '<p><a class="tp-more" href="/chusen/">受付中の抽選・予約をすべて見る →</a></p></section>' + TOP_JS)
    return top, bottom


SETS_CSS = (".st-l{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}"
            ".st-i{display:block;padding:12px 14px;border:1px solid #262c3a;border-radius:12px;background:#141823;color:#e9edf5;text-decoration:none}"
            ".st-i:hover{border-color:#ffd23f}.st-i b{display:block;font-size:15px;line-height:1.4}"
            ".st-n{display:inline-block;margin:6px 6px 4px 0;padding:1px 9px;border-radius:999px;background:#ffd23f;color:#0b0d12;font-size:12px;font-weight:800}"
            ".st-d{font-size:12px;color:#ff8a95;font-weight:700}.st-s{display:block;font-size:12.5px;color:#aab2c3;line-height:1.6}")


def _sets_html(c, sub):
    """ポケカ・ワンピのカテゴリページの「弾ごとの抽選」：弾ごとに、受付中・予告の数・やっているお店・いちばん近い締切（11/14 ユーザー）"""
    by = {}
    for i in sub:
        if i["ph"] in ("open", "upcoming"):
            by.setdefault(i.get("series") or "そのほか", []).append(i)
    if not by:
        return ""
    cards = []
    for nm, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        stores = list(dict.fromkeys(i["store"] for i in sorted(lst, key=lambda i: i.get("end") or "9999") if i.get("store")))
        ends = sorted(i["end"] for i in lst if i["ph"] == "open" and i.get("end"))
        no = sum(1 for i in lst if i["ph"] == "open")
        path = lst[0].get("spath") or f'{c["slug"]}/'
        cards.append(f'<a class="st-i" href="/{escape(path)}"><b>{escape(nm)}</b>'
                     f'<span class="st-n">受付中 {no}件</span>' + (f'<span class="st-n" style="background:#5ee0ff">予告 {len(lst) - no}件</span>' if len(lst) > no else "")
                     + (f'<span class="st-d">いちばん近い締切 {escape(_fmt(ends[0]))}</span>' if ends else "")
                     + f'<span class="st-s">{escape("・".join(stores[:8]))}{f" ほか{len(stores) - 8}店" if len(stores) > 8 else ""}</span></a>')
    return (f'<style>{SETS_CSS}</style><section class="sec"><h2>{escape(c["short"])}の弾ごとの抽選（{len(by)}種類）</h2>'
            '<p class="note">同じ弾の抽選をまとめています。押すと、その弾の抽選をやっているお店の一覧が見られます。</p>'
            f'<div class="st-l">{"".join(cards)}</div></section>')


def _simple_page(cats, html):
    """404・プライバシーポリシー：本文を左のメニューつきの暗い見た目で包む"""
    css = SHELL_CSS.read_text(encoding="utf-8") + ".doc{max-width:680px;line-height:1.85}.doc h1{font-size:22px;font-weight:900}.doc h2{font-size:16px;margin-top:24px}.doc p{color:var(--ink-2)}"
    html = re.sub(r"<style>.*?</style>", "", html, count=1, flags=re.S)
    html = html.replace("</head>", f'<meta name="theme-color" content="{BG}">{FONTS}<style>{css}</style></head>', 1)
    head, body = html.split("<body>", 1)
    body = body.replace("</body></html>", "")
    return f'{head}<body><div class="shell">{side_html(cats, counts=False)}<main class="main doc">{SEARCH_FORM}{body}</main></div></body></html>'


def _favicon_svg(color, accent):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="{color}"/>'
            f'<rect x="12" y="22" width="40" height="22" rx="6" fill="#fff"/><circle cx="24" cy="33" r="5" fill="{color}"/>'
            f'<circle cx="41" cy="30" r="3" fill="{accent}"/><circle cx="47" cy="36" r="3" fill="{accent}"/></svg>')


def _og_default(path, s, brand):
    try:
        sg.og_image(path, "GAME & HOBBY", s.get("accent_color") or "#0f8b8d", s.get("site_name") or "ゲーム・ホビー入荷速報",
                    [("抽選・予約・再入荷", "定価で買う", True), ("PS5・Switch 2・ガンプラ・フィギュア", "1日6回更新", False)],
                    sub=s.get("site_tagline") or "", brand=(brand["name"], brand["domain"]))
        return True
    except Exception as e:
        log(f"OG画像: スキップ {e}")
        return False


def _icon_png(path, color, size):
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (size, size), color)
        d = ImageDraw.Draw(im)
        m = size // 5
        d.rounded_rectangle([m, size * 0.36, size - m, size * 0.68], radius=size // 10, fill="#ffffff")
        d.ellipse([size * 0.3, size * 0.44, size * 0.44, size * 0.58], fill=color)
        im.save(path)
    except Exception as e:
        log(f"アイコン: スキップ {e}")


def _phase(i, t):
    """サーバー側の目安（検索エンジン向けの一覧・件数に使う。画面はブラウザが「今」で計算し直す）"""
    s, e = parse_dt(i.get("start")), parse_dt(i.get("end"))
    k = i.get("kind")
    if k == "release":
        return "ended" if e and e.date() < t.date() else "announced"
    if k in ("restock", "first_come"):
        return "ended" if e and e < t else "restock"
    if e and e < t:
        a = parse_dt(i.get("announce")) if re.match(r"\d{4}-", str(i.get("announce") or "")) else None
        if k in ("lottery", "fukubukuro") and ((a and a.date() >= t.date()) or (not a and (t - e).days < 7)):
            return "waiting"
        return "ended"
    if s and s > t:
        return "upcoming"
    return "open"


PH_LABEL = {"open": "受付中", "upcoming": "予告", "waiting": "結果待ち", "restock": "再入荷・先着", "announced": "発売・再販", "ended": "終了"}


def _gone_redirects(out, pmod, limit=1800):
    """前に出していたのに今回は無くなったページ（受付が全部終わった商品のまとめ・プレミア一覧から外れた商品など）を、
    いちばん近い上の階層のページ（無ければトップ）へ 301 で転送する行。検索やXの古いリンクから来た人が「見つかりません」にならないように（11/13）。
    今あるページは転送しない（Cloudflare Pages は _redirects をファイルより先に使うため）。行数は Cloudflare の上限（2,000）より少なく。"""
    rows = []
    for path, v in pmod.items():
        p = str(path or "").strip("/")
        if not p or not re.fullmatch(r"[A-Za-z0-9._/-]+", p) or (out / p / "index.html").exists():
            continue
        parts = p.split("/")[:-1]
        while parts and not (out / "/".join(parts) / "index.html").exists():
            parts.pop()
        to = "/" + "/".join(parts) + "/" if parts else "/"
        last = str(v[1] or "") if isinstance(v, list) and len(v) > 1 else ""
        rows.append((last, f"/{p}/ {to} 301"))
    rows.sort(key=lambda r: r[0], reverse=True)   # 新しく消えたものを優先
    return "".join(line + "\n" for _, line in rows[:limit])


def build(settings=None, out_dir=None, force=False):
    from common import load_settings
    s = settings or load_settings()
    cats = s.get("categories") or gamecats.categories()
    cat_by = {c["id"]: c for c in cats}
    groups = s.get("category_groups") or gamecats.groups()
    kinds = dict(gamecats.KINDS, **(s.get("kind_names") or {}))
    brand = _brand(s)
    site = (s.get("site_public_url") or os.environ.get("SITE_URL_GAME") or "").rstrip("/")
    tag = game_affi.amazon_tag(s)   # AMAZON_TAG_GAME → settings の amazon_tag → トレカと同じ AMAZON_TAG
    out = Path(out_dir or ROOT / "site_game")
    souba_st = load_json("souba.json", {})
    kaitori_st = load_json("kaitori.json", {})
    kaitori_multi = load_json("kaitori_multi.json", {})
    watch_status = (load_json("watch_map.json", {}) or {}).get("_status") or {}
    t = now()
    verify = s.get("google_site_verification") or ""

    raw = load_json("lotteries.json", {})
    rk_cache = load_json(game_affi.CACHE, {})   # 楽天ブックスの商品ページ・写真（game_affi.update が作る）
    shop_models = game_affi._models()
    items = []
    for i in raw.values():
        st = i.get("status")
        e = parse_dt(i.get("end"))
        if st not in ACTIVE + ("closed", "expired"):
            continue
        if e and e < t and ((t - e).days > KEEP_ENDED_DAYS or i.get("kind") == "release" and (t - e).days > 1):
            continue  # 終わってしばらくたったもの（終了のタブに少しだけ残す）
        if st not in ACTIVE and not e:
            continue
        if i.get("game") not in cat_by:
            continue
        if not shown_ok(i):
            continue   # 元の記事と合わなかった・まだ確かめていない新着（game_verify）はサイトに出さない
        row = {k: i.get(k) for k in FIELDS}
        row["verified"] = i.get("verified")
        row["from_tcg"] = bool(i.get("from_tcg"))   # トレカ抽選ナビから載せた抽選（X投稿しない）
        row["kind"] = row.get("kind") or "lottery"
        row["lpath"] = detail.lottery_path(i)
        try:
            import game_souba
            sb = game_souba.for_item(dict(i, series=canon_series(i["game"], i["series"]) if i.get("series") else None), souba_st)
            if sb:
                row["sb"] = sb["text"] + (f"・{sb['hint']}" if sb["hint"] else "")
            else:   # スニダンに無い商品は、買取店の新品の買取価格（全店でいちばん高いところ）
                import game_kaitori
                bk = game_kaitori.best_for(i, kaitori_multi)
                if bk:
                    row["sb"] = game_kaitori.label(i, bk)
                else:
                    kp = game_souba.kaitori_for(i, kaitori_st)
                    if kp:
                        row["sb"] = game_souba.kaitori_label(i, kp)
        except Exception:
            pass
        if row.get("series"):
            row["series"] = canon_series(i["game"], row["series"])
            row["spath"] = f"{cat_by[i['game']]['slug']}/{series_slug(i['game'], row['series'])}/"
        if row.get("store"):
            ch = chain_of(row["store"])
            if ch:
                row["chain"] = ch
                row["rec"] = bool(CHAIN[ch][3])
        row["ph"] = _phase(row, t)
        row.update(game_affi.links_for(i, rk_cache, s, shop_models))   # rk（楽天の商品ページ・写真）・az（Amazonの商品ページ）
        if not (row.get("rk") or {}).get("img"):   # 写真が無い行は、買取相場・発売予定の商品（楽天ブックス）の写真と商品ページで補う（11/14 ユーザー：抽選一覧に写真をアフィリンク付きで）
            try:
                _ph = i.get("photo") or game_affi.photo_for(i, rk_cache, s, shop_models) or _photo_for(i.get("product") or "", s)
                if _ph:
                    row["rk"] = _ph
            except Exception:
                pass
        av = avail_of(row, watch_status)
        if av:
            row["avail"] = av   # いま楽天・Amazonで予約受付中・販売中（見張りが見た状態）→ カード・個別ページの目立つところに
        items.append(row)
    # ポケカ・ワンピ：写真の無い抽選は、同じ弾のほかの抽選の写真を使う（弾の名前をそろえてあるので同じ商品。11/14 ユーザー：写真を埋めて）
    _setph = {}
    for r_ in items:
        if r_.get("series") and (r_.get("rk") or {}).get("img") and not (r_.get("rk") or {}).get("search"):
            _setph.setdefault((r_["game"], r_["series"]), r_["rk"])
    for r_ in items:
        if not (r_.get("rk") or {}).get("img") and (r_.get("game"), r_.get("series")) in _setph and (cat_by.get(r_["game"]) or {}).get("sets"):
            r_["rk"] = dict(_setph[(r_["game"], r_["series"])])
    live = [i for i in items if i["ph"] != "ended"]
    import game_premium
    try:   # カテゴリごとの商品一覧（買取相場の商品＋抽選・発売の商品）→ 左メニューの数・カテゴリページ
        pidx = game_premium.product_index(s, live)
    except Exception as e:
        log(f"商品一覧: スキップ {e}")
        pidx = {}
    PCOUNTS.clear()
    PCOUNTS.update({cid: len(v) for cid, v in pidx.items()})

    meta_state = load_json("site_meta.json", {})
    digest = sha(json.dumps(sorted(items, key=lambda x: x.get("key") or ""), ensure_ascii=False, sort_keys=True) + t.date().isoformat()
                 + str(sorted((c["id"], c["enabled"]) for c in cats)) + json.dumps(s.get("amazon_invite") or {}, ensure_ascii=False))
    changed = meta_state.get("digest") != digest
    force = force or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not changed and not force and out_dir is None:
        (out / ".changed").unlink(missing_ok=True)
        print("ゲームサイト: 変化なしなので作り直さない")
        return out
    updated = t.isoformat() if changed or not meta_state.get("updated") else meta_state["updated"]
    upd = parse_dt(updated) or t
    md = f"{upd.month}/{upd.day}"
    tpl = TEMPLATE.read_text(encoding="utf-8")
    urls = []
    pmod = load_json("page_lastmod.json", {})
    today_iso = t.date().isoformat()

    cats_js = {c["id"]: {"short": c["short"], "slug": c["slug"], "color": c.get("color") or "#1b3a5c", "group": c["group"], "sf": 1 if c.get("sets") else 0} for c in cats}   # sf：一覧でお店の名前を先に出す（ポケカ・ワンピ）
    # 左のメニューのカテゴリ別の件数用（受付状況はブラウザで今の時刻から数える）：[カテゴリ, 開始, 締切, 種類, 発表日]（日時は1970年からの分）
    _mins = lambda x: int(x.timestamp() // 60) if x else 0
    cc = [[i["game"], _mins(parse_dt(i.get("start"))), _mins(parse_dt(i.get("end"))), i["kind"],
           _mins(parse_dt(i.get("announce")) if re.match(r"\d{4}-", str(i.get("announce") or "")) else None)] for i in live]
    common_data = {"updated": updated, "kinds": kinds, "cats": cats_js, "groups": groups, "cc": cc}
    shell_css = SHELL_CSS.read_text(encoding="utf-8")

    def pin_html():
        inv = s.get("amazon_invite") or {}
        if not (inv.get("enabled") and inv.get("url")):
            return ""
        u = inv["url"]
        if tag and "amazon." in u and "tag=" not in u:
            u += ("&" if "?" in u else "?") + f"tag={tag}"
        return (f'<a class="pin" href="{escape(u)}" target="_blank" rel="nofollow sponsored noopener"><b>{escape(inv.get("label") or "Amazon 招待リクエスト")}</b>'
                f'<span>締切なし・いつでも申し込める招待制販売</span><span class="go">Amazonで申し込む</span></a>')

    def prerender(sub):
        if not sub:
            return '<div class="empty">いま掲載している情報はありません。新しい受付が見つかり次第、自動で追加されます。</div>'
        rows = []
        for i in sorted(sub, key=lambda x: (x["ph"] == "ended", x.get("end") or x.get("start") or "9999"))[:120]:
            when = f'<time datetime="{escape(i["end"])}">{_fmt(i["end"])}</time>' if i.get("end") else "日時は告知で確認"
            rows.append(f'<li><b>{escape(PH_LABEL.get(i["ph"], ""))}</b> {escape(kinds.get(i["kind"], ""))}｜<a href="/{escape(i["lpath"])}">{escape(i["store"])} {escape(i.get("product") or "")}</a>'
                        f'｜{"締切" if i["kind"] not in ("release", "restock", "first_come") else "日付"} {when}</li>')
        return '<ul class="pre-list">' + "".join(rows) + "</ul>"

    def summary(sub, what):
        op = [i for i in sub if i["ph"] == "open"]
        if not op:
            return f"現在受付中の{what}はありません。予告・発売日の情報があれば上のタブに出ます。新しい受付が見つかり次第、自動で追加されます。"
        soon = sorted([i for i in op if i.get("end")], key=lambda i: i["end"])
        txt = f"現在受付中の{what}は{len(op)}件です。"
        if soon:
            i = soon[0]
            txt += f"いちばん締切が近いのは{escape(i['store'])}の「{escape(i.get('series') or i.get('product') or '')}」で、{_fmt(i['end'])}締切です。"
        kc = {}
        for i in op:
            kc[kinds.get(i["kind"], i["kind"])] = kc.get(kinds.get(i["kind"], i["kind"]), 0) + 1
        txt += "種類は" + "・".join(f"{k}{v}件" for k, v in sorted(kc.items(), key=lambda x: -x[1])) + "。"
        return txt

    def crumbs(trail):
        html = '<nav class="crumbs" aria-label="パンくず">' + " › ".join(
            (f'<a href="/{escape(p)}">{escape(n)}</a>' if k < len(trail) - 1 else f"<span>{escape(n)}</span>") for k, (n, p) in enumerate(trail)) + "</nav>"
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": k + 1, "name": n, "item": f"{site}/{p}"} for k, (n, p) in enumerate(trail)]}
        return html, ld

    def faq_html(qa):
        if not qa:
            return "", None
        h = '<section class="faq sec"><h2>よくある質問</h2>' + "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in qa) + "</section>"
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
        return h, ld

    def links_html(pairs):
        return "".join(f'<a href="/{escape(p)}">{escape(n)}</a>' for n, p in pairs)

    def write(path, meta, sub, trail=None, data_extra=None, body_top="", body_bottom="", noindex=False, list_mode=True, ld_extra=(), cur=None):
        p = out / path / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        canon = f"{site}/{path}" if site else ""
        ld = list(ld_extra)
        cr = ""
        if trail:
            cr, bl = crumbs(trail)
            ld.insert(0, bl)
        fh, fl = faq_html(meta.get("faq") or [])
        if fl:
            ld.append(fl)
        ld.append({"@context": "https://schema.org", "@type": "WebPage", "name": meta["title"], "description": meta["desc"], "url": canon or None, "inLanguage": "ja",
                   "dateModified": updated, "publisher": {"@type": "Organization", "name": brand["name"], "url": f"{site}/"}})
        if not path:
            ld.insert(0, {"@context": "https://schema.org", "@type": "WebSite", "name": brand["name"], "url": f"{site}/", "inLanguage": "ja"})
        og = meta.get("og") or (f"{site}/og.png" if site else "/og.png")
        head = []
        if canon:
            head += [f'<link rel="canonical" href="{escape(canon)}">', f'<meta property="og:url" content="{escape(canon)}">']
        head += [f'<meta property="og:title" content="{escape(meta["title"])}">', f'<meta property="og:description" content="{escape(meta["desc"])}">',
                 '<meta property="og:type" content="website">', f'<meta property="og:site_name" content="{escape(brand["name"])}">', '<meta property="og:locale" content="ja_JP">',
                 f'<meta property="og:image" content="{escape(og)}">', '<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:image" content="{escape(og)}">',
                 f'<meta name="theme-color" content="{BG}">', '<link rel="icon" href="/favicon.svg" type="image/svg+xml">', '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
                 '<meta name="robots" content="noindex,follow">' if noindex else '<meta name="robots" content="index,follow,max-image-preview:large">']
        if verify:
            head.append(f'<meta name="google-site-verification" content="{escape(verify)}">')
        for x in ld:
            head.append('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>")
        data = dict(common_data, items=[{k: v for k, v in i.items() if v not in (None, "", []) and k not in ("ph", "manual", "products")} for i in sub],
                    page=dict({"list": list_mode, "top": not path}, **(data_extra or {})))
        body = tpl
        for k, v in {"__TITLE__": escape(meta["title"]), "__DESC__": escape(meta["desc"]), "__HEADMETA__": "\n".join(head), "__CRUMBS__": cr,
                     "__H1__": escape(meta["h1"]), "__UPDATED__": escape(f"更新 {_fmt(updated)}"), "__SUMSHORT__": escape(meta.get("sumshort") or ""),
                     "__PIN__": meta.get("pin", ""), "__BODY_TOP__": body_top, "__PRERENDER__": prerender(sub) if list_mode else "", "__BODY_BOTTOM__": body_bottom,
                     "__FAQ__": fh, "__LEAD__": escape(meta.get("lead") or ""), "__SUMMARY__": meta.get("summary") or "", "__LINKS__": meta.get("links", ""),
                     "__CREDIT__": CREDIT if any((i.get("rk") or {}).get("img") for i in sub) else "",
                     "__SHELL_CSS__": shell_css, "__SIDEBAR__": side_html(cats, (data_extra or {}).get("game"), cur), "__SEARCH__": SEARCH_FORM}.items():
            body = body.replace(k, v)
        body = body.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
        cut = body.index('<div class="shell">')
        html = ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                f'{body[:cut]}</head><body>{body[cut:]}</body></html>')
        p.write_text(html, encoding="utf-8")
        if site and not noindex:
            fp = sha(re.sub(r"更新 \d+/\d+\([月火水木金土日]\) \d\d:\d\d", "", html))
            prev = pmod.get(path)
            lm = today_iso if not prev or prev[0] != fp else prev[1]
            pmod[path] = [fp, lm, (prev or [None, None, today_iso])[2]]
            urls.append((f"{site}/{path}", lm))

    menu = [("すべて", "chusen/"), ("いま一覧", "now/"), ("今日", "today/"), ("カレンダー", "calendar/")] + [(c["short"], f"{c['slug']}/") for c in cats] + [("見方・使い方", "guide/")]
    lk = links_html(menu)
    cat_counts = {c["id"]: sum(1 for i in live if i["game"] == c["id"] and i["ph"] == "open") for c in cats}

    # --- お店（チェーン）ごとのページ /chain/<店>/（11/10 トレカ抽選ナビを参考に：「ヨドバシ 抽選」「ゲオ 予約」などで探す人のため）---
    chains = {}
    for i in items:
        c_ = sg.chain_of(i.get("store"))
        if c_:
            chains.setdefault(c_, []).append(i)
    chain_links = ('<section class="sec"><h2>お店ごとの抽選・予約・再販</h2><div class="links">' + "".join(
        f'<a href="/chain/{c_}/">{escape(sg.CHAIN[c_][1])}<small>{sum(1 for j in lst if j["ph"] == "open")}件</small></a>'
        for c_, lst in sorted(chains.items(), key=lambda kv: -len(kv[1]))) + "</div></section>") if chains else ""
    for c_, lst in chains.items():
        cname = sg.CHAIN[c_][1]
        no = sum(1 for i in lst if i["ph"] == "open")
        cats_in = list(dict.fromkeys(cat_by[i["game"]]["short"] for i in lst if i["game"] in cat_by))
        faq_c = [(f"{cname}のゲーム・ホビーの抽選・予約はいつありますか？",
                  (f"いま受付中は{no}件です（" + "・".join(cats_in[:6]) + "）。" if no else "いま受付中のものはありません。") + "新しい抽選・予約・再販が見つかると、このページに自動で追加します。"),
                 (f"{cname}の抽選の応募条件は？", "会員登録・アプリ・本人確認・購入履歴などの条件を、告知から読み取ってタグで表示しています。応募前に必ず公式の応募ページで確認してください。")]
        write(f"chain/{c_}/", {"title": f"{cname}のゲーム・ホビー抽選・予約・再販情報【{md}更新】受付中{no}件｜{brand['name']}",
                                "desc": f"{cname}のPS5・Switch 2・ガンプラ・ポケカなどの抽選・予約・再販の受付情報。締切・応募条件・応募ページへのリンクをまとめて毎日更新。いま受付中{no}件。",
                                "h1": f"{cname}の抽選・予約・再販", "sumshort": f"いま受付中{no}件。締切が近い順です。", "lead": "・".join(cats_in[:8]),
                                "summary": summary(lst, f"{cname}の受付"), "links": lk, "faq": faq_c}, lst,
              trail=[("トップ", ""), ("抽選・受付中", "chusen/"), (cname, f"chain/{c_}/")], data_extra={"game": ""}, body_bottom=chain_links,
              noindex=len(lst) < 3)   # 1〜2件だけのお店のページは中身が薄いので検索には出さない（11/9 監査と同じ考え方）

    # --- トップ ---
    n_open = sum(1 for i in live if i["ph"] == "open")
    top_faq = [("このサイトは何のサイトですか？", f"{brand['name']}は、PS5・Switch 2などのゲーム機と、ガンプラ・フィギュア・一番くじなどのホビーについて、楽天・Amazonなどで定価で売り出された（再販・入荷・予約開始）ことをXで速報し、買取店の新品の買取相場・定価以上で売れる商品・発売予定を毎日まとめているサイトです。抽選・招待・先着の受付情報も各店の告知から自動で集めています。"),
               ("受付状況はいつの時点のものですか？", "ページを開いた時刻でブラウザが計算しています。受付中・予告・終了と残り時間は、開くたびに今の時刻で表示されます。"),
               ("どんな条件があるか分かりますか？", "会員・アプリ・本人確認・購入履歴・プレイ時間・PSN必須・NSO加入・1人1台などの条件を、告知から読み取ってタグで表示しています。必ず応募ページの原文でご確認ください。")]
    # 11/9 ユーザーの指示：サイトのトップ（/）は「プレミア商品一覧」（game_premium が書く）。抽選・受付中の一覧は /chusen/ へ
    write("chusen/", {"title": f"ゲーム・ホビーの抽選・予約・受付中の一覧【{md}更新】締切が近い順｜{brand['name']}",
               "desc": f"PS5・Switch 2・たまごっち・ガンプラ・フィギュアなどの再販・入荷・予約開始を速報。楽天・Amazonで定価で売り出されたらXで通知。買取店{_n_stores()}店の買取相場と、定価以上で売れる商品の一覧も毎日更新。いま受付中の抽選・予約{n_open}件。",
               "h1": "ゲーム・ホビーの抽選・予約・受付中の一覧", "sumshort": f"いま受付中{n_open}件。締切が近い順に、条件つきで並べています。",
               "lead": s.get("site_tagline") or "", "summary": summary(live, "受付"), "links": lk, "faq": top_faq, "pin": pin_html()}, items,
          trail=None, data_extra={"game": ""}, body_bottom=chain_links)

    # --- /now/ お店 × 商品 ---
    write("now/", {"title": f"いま買える？お店×商品の受付状況一覧【{md}更新】｜{brand['name']}",
                   "desc": "PS5・Switch 2・ガンプラなどを、お店ごと・商品ごとに「受付中・予告・結果待ち・再入荷」で一覧にした表。どこで何が動いているかが一目で分かります。",
                   "h1": "いま、どのお店で何が動いているか", "sumshort": "お店×商品の表。色が付いているところが、いま受付中・予告のものです。",
                   "lead": "受付中（緑）・まもなく締切（赤）・予告と発売日（水色）・結果待ち（灰）。表はページを開いた時刻で作っています。", "summary": summary(live, "受付"), "links": lk},
          live, trail=[("トップ", ""), ("いま一覧", "now/")], body_top='<div id="matrix" class="sec"></div>', list_mode=False, data_extra={"list": False})

    # --- /today/ ---
    td = [i for i in live if (parse_dt(i.get("end")) and parse_dt(i["end"]).date() == t.date()) or (parse_dt(i.get("start")) and parse_dt(i["start"]).date() == t.date())]
    write("today/", {"title": f"今日締切・今日開始の抽選・予約【{t.month}/{t.day}】｜{brand['name']}",
                     "desc": f"{t.month}/{t.day}に締切または受付開始となるゲーム機・ホビーの抽選・予約・先着を一覧に。残り時間つき。",
                     "h1": f"今日（{t.month}/{t.day}）締切・開始のもの", "sumshort": f"今日が締切・開始のものは{len(td)}件です。", "lead": "今日中に動くものだけを並べています。",
                     "summary": summary(td, "今日締切・開始の受付"), "links": lk}, td, trail=[("トップ", ""), ("今日", "today/")])

    # --- /calendar/ 予約開始・発売日・再販日 ---
    ev = []
    for i in live:
        if i["kind"] == "release" and i.get("end"):
            ev.append((i["end"][:10], "発売・再販", i))
        if i["kind"] in ("preorder", "lottery", "fukubukuro", "first_come") and i.get("start") and parse_dt(i["start"]) >= t.replace(hour=0, minute=0):
            ev.append((i["start"][:10], f"{kinds.get(i['kind'], '')}開始", i))
    ev.sort(key=lambda x: x[0])
    cal_html = ('<ul class="cal sec">' + "".join(
        f'<li><b>{escape(_fmt(d + "T00:00").split(" ")[0])}</b><div><span class="k">{escape(lab)}</span><a href="/{escape(i["lpath"])}">{escape(i["store"])} {escape(i.get("product") or "")}</a>'
        f'<small>{escape(cat_by[i["game"]]["short"])}{"・定価 " + escape(i["price"]) if i.get("price") else ""}</small></div></li>' for d, lab, i in ev) + "</ul>") if ev else \
        '<div class="empty">予定されている予約開始・発売日はまだありません。見つかり次第ここに載ります。</div>'
    evs_ = [e_ for e_ in (detail.cal_event(i, i.get("store") or "", detail.short_name(i), f"{site}/{i['lpath']}" if site else "", domain=brand["domain"])
                          for i in live if i["ph"] in ("open", "upcoming") and i.get("end")) if e_]
    (out / "cal").mkdir(parents=True, exist_ok=True)
    (out / "cal" / "shimekiri.ics").write_text(detail.ics_wrap(evs_, cal_name=f"抽選・予約の締切（{brand['name']}）"), encoding="utf-8")
    sub_html = ('<section class="sec" id="sub"><h2>これからの締切を自動でカレンダーに入れる</h2><p class="lead-sum">一度登録すると、受付中・予告の締切（1時間前〜締切）が自動で入ります。'
                f'</p><div class="links"><a href="webcal://{escape(brand["domain"])}/cal/shimekiri.ics">iPhone・Macのカレンダー</a>'
                f'<a href="https://calendar.google.com/calendar/r?cid={escape("webcal://" + brand["domain"] + "/cal/shimekiri.ics")}" target="_blank" rel="noopener">Googleカレンダー</a></div></section>')
    cal_html += sub_html
    write("calendar/", {"title": f"予約開始・発売日・再販日カレンダー【{md}更新】｜{brand['name']}",
                        "desc": "PS5・Switch 2・ガンプラ・フィギュア・一番くじなどの予約開始日、発売日、再販日を日付順に。メーカー発表と各店の受付開始をまとめています。",
                        "h1": "予約開始・発売日・再販日カレンダー", "sumshort": f"これからの予定 {len(ev)}件。", "lead": "日付はメーカー・各店の発表から読み取ったものです。変わることがあります。",
                        "summary": "予約開始・発売日・再販日を日付順に並べています。" if ev else "予定はまだありません。", "links": lk},
          [], trail=[("トップ", ""), ("カレンダー", "calendar/")], body_top=cal_html, list_mode=False, data_extra={"list": False}, cur="calendar")

    # --- カテゴリページ・モデルページ・お店×カテゴリ ---
    for c in cats:
        g = c["id"]
        sub = [i for i in items if i["game"] == g]
        n = cat_counts[g]
        og_p = out / c["slug"] / "og.png"
        try:
            sg.og_image(og_p, c["short"], c.get("color") or "#1b3a5c", f"{c['short']}の抽選・予約・再入荷",
                        [("受付中", f"{n}件", True), ("更新", md, False)], sub=s.get("site_tagline") or "", brand=(brand["name"], brand["domain"]))
            og_u = f"{site}/{c['slug']}/og.png"
        except Exception:
            og_u = None
        sers = {}
        for i in sub:
            if i.get("series"):
                sers.setdefault(i["series"], []).append(i)
        ser_links = '<section class="sec"><h2>機種・モデルごと</h2><div class="links">' + "".join(
            f'<a href="/{escape(i[0]["spath"])}">{escape(x)}<small>{sum(1 for j in i if j["ph"] == "open")}件</small></a>' for x, i in sorted(sers.items(), key=lambda kv: -len(kv[1]))) + "</div></section>" if sers else ""
        faq = [(f"{c['short']}の{'抽選' if 'lottery' in c['kinds'] else '予約'}はどこで受け付けていますか？",
                ("いま受付中は" + "・".join(dict.fromkeys(i["store"] for i in sub if i["ph"] == "open")) + f"（{n}件）です。" if n else "いま受付中のものはありません。") + "一覧は締切が近い順です。"),
               ("どんな条件がありますか？", "会員登録・アプリ・本人確認・購入履歴・プレイ時間・PSN必須・NSO加入・1人1台など、告知から読み取った条件をタグで表示しています。応募前に公式ページで必ずご確認ください。")]
        npd = len(pidx.get(g, []))
        write(f"{c['slug']}/", {"title": f"{c['short']} 商品一覧・定価・買取相場と発売・再販情報【{md}更新】｜{brand['name']}",
                                 "desc": (f"{c['name']}の商品{npd}件の最高買取価格（買取相場）と、" if npd else f"{c['name']}の") + "発売・予約・再販・抽選の情報。楽天・Amazonで売り出されたらXで通知します。",
                                 "h1": f"{c['short']}の商品一覧と発売・再販情報", "sumshort": (f"いま受付中{n}件。弾ごとにまとめています。" if c.get("sets") else f"商品{npd}件・いま受付中{n}件。"), "lead": c["name"], "summary": summary(sub, f"{c['short']}の受付"),
                                 "links": lk, "faq": faq, "og": og_u}, sub, trail=[("トップ", ""), (c["short"], f"{c['slug']}/")], data_extra={"game": g},
              body_top=_notice_html(c.get("notice")) + (_sets_html(c, sub) if c.get("sets") else   # ポケカ・ワンピは弾ごとのまとめ（11/14）
                       f"<style>{game_premium.CSS}</style>" + game_premium.cat_products_html(pidx.get(g, []), c["short"], c.get("subgenres"), has_list=bool(sub))),
              body_bottom=ser_links, noindex=(npd == 0 and not sub))   # 商品も受付も0件の一覧は検索に出さない（11/14 Fable）
        _prev_pages = load_json("lottery_pages.json", {}) or {}
        _hubs = {h["path"]: h for h in _hubs_cfg() if h.get("game") == g}
        _hub_done = set()
        for x, lst in sers.items():
            path = lst[0]["spath"]
            no = sum(1 for i in lst if i["ph"] == "open")
            # 11/14 ユーザー：1ページあたりのボリュームを増やす → これまでの受付の記録・買取相場・データから作るよくある質問
            _xb, _xf = _series_extra(x, path, lst, _prev_pages, s)
            if path in _hubs:   # モデルの常設まとめと同じページ：当てはまる商品の買取相場・記録も足す
                _hb, _hf, _, _ = _hub_extra(_hubs[path], _prev_pages, {i.get("key") for i in lst}, s)
                _xb, _xf = _xb + _hb, _xf + _hf
                _hub_done.add(path)
            write(path, {"title": f"{x} 抽選・予約・再入荷情報まとめ【{md}更新】｜{brand['name']}",
                         "desc": f"{x}（{c['short']}）の抽選・予約・再入荷の受付情報。いま受付中{no}件。各店の締切・条件・定価をまとめています。",
                         "h1": f"{x}の抽選・予約・再入荷", "sumshort": f"いま受付中{no}件。", "lead": f"{c['name']}のうち「{x}」の情報だけを並べています。",
                         "summary": summary(lst, f"「{x}」の受付"), "links": lk, "og": og_u,
                         "faq": [(f"{x}はいまどこで買えますか（受付中）？", ("いま受付中は" + "・".join(dict.fromkeys(i["store"] for i in lst if i["ph"] == "open")) + "です。" if no else "いま受付中のものはありません。予告・発売日のタブもご覧ください。"))] + _xf},
                  lst, trail=[("トップ", ""), (c["short"], f"{c['slug']}/"), (x, path)], data_extra={"game": g},
                  body_bottom=(lambda h_: f'<section class="xsec xai"><style>.pm-ai p{{line-height:1.85;color:#cfd5e1}}.pm-ai h2{{font-size:17px;margin:16px 0 6px}}.pm-ai .note{{font-size:12px;color:#8a93a6}}</style>{h_}</section>' if h_ else "")(__import__("game_aitext").html_for("s:" + path)) + _xb)   # AIの解説（11/14 ユーザー：1ページごとの中身も充実）
        # モデルの常設まとめ（受付が終わっても消さない。11/14 ユーザー「A、OK」）
        for path, h in _hubs.items():
            if path in _hub_done:
                continue
            lst = [i for i in sub if _hub_hit(h, f'{i.get("product") or ""} {i.get("series") or ""}')]
            hb, hf, n_p, n_r = _hub_extra(h, _prev_pages, {i.get("key") for i in lst}, s)
            if not lst and n_p < 2 and n_r < 1:   # 中身が無いページは作らない
                continue
            no = sum(1 for i in lst if i["ph"] == "open")
            nm = h["name"]
            write(path, {"title": f"{nm} 抽選・予約・再販・在庫情報まとめ【{md}更新】｜{brand['name']}",
                         "desc": f"{nm}の抽選・予約・再販・在庫の情報と、商品ごとの買取相場。いま受付中{no}件・商品{n_p}件・これまでの受付{n_r}件。販売開始はXで通知。",
                         "h1": f"{nm}の抽選・予約・再販・在庫", "sumshort": f"いま受付中{no}件。", "lead": f"{c['name']}のうち「{nm}」の受付・販売・買取相場をまとめています。",
                         "summary": summary(lst, f"「{nm}」の受付") if lst else f"いま受付中の{nm}の抽選・予約はありません。下の商品の販売状況とこれまでの記録をご覧ください。",
                         "links": lk, "og": og_u,
                         "faq": [(f"{nm}はいまどこで買えますか（受付中）？", ("いま受付中は" + "・".join(dict.fromkeys(i["store"] for i in lst if i["ph"] == "open")) + "です。") if no else "いま受付中の抽選・予約はありません。再販・入荷はXでお知らせします。")] + hf},
                  lst, trail=[("トップ", ""), (c["short"], f"{c['slug']}/"), (nm, path)], data_extra={"game": g}, body_bottom=hb)
        by_chain = {}
        for i in sub:
            if i.get("chain"):
                by_chain.setdefault(i["chain"], []).append(i)
        for ch, lst in by_chain.items():
            cname = CHAIN[ch][1]
            path = f"chain/{ch}/{c['slug']}/"
            no = sum(1 for i in lst if i["ph"] == "open")
            write(path, {"title": f"{cname}の{c['short']} 抽選・予約・再入荷【{md}更新】｜{brand['name']}",
                         "desc": f"{cname}で受け付けている{c['short']}の抽選・予約・再入荷の情報。いま受付中{no}件。締切・条件つき。",
                         "h1": f"{cname}の{c['short']}", "sumshort": f"いま受付中{no}件。", "lead": f"{cname}の{c['name']}に関する受付だけを並べています。",
                         "summary": summary(lst, f"{cname}の{c['short']}の受付"), "links": lk, "og": og_u},
                  lst, trail=[("トップ", ""), (c["short"], f"{c['slug']}/"), (cname, path)], data_extra={"game": g},
                  noindex=len(lst) < 3)   # お店×カテゴリで受付が3件未満の薄いページは検索に出さない（11/14 Fable）

    # --- 個別ページ /l/<id>/（終了しても KEEP 日はページを残す）---
    pages = load_json("lottery_pages.json", {})
    games_map = {c["id"]: (c["short"], c["slug"]) for c in cats}
    dbrand = dict(brand, color=BG)  # 個別ページの上のバーの色（ボタンの色は _theme_detail で付け直す）
    for i in items:
        snap = detail.snapshot(i)
        snap["kind"] = i.get("kind") or "lottery"
        if i.get("price"):
            snap["price"] = i["price"]
        if (i.get("rk") or {}).get("img"):   # 写真（押すと楽天の商品ページ）
            snap["image"], snap["img_url"] = i["rk"]["img"], i["rk"]["u"]
        else:
            snap.pop("image", None), snap.pop("img_url", None)
        snap["shop"] = {k: i[k] for k in ("rk", "az", "yh", "mc") if i.get(k)}
        if i.get("facts"):   # 元の記事から取った要点（game_verify。自分の言葉で書き直したもの）と、その記事
            snap["facts"], snap["facts_src"] = i["facts"], i.get("facts_src") or ""
        if i.get("avail"):
            snap["avail"] = i["avail"]
        pages[i["key"]] = {"snap": snap, "path": i["lpath"], "end": i.get("end"), "seen": today_iso}
    for k, rec in list(pages.items()):
        snap = dict(rec["snap"])
        snap.setdefault("kind", "lottery")
        from approve import AD_ITEM as _ADI, AD_HOST as _ADH
        if (raw.get(k) or {}).get("status") in ("rejected", "duplicate") or _ADI.search(snap.get("product") or "") or _ADH.search(snap.get("url") or ""):
            del pages[k]   # 外した抽選（情報元の広告など）は個別ページも消す（11/14 ユーザー指摘：ポケパ365のページがまだあった）
            continue
        e = parse_dt(snap.get("end"))
        ended = rec.get("ended") or (e is not None and e < t) or (k not in {i["key"] for i in items} and (t - (parse_dt(rec.get("seen") + "T00:00") or t)).days >= 1)
        if ended and (t - (parse_dt(rec.get("seen") + "T00:00") or t)).days > 45:
            del pages[k]
            continue
        rec["ended"] = bool(ended)
        g = snap.get("game")
        if g not in games_map:
            continue
        rel = [(f"{cat_by[g]['short']}の一覧", f"/{cat_by[g]['slug']}/"), ("いま一覧（お店×商品）", "/now/"), ("今日締切・開始", "/today/")]
        if snap.get("spath"):
            rel.insert(0, (f"「{snap.get('series')}」の一覧", f"/{snap['spath']}"))
        nxt = (f"いま受付中の{cat_by[g]['short']}を見る", f"/{cat_by[g]['slug']}/") if ended else None
        html = detail.render(snap, site=site, path=rec["path"], verify=verify, now_dt=t, ended=ended, related=rel, updated=updated,
                             next_link=nxt, brand=dbrand, games=games_map)
        html = _theme_detail(_shop_detail(_release_detail(html, snap), snap), side_html(cats, g, counts=False))
        try:
            html = _extra_detail(html, snap, k, pages, live, cat_by, s, t)
        except Exception as e:
            log(f"個別ページの中身を足す: スキップ {k} {e}")
        if cat_by[g].get("notice"):   # お酒の「20歳になってから」など、カテゴリの注意書き（h1 のすぐ下）
            html = re.sub(r"(</h1>)", lambda m: m.group(1) + _notice_html(cat_by[g]["notice"]), html, count=1)
        p = out / rec["path"] / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        if not ended:  # 「iPhone・スマホ」のカレンダーのボタン用（締切の1時間前〜締切の予定）
            ev_ = detail.cal_event(snap, snap.get("store") or "", detail.short_name(snap), f"{site}/{rec['path']}" if site else "", domain=brand["domain"])
            if ev_:
                (p.parent / "shimekiri.ics").write_text(detail.ics_wrap([ev_]), encoding="utf-8")
        if site and not ended:
            fp = sha(re.sub(r"情報の更新：\d+/\d+ \d\d:\d\d", "", html))
            prev = pmod.get(rec["path"])
            lm = today_iso if not prev or prev[0] != fp else prev[1]
            pmod[rec["path"]] = [fp, lm, (prev or [None, None, today_iso])[2]]
            urls.append((f"{site}/{rec['path']}", lm))
    save_json("lottery_pages.json", pages)

    # --- ガイド ---
    import yaml
    gp = ROOT / "config" / "game" / "guides.yaml"
    guides = ((yaml.safe_load(gp.read_text(encoding="utf-8")) or {}).get("guides") or []) if gp.exists() else []
    gl = '<section class="sec"><h2>解説</h2><div class="links">' + "".join(f'<a href="/guide/{escape(g["slug"])}/">{escape(g.get("short") or g["h1"])}</a>' for g in guides) + "</div></section>" if guides else ""
    write("guide/", {"title": f"抽選・予約・再入荷の見方と使い方｜{brand['name']}", "desc": "抽選・招待・予約・再入荷・先着のちがい、受付状況の見方、申し込む前に確かめることをまとめています。",
                     "h1": "このサイトの見方・使い方", "sumshort": "種類と受付状況の意味、申し込む前に確かめること。", "lead": "定価で買える機会を見つけるためのサイトです。", "summary": "解説ページの一覧です。", "links": lk},
          [], trail=[("トップ", ""), ("見方・使い方", "guide/")], body_top=gl, list_mode=False, data_extra={"list": False})
    for gd in guides:
        rx = re.compile(gd["store_re"], re.I)
        sub = [i for i in live if rx.search(i.get("store") or "")]
        body = f'<article class="guide"><p>{gd["intro"]}</p>' + "".join(f'<h2>{escape(sec["h"])}</h2>{sec["html"]}' for sec in gd.get("sections") or [])
        if gd.get("sources"):
            body += '<p class="note">参考：' + "・".join(f'<a href="{escape(u)}" target="_blank" rel="noopener nofollow">{escape(tt)}</a>' for tt, u in gd["sources"]) + "</p>"
        body += "</article>"
        write(f"guide/{gd['slug']}/", {"title": f"{gd['title']}｜{brand['name']}", "desc": gd["desc"], "h1": gd["h1"], "sumshort": gd.get("short") or "", "lead": gd.get("intro") or "",
                                       "summary": summary(sub, gd["name"] + "の受付") if sub else "", "links": lk, "faq": [tuple(q) for q in gd.get("faq") or []]},
              sub, trail=[("トップ", ""), ("見方・使い方", "guide/"), (gd["name"], f"guide/{gd['slug']}/")], body_top=body, list_mode=bool(sub))

    # --- そのほか ---
    (out / "privacy.html").write_text(_simple_page(cats, _privacy(s)), encoding="utf-8")
    (out / "404.html").write_text(_simple_page(cats, (
        f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
        f'<title>ページが見つかりません｜{escape(brand["name"])}</title></head>'
        '<body><img src="/rinrin.png" alt="" width="96" height="96"><h1>ページが見つかりません</h1><p>受付が終わってページを削除した可能性があります。</p>'
        '<p><a href="/premium/">プレミア商品一覧</a> ・ <a href="/chusen/">受付中の一覧</a> ・ <a href="/now/">いま一覧</a> ・ <a href="/calendar/">カレンダー</a></p></body></html>')), encoding="utf-8")
    _x_draft(out, live, s, site, updated, cats)
    try:   # 定価以上で売れる商品（買取店の新品の買取価格×楽天の定価）：/premium/ と /premium/<JAN>/
        import game_premium
        import game_affi as _ga
        pm_paths, _ = game_premium.write_pages(out, cats, site, brand, live, s, _simple_page, _ga.affiliate_id(s))
        for pth, fp in pm_paths:   # 更新日は中身（価格など）が変わった日だけ（毎回「今日」だとGoogleが日付を信用しなくなる）
            prev = pmod.get(pth)
            lm = today_iso if not prev or prev[0] != fp else prev[1]
            pmod[pth] = [fp, lm, (prev or [None, None, today_iso])[2]]
            urls.append((f"{site}/{pth}", lm))
    except Exception as e:
        log(f"プレ値商品のページ: スキップ {e}")
    try:   # トップ（11/14 ユーザー：開いたら「いま買える・いま応募できる」が分かるページに。プレミア商品一覧は /premium/ へ）
        import game_premium
        _allx = game_premium.catalog(s, game_premium.watch_map_cached())
        _cnt = {g_: sum(1 for i in live if i["game"] == g_) + len(pidx.get(g_, [])) for g_ in {c["id"] for c in cats}}
        _bt, _bb = _top_blocks(_allx, game_premium.watch_map_cached(), cats, _cnt, s)
        _soon = sorted([i for i in live if i["ph"] in ("open", "upcoming")], key=lambda i: (i["ph"] != "open", i.get("end") or "9999"))[:40]
        write("", {"title": f"ゲーム・ホビー入荷速報｜PS5・Switch 2・ポケカの再販・抽選と定価以上で売れるプレミア商品【{md}更新】",
                   "desc": f"楽天・Amazonで定価販売・予約が始まった商品をすぐお知らせ。締切が近いPS5・Switch 2・ポケカ・ガンプラの抽選・予約（受付中{n_open}件）と、定価より高く売れるプレミア商品のランキングを毎日更新。",
                   "h1": "いま買える・いま応募できるゲームとホビー", "sumshort": f"定価販売の速報・締切が近い抽選・定価より高く売れる商品をまとめています（受付中{n_open}件）。",
                   "lead": s.get("site_tagline") or "", "summary": summary(live, "受付"), "links": lk, "faq": top_faq, "pin": pin_html()},
              _soon, trail=None, data_extra={"game": ""}, body_top=_bt, body_bottom=_bb)
    except Exception as e:
        log(f"トップ: スキップ {e}")
    try:   # ページごとの中身の量を測る（次の回の解説文づくりが、少ないページから順に使う）
        import game_volume
        game_volume.measure(out, int(s.get("content_target_chars", 1500)))
    except Exception as e:
        log(f"ページの中身の測定: スキップ {e}")
    (out / "favicon.svg").write_text(_favicon_svg(brand["color"], s.get("accent_color") or "#0f8b8d"), encoding="utf-8")
    _icon_png(out / "apple-touch-icon.png", brand["color"], 180)
    _icon_png(out / "icon-192.png", brand["color"], 192)
    _og_default(out / "og.png", s, brand)
    static = ROOT / "src" / "static_game"
    if static.exists():
        import shutil
        for f in static.glob("*"):
            shutil.copy(f, out / f.name)
    if s.get("indexnow_key"):
        (out / f"{s['indexnow_key']}.txt").write_text(s["indexnow_key"], encoding="utf-8")
    (out / "_redirects").write_text(_gone_redirects(out, pmod), encoding="utf-8")   # 「定価以上で売れる」は 11/14 に /premium/ に戻した（トップは「いま買える」ページ）
    (out / "_headers").write_text("/og.png\n  Cache-Control: public, max-age=3600\n", encoding="utf-8")
    if site:
        (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                         + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u, lm in dict(urls).items()) + "</urlset>\n", encoding="utf-8")
        _write_x_queue(out, items, site)
        (out / "robots.txt").write_text("".join(f"User-agent: {b}\nAllow: /\nDisallow: /x-draft.html\nDisallow: /x-plan.html\nDisallow: /x-plan.json\nDisallow: /watch.json\nDisallow: /content-report.html\nDisallow: /x-queue.json\n\n" for b in ("Googlebot", "Bingbot", "*")) + f"Sitemap: {site}/sitemap.xml\n", encoding="utf-8")
        L = [f"# {brand['name']}", "", f"> {s.get('site_tagline') or ''}。PS5・Switch 2などのゲーム機と、ガンプラ・フィギュア・一番くじなどのホビーの抽選・招待・予約・再入荷・先着の受付情報を自動で集めて1日6回更新。いま受付中{n_open}件。フリマ・転売の出品価格は載せません（ゲーム機など一部の商品だけ、スニダンの取引の相場を目安として載せています）。",
             "", "## 主なページ", f"- [トップ]({site}/)", f"- [いま一覧（お店×商品）]({site}/now/)", f"- [今日締切・開始]({site}/today/)", f"- [カレンダー]({site}/calendar/)", f"- [見方・使い方]({site}/guide/)", ""]
        L += [f"- [{c['short']}]({site}/{c['slug']}/)" for c in cats]
        (out / "llms.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    sg.inject_ga(out, os.environ.get("GA_ID_GAME") or s.get("ga_id"))
    save_json("site_meta.json", {"digest": digest, "updated": updated})
    save_json("page_lastmod.json", pmod)
    (out / ".changed").unlink(missing_ok=True)
    if changed or force:
        (out / ".changed").write_text(updated, encoding="utf-8")
    log(f"ゲームサイト: {len(urls)}ページ → {out}")
    return out
