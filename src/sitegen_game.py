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


def side_html(cats, cur_game=None, cur=None, counts=True):
    """左のメニュー（ロゴ・受付状況・カテゴリ・通知をオン）。スマホでは本文の上に横並びで出る"""
    stat = "".join(f'<a href="/#{k}" data-t="{k}">{n}<span class="n" data-n="{k}"></span></a>' for k, n in STAT_NAV)
    here = ' aria-current="page"'
    stat += f'<a href="/calendar/"{here if cur == "calendar" else ""}>カレンダー</a>'
    cl = "".join(f'<a href="/{escape(c["slug"])}/"{here if cur_game == c["id"] else ""}>{escape(c["short"])}'
                 + (f'<span class="n" data-cn="{escape(c["id"])}"></span>' if counts else "") + "</a>" for c in cats)
    return ('<aside class="side" aria-label="メニュー">'
            '<a class="brand" href="/"><img src="/rinrin.png" alt="" width="36" height="36"><span>ゲーム・ホビー<br><em>入荷速報</em></span></a>'
            f'<nav class="stat" aria-label="受付状況">{stat}</nav>'
            f'<nav class="cats" aria-label="カテゴリ"><p class="cats-h">カテゴリ</p>{cl}</nav>'
            f'<a class="notify" href="/calendar/#sub"><span>{BELL_SVG}通知をオン</span><small>締切をカレンダーでお知らせ</small></a>'
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
                  lambda m: f'<body><div class="shell">{side}<div class="main"><p class="promo">本ページはプロモーションを含みます</p><main class="wrap">', html, count=1, flags=re.S)
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


def _shop_detail(html, snap):
    """個別ページ：応募ボタンの下に「楽天で見る」「Amazonで見る」、写真に大きさ、下に写真の出どころ（detail.py は変えない）"""
    sh = snap.get("shop") or {}
    b = shop_buttons(sh.get("rk"), sh.get("az"), yh=sh.get("yh", ""), mc=sh.get("mc", ""))
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
sec("朝のまとめ",("【"+(N.getMonth()+1)+"/"+N.getDate()+" いま受付中】\\n"+Object.keys(byc).map(function(g){{return (D.cats[g]||g)+" "+byc[g].length+"件"}}).join(" / ")+"\\n"+open.sort(function(a,b){{return (a.end||"9")>(b.end||"9")?1:-1}}).slice(0,5).map(function(i){{return "・"+i.store+" "+nm(i)+(i.end?"（"+f(i.end)+"まで）":"")}}).join("\\n")+"\\n"+D.site+"/\\n#PS5 #Switch2 #ガンプラ #福袋2027"));
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


def _simple_page(cats, html):
    """404・プライバシーポリシー：本文を左のメニューつきの暗い見た目で包む"""
    css = SHELL_CSS.read_text(encoding="utf-8") + ".doc{max-width:680px;line-height:1.85}.doc h1{font-size:22px;font-weight:900}.doc h2{font-size:16px;margin-top:24px}.doc p{color:var(--ink-2)}"
    html = re.sub(r"<style>.*?</style>", "", html, count=1, flags=re.S)
    html = html.replace("</head>", f'<meta name="theme-color" content="{BG}">{FONTS}<style>{css}</style></head>', 1)
    head, body = html.split("<body>", 1)
    body = body.replace("</body></html>", "")
    return f'{head}<body><div class="shell">{side_html(cats, counts=False)}<main class="main doc">{body}</main></div></body></html>'


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
        row = {k: i.get(k) for k in FIELDS}
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
        items.append(row)
    live = [i for i in items if i["ph"] != "ended"]

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

    cats_js = {c["id"]: {"short": c["short"], "slug": c["slug"], "color": c.get("color") or "#1b3a5c", "group": c["group"]} for c in cats}
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
                     "__SHELL_CSS__": shell_css, "__SIDEBAR__": side_html(cats, (data_extra or {}).get("game"), cur)}.items():
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

    menu = [("すべて", ""), ("いま一覧", "now/"), ("今日", "today/"), ("カレンダー", "calendar/")] + [(c["short"], f"{c['slug']}/") for c in cats] + [("見方・使い方", "guide/")]
    lk = links_html(menu)
    cat_counts = {c["id"]: sum(1 for i in live if i["game"] == c["id"] and i["ph"] == "open") for c in cats}

    # --- トップ ---
    n_open = sum(1 for i in live if i["ph"] == "open")
    top_faq = [("このサイトは何のサイトですか？", f"{brand['name']}は、PS5・Switch 2などのゲーム機と、ガンプラ・フィギュア・一番くじなどのホビーについて、定価で買える「抽選・招待・予約・再入荷・先着・福袋」の受付情報を自動で集めて1日6回更新しているサイトです。フリマ・転売の出品価格は載せません（ゲーム機など一部の商品だけ、スニダンの取引の相場を目安として載せています）。"),
               ("受付状況はいつの時点のものですか？", "ページを開いた時刻でブラウザが計算しています。受付中・予告・終了と残り時間は、開くたびに今の時刻で表示されます。"),
               ("どんな条件があるか分かりますか？", "会員・アプリ・本人確認・購入履歴・プレイ時間・PSN必須・NSO加入・1人1台などの条件を、告知から読み取ってタグで表示しています。必ず応募ページの原文でご確認ください。")]
    write("", {"title": f"ゲーム機・ホビーの抽選・予約・再入荷情報まとめ【{md}更新】｜{brand['name']}",
               "desc": f"PS5 Pro・Switch 2・ガンプラ・フィギュア・一番くじ・福袋などの抽選販売・招待・予約開始・再入荷・先着を、各店の公式告知から自動で集めて1日6回更新。いま受付中{n_open}件。締切までの残り時間・条件（会員・本人確認・プレイ時間など）が一目で分かります。",
               "h1": f"ゲーム機・ホビーの抽選・予約・再入荷 まとめ", "sumshort": f"いま受付中{n_open}件。締切が近い順に、条件つきで並べています。",
               "lead": s.get("site_tagline") or "", "summary": summary(live, "受付"), "links": lk, "faq": top_faq, "pin": pin_html()}, items,
          trail=None, data_extra={"game": ""})

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
        write(f"{c['slug']}/", {"title": f"{c['short']} 抽選・予約・再入荷情報まとめ【{md}更新】｜{brand['name']}",
                                 "desc": f"{c['name']}の抽選販売・招待・予約開始・再入荷・先着の受付情報を各店の公式告知から自動で集めて1日6回更新。いま受付中{n}件。締切までの残り時間と条件が分かります。",
                                 "h1": f"{c['short']}の抽選・予約・再入荷", "sumshort": f"いま受付中{n}件。", "lead": c["name"], "summary": summary(sub, f"{c['short']}の受付"),
                                 "links": lk, "faq": faq, "og": og_u}, sub, trail=[("トップ", ""), (c["short"], f"{c['slug']}/")], data_extra={"game": g}, body_bottom=ser_links)
        for x, lst in sers.items():
            path = lst[0]["spath"]
            no = sum(1 for i in lst if i["ph"] == "open")
            write(path, {"title": f"{x} 抽選・予約・再入荷情報まとめ【{md}更新】｜{brand['name']}",
                         "desc": f"{x}（{c['short']}）の抽選・予約・再入荷の受付情報。いま受付中{no}件。各店の締切・条件・定価をまとめています。",
                         "h1": f"{x}の抽選・予約・再入荷", "sumshort": f"いま受付中{no}件。", "lead": f"{c['name']}のうち「{x}」の情報だけを並べています。",
                         "summary": summary(lst, f"「{x}」の受付"), "links": lk, "og": og_u,
                         "faq": [(f"{x}はいまどこで買えますか（受付中）？", ("いま受付中は" + "・".join(dict.fromkeys(i["store"] for i in lst if i["ph"] == "open")) + "です。" if no else "いま受付中のものはありません。予告・発売日のタブもご覧ください。"))]},
                  lst, trail=[("トップ", ""), (c["short"], f"{c['slug']}/"), (x, path)], data_extra={"game": g})
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
                  lst, trail=[("トップ", ""), (c["short"], f"{c['slug']}/"), (cname, path)], data_extra={"game": g})

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
        pages[i["key"]] = {"snap": snap, "path": i["lpath"], "end": i.get("end"), "seen": today_iso}
    for k, rec in list(pages.items()):
        snap = dict(rec["snap"])
        snap.setdefault("kind", "lottery")
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
        html = _theme_detail(_shop_detail(html, snap), side_html(cats, g, counts=False))
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
        '<p><a href="/">受付中の一覧</a> ・ <a href="/now/">いま一覧</a> ・ <a href="/calendar/">カレンダー</a></p></body></html>')), encoding="utf-8")
    _x_draft(out, live, s, site, updated, cats)
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
    (out / "_headers").write_text("/og.png\n  Cache-Control: public, max-age=3600\n", encoding="utf-8")
    if site:
        (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                         + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u, lm in dict(urls).items()) + "</urlset>\n", encoding="utf-8")
        (out / "robots.txt").write_text("".join(f"User-agent: {b}\nAllow: /\nDisallow: /x-draft.html\nDisallow: /x-plan.html\nDisallow: /x-plan.json\nDisallow: /watch.json\n\n" for b in ("Googlebot", "Bingbot", "*")) + f"Sitemap: {site}/sitemap.xml\n", encoding="utf-8")
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
