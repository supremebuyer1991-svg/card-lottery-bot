"""抽選ごとの個別ページ（/l/<id>/）

・Xのポストやリプ欄に貼るためのページ。1つの抽選の締切・応募方法・条件・対象商品と応募ボタンだけを載せる
・受付状況（受付前／受付中／本日締切／受付終了）はページを開いた時にブラウザで計算する
  （サイトは中身が変わった時しか再公開されないため、書き出した時点の表示のままだと古くなる）
・受付が終わってもURLが切れないよう、state/lottery_pages.json に控えを残して keep_days 日はページを残す
"""
import json
import re
from html import escape
from urllib.parse import quote

from common import parse_dt

WEEK = "月火水木金土日"
GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "フュージョンワールド"}
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}
KEEP = ("key", "game", "store", "product", "products", "series", "start", "end", "announce", "buy", "method",
        "conditions", "tags", "url", "channel", "area", "address", "id_check", "member", "image", "img_url", "spath", "found_at", "manual")


def lottery_path(i) -> str:
    """個別ページのパス。manual.yaml の slug があればそれ、無ければキーの先頭10文字"""
    slug = re.sub(r"[^a-z0-9-]", "", str(i.get("slug") or "").lower()).strip("-")
    return f"l/{slug or (i.get('key') or '')[:10]}/"


def fmt(s, with_time=True):
    dt = parse_dt(s)
    if not dt:
        return None
    t = f"{dt.month}/{dt.day}({WEEK[dt.weekday()]})"
    return f"{t} {dt:%H:%M}" if with_time else t


def short_name(i):
    if i.get("series"):
        return i["series"]
    p = (i.get("product") or "").replace("ワンピカード", "ワンピースカード")
    q = re.search(r"[「『]([^」』]{2,})[」』]", p)
    if q:
        p = q.group(1)
    p = re.sub(r"[（(][^）)]{8,}[）)]", "", p)
    p = re.sub(r"^(ポケモンカードゲーム|ONE PIECEカードゲーム|ドラゴンボール.{0,12}フュージョンワールド)\s*", "", p).strip()
    return p[:24] + "…" if len(p) > 24 else p


CSS = """
:root{--paper:#f3f4f7;--card:#fff;--ink:#161c2e;--ink-2:#545c73;--rule:#dfe2ea;--red:#c8102e;--red-soft:#fbe7ea;
 --amber:#a85d00;--amber-soft:#fff1dc;--done:#2f7a4f;--done-soft:#e3f2e8;--navy-soft:#e6e9f2;
 --font-body:"Zen Kaku Gothic New","Hiragino Sans","Noto Sans JP",sans-serif;--font-num:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#10131c;--card:#181c28;--ink:#eceef5;--ink-2:#a3aac0;--rule:#2a3043;
 --red:#ff5a6e;--red-soft:#3a1820;--amber:#ffb547;--amber-soft:#3a2a12;--done:#5cc78a;--done-soft:#163322;--navy-soft:#232a3d;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#10131c;--card:#181c28;--ink:#eceef5;--ink-2:#a3aac0;--rule:#2a3043;--red:#ff5a6e;--red-soft:#3a1820;
 --amber:#ffb547;--amber-soft:#3a2a12;--done:#5cc78a;--done-soft:#163322;--navy-soft:#232a3d;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.7 var(--font-body)}
.wrap{max-width:720px;margin:0 auto;padding:0 16px}a{color:inherit}
header{background:var(--card);border-bottom:1px solid var(--rule)}header .wrap{padding-block:14px 12px}
.logo{display:inline-flex;flex-direction:column;gap:4px;text-decoration:none}
.logo small{font-family:var(--font-num);font-size:9px;font-weight:600;letter-spacing:.22em;color:var(--ink-2);line-height:1}
.logo .w{display:flex;align-items:center;font-family:"Dela Gothic One","Hiragino Sans",sans-serif;font-size:22px;line-height:1}
.logo .t{margin:0 5px;background:var(--red);color:#fff;padding:5px 11px 6px;border-radius:4px}
.crumbs{font-size:12px;color:var(--ink-2);margin:14px 0 0}.crumbs a{color:var(--ink-2)}
.tk{background:var(--card);border:1px solid var(--rule);border-radius:14px;margin:14px 0;overflow:hidden}
.tk-h{padding:16px 16px 14px;border-bottom:1px dashed var(--rule)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.chip{font-size:12px;font-weight:700;border-radius:999px;padding:2px 10px;background:var(--navy-soft);color:var(--ink)}
.chip.st{background:var(--red);color:#fff}.chip.st.soon{background:var(--amber);color:#fff}.chip.st.pre{background:var(--ink-2)}.chip.st.end{background:var(--rule);color:var(--ink-2)}
h1{font-size:21px;line-height:1.4;margin:0}.store{color:var(--ink-2);font-weight:700;margin:6px 0 0}
.cd{display:flex;align-items:baseline;gap:10px;margin-top:12px;padding:10px 12px;border-radius:10px;background:var(--red-soft)}
.cd b{font-family:var(--font-num);font-size:22px;color:var(--red)}.cd span{font-size:13px;color:var(--ink-2)}
.cd.soon{background:var(--amber-soft)}.cd.soon b{color:var(--amber)}.cd.end{background:var(--navy-soft)}.cd.end b{color:var(--ink-2);font-family:var(--font-body);font-size:17px}
dl{margin:0;padding:6px 16px}dl div{display:grid;grid-template-columns:7em 1fr;gap:10px;padding:10px 0;border-bottom:1px solid var(--rule)}
dl div:last-child{border-bottom:0}dt{color:var(--ink-2);font-size:13px;font-weight:700}dd{margin:0;font-weight:500}
dd ul{margin:0;padding-left:1.1em}dd li{margin:2px 0}
.acts{padding:14px 16px 16px;display:grid;gap:10px;border-top:1px dashed var(--rule)}
.go{display:flex;justify-content:center;align-items:center;gap:8px;background:var(--red);color:#fff;text-decoration:none;font-weight:900;
 font-size:17px;letter-spacing:.04em;padding:14px;border-radius:10px}.go-top{margin-top:12px}.go.off{background:var(--rule);color:var(--ink-2);pointer-events:none}
.sub-acts{display:flex;gap:8px;flex-wrap:wrap}.apb{flex:1;font:inherit;font-weight:700;font-size:14px;border:1px solid var(--rule);border-radius:10px;padding:9px;background:#fff;cursor:pointer}.apb.on{color:#15803d;border-color:#15803d}.mlk{display:block;text-align:center;font-size:13px;margin-top:8px}.sub-acts a{flex:1;text-align:center;border:1px solid var(--rule);border-radius:10px;padding:9px;text-decoration:none;font-weight:700;font-size:14px}
.note{font-size:12px;color:var(--ink-2);margin:0}
.ended{background:var(--navy-soft);border-radius:10px;padding:12px 14px;margin:14px 0 0;font-weight:700}
.more{background:var(--card);border:1px solid var(--rule);border-radius:14px;padding:14px 16px;margin:14px 0}
.more h2{font-size:15px;margin:0 0 8px}.more a{display:block;padding:8px 0;border-bottom:1px solid var(--rule);text-decoration:none;font-weight:700}
.more a:last-child{border-bottom:0}.more a::after{content:" →";color:var(--red)}
footer{color:var(--ink-2);font-size:12px;padding:8px 0 40px}
.ad{background:var(--card);border:1px solid var(--rule);border-radius:14px;padding:12px 14px;margin:14px 0}
.ad-top{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--ink-2);margin-bottom:8px}.ad-pr{border:1px solid var(--rule);border-radius:4px;padding:0 5px;font-size:10px}
.ad-main{display:flex;gap:12px;align-items:center}.ad-img img{width:84px;height:84px;object-fit:contain;border-radius:8px;background:#fff}
.ad-info{display:grid;gap:4px}.ad-info small{color:var(--ink-2)}.ad-btns,.ad-sup>div,.ad-amz{display:flex;flex-wrap:wrap;gap:6px}
.ad-btns a,.ad-sup a,.ad-amz a{border:1px solid var(--rule);border-radius:8px;padding:6px 10px;text-decoration:none;font-size:13px;font-weight:700;display:inline-flex;align-items:center;gap:4px}
.b-rak{background:#bf0000;color:#fff!important;border-color:#bf0000!important}.b-amz{background:#ffd814;color:#0f1111!important;border-color:#fcd200!important}
.ad-sup p{font-size:12px;color:var(--ink-2);margin:10px 0 6px}.ad-sup strong{font-family:var(--font-num)}.ad-note{font-size:11px;color:var(--ink-2)}
.ad-amz{margin-top:8px;align-items:center;font-size:12px}.ph{display:inline-flex;width:84px;height:84px;align-items:center;justify-content:center;color:var(--ink-2)}
.ad-flow,.rec-note{display:none}
"""

JS = """
(function(){var W="月火水木金土日".split("");var el=document.getElementById("st"),cd=document.getElementById("cd"),go=document.getElementById("go");
var S=Date.parse(el.dataset.start||"")||null,E=Date.parse(el.dataset.end||"")||null,N=Date.now();
function two(n){return ("0"+n).slice(-2)}
function left(ms){var d=Math.floor(ms/864e5),h=Math.floor(ms%864e5/36e5),m=Math.floor(ms%36e5/6e4);return d>0?d+"日"+h+"時間":h>0?h+"時間"+m+"分":m+"分"}
function same(a,b){a=new Date(a);b=new Date(b);return a.getFullYear()==b.getFullYear()&&a.getMonth()==b.getMonth()&&a.getDate()==b.getDate()}
var cls="",lab="受付中",big="",sub="";
if(E&&E<N){cls="end";lab="受付終了";big="この抽選の受付は終了しました";sub="";if(go){go.className="go off";go.textContent="受付は終了しました";}}
else if(S&&S>N){cls="pre";lab="受付前";big="開始まであと"+left(S-N);var s=new Date(S);sub=(s.getMonth()+1)+"/"+s.getDate()+"("+W[(s.getDay()+6)%7]+") "+two(s.getHours())+":"+two(s.getMinutes())+" 受付開始";}
else if(E){var soon=E-N<864e5;cls=soon?"soon":"";lab=same(E,N)?"本日締切":soon?"まもなく締切":"受付中";big="締切まであと"+left(E-N);}
else{big="受付中";sub="締切は告知でご確認ください";}
el.textContent=lab;el.className="chip st "+cls;if(cd){cd.className="cd "+cls;cd.innerHTML="<b>"+big+"</b>"+(sub?"<span>"+sub+"</span>":"");}
})();
(function(){var b=document.getElementById("ap");if(!b)return;var K="lot_applied";
function ld(){try{return JSON.parse(localStorage.getItem(K)||"{}")}catch(e){return {}}}
function sv(v){try{localStorage.setItem(K,JSON.stringify(v))}catch(e){}}
function show(){var a=ld()[b.dataset.key];b.className="apb"+(a?" on":"");b.textContent=a?"✓ 応募した":"☐ 応募した";}
b.addEventListener("click",function(){var a=ld(),k=b.dataset.key;if(a[k])delete a[k];else{var o={};try{o=JSON.parse(b.dataset.snap)}catch(e){}o.t=Date.now();a[k]=o;}sv(a);show();});
show();var l=document.createElement("a");l.href="/mylist/";l.className="mlk";l.textContent="応募したリストを見る →";b.parentNode.parentNode.appendChild(l);})();
"""


def _status(i, t):
    s, e = parse_dt(i.get("start")), parse_dt(i.get("end"))
    if e and e < t:
        return "end", "受付終了"
    if s and s > t:
        return "pre", "受付前"
    if e and (e - t).total_seconds() < 86400:
        return "soon", "まもなく締切"
    return "", "受付中"


def render(i, *, site, path, verify, now_dt, ended=False, redirect=None, aff="", related=(), updated=""):
    """1件分のHTML。i は sitegen の row（＋products / start / announce / buy）"""
    g = i.get("game")
    gshort = GAME_SHORT.get(g, "")
    name = short_name(i)
    store = i.get("store") or ""
    end_s, start_s = fmt(i.get("end")), fmt(i.get("start"))
    is_end = ended or bool(parse_dt(i.get("end")) and parse_dt(i["end"]) < now_dt)
    cls, lab = ("end", "受付終了") if is_end else _status(i, now_dt)
    canon = f"{site}/{path}" if site else ""
    ch = "店頭抽選（店頭で受け取り）" if i.get("channel") == "store" else "ネット抽選（当選後に購入・発送）"
    title = f"{store}の{gshort}抽選「{name}」" + (f"【{end_s}締切】" if end_s else "") + "｜トレカ抽選ナビ"
    desc = (f"{store}で受付中の{gshort}の抽選販売「{name}」。" + ((f"応募期間 {start_s}〜{end_s}。" if start_s else f"応募締切 {end_s}。") if end_s else "") +
            "応募方法・応募条件・対象商品・当選発表日をまとめています。")
    if is_end:
        desc = f"{store}の{gshort}の抽選「{name}」は受付を終了しました。いま受付中の抽選は一覧からさがせます。"

    rows = []

    def row(k, v, raw=False):
        if v:
            rows.append(f"<div><dt>{escape(k)}</dt><dd>{v if raw else escape(str(v))}</dd></div>")
    period = (f"{start_s} 〜 " if start_s else "") + (end_s or "締切は告知でご確認ください")
    row("応募期間" if start_s else "応募締切", (period + "まで") if end_s and not start_s else period)
    row("当選発表", i.get("announce") if not parse_dt(i.get("announce")) else fmt(i.get("announce")))
    row("購入期間", i.get("buy"))
    row("受け取り", ch + (f"｜{i['area']}" if i.get("channel") == "store" and i.get("area") else ""))
    if i.get("channel") == "store" and i.get("address"):
        from address import maps_url
        row("お店の住所", f'{escape(i["address"])} <a href="{escape(maps_url(store, i["address"]))}" target="_blank" rel="noopener">Googleマップで見る</a>', raw=True)
    row("応募方法", i.get("method"))
    row("応募条件", i.get("conditions"))
    req = []
    if i.get("id_check"):
        req.append("本人確認あり")
    if i.get("member") == "account":
        req.append("会員登録が必要")
    elif i.get("member") == "card":
        req.append("会員カード・アプリの提示が必要")
    row("必要なもの", "・".join(req))
    prods = [p for p in (i.get("products") or []) if p]
    if prods:
        row("対象商品", "<ul>" + "".join(f"<li>{escape(str(p))}</li>" for p in prods) + "</ul>", raw=True)
    else:
        row("商品", (i.get("product") or "").replace("ワンピカード", "ワンピースカード") or None)

    chips = [f'<span class="chip st {cls}" id="st" data-start="{escape(i.get("start") or "")}" data-end="{escape(i.get("end") or "")}">{lab}</span>']
    if gshort:
        chips.append(f'<span class="chip">{escape(gshort)}</span>')
    chips.append(f'<span class="chip">{"店頭抽選" if i.get("channel") == "store" else "ネット抽選"}</span>')
    if i.get("channel") == "store" and i.get("area"):
        chips.append(f'<span class="chip">{escape(i["area"])}</span>')

    if is_end:
        cd_html = '<div class="cd end" id="cd"><b>この抽選の受付は終了しました</b></div>'
    else:
        cd_html = f'<div class="cd {cls}" id="cd"><b>{"受付前" if cls == "pre" else "受付中"}</b><span>{escape(period)}</span></div>'
    share = f"{store}の{gshort}抽選「{name}」" + (f"\n⏰{end_s}締切" if end_s else "")
    share_url = "https://x.com/intent/post?text=" + quote(share + "\n" + (canon or ""))
    go_rel = "nofollow sponsored noopener" if re.search(r"amazon|amzn|アマゾン", f'{store}{i.get("url") or ""}', re.I) else "nofollow noopener"
    btn = (f'<a class="go off" id="go">受付は終了しました</a>' if is_end else
           (f'<a class="go" id="go" href="{escape(i["url"])}" target="_blank" rel="{go_rel}">応募ページを開く →</a>' if i.get("url")
            else '<a class="go off" id="go">応募先は店舗の告知でご確認ください</a>'))
    # 新着・締切間近のカードから来た人がすぐ応募できるよう、見出しのすぐ下にも応募ボタン
    top_go = (f'<a class="go go-top" href="{escape(i["url"])}" target="_blank" rel="{go_rel}">応募ページを開く →</a>'
              if i.get("url") and not is_end else "")
    snap = {"store": store, "product": name, "series": i.get("series"), "end": i.get("end"), "announce": i.get("announce"),
            "url": i.get("url"), "lpath": path, "game": g}
    ap_btn = (f'<button type="button" id="ap" class="apb" data-key="{escape(i.get("key") or "")}" '
              f'data-snap="{escape(json.dumps(snap, ensure_ascii=False))}">☐ 応募した</button>') if i.get("key") else ""
    acts = (f'<div class="acts">{btn}<div class="sub-acts">{ap_btn}<a href="{escape(share_url)}" target="_blank" rel="noopener">Xでシェア</a>'
            f'<a href="/{GAME_SLUG.get(g, "")}/">ほかの抽選を見る</a></div>'
            '<p class="note">情報は変わることがあります。応募前に必ず公式の告知をご確認ください。</p></div>')

    rel = "".join(f'<a href="{escape(h)}">{escape(t)}</a>' for t, h in related)
    rel_html = f'<nav class="more" aria-label="関連ページ"><h2>ほかの抽選もチェック</h2>{rel}</nav>' if rel else ""
    trail = [("トップ", ""), (f"{gshort}の抽選", f"{GAME_SLUG.get(g, '')}/"), (f"{store}「{name}」", path)]
    crumbs = '<nav class="crumbs" aria-label="パンくず">' + " › ".join(
        (f'<a href="/{escape(p)}">{escape(n)}</a>' if k < len(trail) - 1 else f"<span>{escape(n)}</span>")
        for k, (n, p) in enumerate(trail)) + "</nav>"
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": k + 1, "name": n, "item": f"{site}/{p}"} for k, (n, p) in enumerate(trail)]}]

    og = f"{site}/og.png" if site else "/og.png"
    head = [f"<title>{escape(title)}</title>", f'<meta name="description" content="{escape(desc)}">',
            f'<meta property="og:title" content="{escape(title)}">', f'<meta property="og:description" content="{escape(desc)}">',
            '<meta property="og:type" content="article">', '<meta property="og:site_name" content="トレカ抽選ナビ">',
            '<meta property="og:locale" content="ja_JP">', f'<meta property="og:image" content="{escape(og)}">',
            '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:image" content="{escape(og)}">',
            '<meta name="theme-color" content="#c8102e">', '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
            '<link rel="icon" href="/favicon.png" sizes="48x48">', '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
            f'<meta name="robots" content="{"noindex,follow" if is_end or redirect else "index,follow,max-image-preview:large"}">']
    if site:
        head.insert(0, '<script>if(/\\.pages\\.dev$/.test(location.hostname))location.replace(%s+location.pathname+location.search+location.hash)</script>' % json.dumps(site))
    if canon:
        head += [f'<link rel="canonical" href="{escape(canon)}">', f'<meta property="og:url" content="{escape(canon)}">']
    if redirect:
        head.append(f'<meta http-equiv="refresh" content="0;url=/{escape(redirect)}">')
    if verify:
        head.append(f'<meta name="google-site-verification" content="{escape(verify)}">')
    head += ['<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>" for x in ld]
    head += ['<link rel="preconnect" href="https://fonts.googleapis.com">',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=IBM+Plex+Mono:wght@500;600&display=swap">',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap&text=%E3%83%88%E3%83%AC%E3%82%AB%E6%8A%BD%E9%81%B8%E3%83%8A%E3%83%93">',
             f"<style>{CSS}</style>"]

    upd = parse_dt(updated)
    foot = f"情報の更新：{upd.month}/{upd.day} {upd:%H:%M}" if upd else ""
    ended_note = ('<p class="ended">この抽選の受付は終了しました。いま受付中の抽選は下の一覧からさがせます。</p>' if is_end else "")
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' + "\n".join(head) +
            '</head><body><header><div class="wrap"><a href="/" class="logo" aria-label="トレカ抽選ナビ トップへ">'
            '<small>TORECA LOTTERY NAVI</small><span class="w">トレカ<span class="t">抽選</span>ナビ</span></a></div></header>'
            f'<main class="wrap">{crumbs}<p style="margin:2px 0 6px;font-size:11px;color:var(--ink-2)">本ページはプロモーションを含みます</p>{ended_note}<article class="tk"><div class="tk-h"><div class="chips">{"".join(chips)}</div>'
            f'<h1>{escape(name)}</h1><p class="store">{escape(store)}</p>{cd_html}{top_go}</div>'
            f'<dl>{"".join(rows)}</dl>{acts}</article>{aff}{rel_html}'
            f'<footer>{escape(foot)}　トレカ抽選ナビは抽選情報をまとめているサイトです。応募・購入は各店舗のページで行われます。</footer></main>'
            f'<script>{JS}</script></body></html>')


def snapshot(i):
    return {k: i.get(k) for k in KEEP if i.get(k) not in (None, "", [])}


MYLIST_JS = r"""
(function(){var K="lot_applied",W="日月火水木金土";
function ld(){try{return JSON.parse(localStorage.getItem(K)||"{}")}catch(e){return null}}
function sv(v){try{localStorage.setItem(K,JSON.stringify(v))}catch(e){}}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function ymd(d){return d.getFullYear()*10000+(d.getMonth()+1)*100+d.getDate()}
function md(d){return (d.getMonth()+1)+"/"+d.getDate()+"("+W[d.getDay()]+")"}
// 当選発表日：ISOの日付か「11/4(水)23時頃」のような書き方から月日を読む（年は締切の年。締切より前の月なら翌年）
function annDate(o){var a=o.announce;if(!a)return null;var d=Date.parse(a);if(!isNaN(d)&&/^\d{4}-/.test(a))return new Date(d);
 var m=String(a).match(/(\d{1,2})\s*[\/月]\s*(\d{1,2})/);if(!m)return null;var e=o.end?new Date(o.end):new Date();var y=e.getFullYear();
 var r=new Date(y,+m[1]-1,+m[2]);if(o.end&&r<new Date(e.getFullYear(),e.getMonth(),e.getDate()-1))r=new Date(y+1,+m[1]-1,+m[2]);return r;}
function p2(n){return("0"+n).slice(-2)}
function gdt(d){return d.getUTCFullYear()+p2(d.getUTCMonth()+1)+p2(d.getUTCDate())+"T"+p2(d.getUTCHours())+p2(d.getUTCMinutes())+"00Z"}
function gday(d){return d.getFullYear()+p2(d.getMonth()+1)+p2(d.getDate())}
function nm(o){return (o.store||"抽選")+"「"+(o.series||o.product||"")+"」"}
function lk(o){return o.lpath?location.origin+"/"+o.lpath:(o.url||"")}
// Googleカレンダーの「予定を追加」画面を開くリンク（締切は締切の時刻、発表日は終日）
function gcal(o,kind){var t,d;if(kind==="end"){if(!o.E)return"";t="【締切】"+nm(o);d=gdt(new Date(o.E-30*60e3))+"/"+gdt(o.E)}
 else{if(!o.A)return"";t="【結果発表】"+nm(o);var n=new Date(o.A.getFullYear(),o.A.getMonth(),o.A.getDate()+1);d=gday(o.A)+"/"+gday(n)}
 return"https://calendar.google.com/calendar/render?action=TEMPLATE&text="+encodeURIComponent(t)+"&dates="+d+"&details="+encodeURIComponent(lk(o)+"\nトレカ抽選ナビの「応募したリスト」から追加")}
function ics(rows){var L=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//toreca-lottery-navi//mylist//JA","CALSCALE:GREGORIAN"],st=gdt(new Date());
 function ev(uid,head,sum,o){L.push("BEGIN:VEVENT","UID:"+uid+"@toreca-navi","DTSTAMP:"+st);L.push.apply(L,head);
  L.push("SUMMARY:"+sum.replace(/[,;\\]/g," "),"DESCRIPTION:"+lk(o).replace(/[,;]/g," "));if(lk(o))L.push("URL:"+lk(o));}
 rows.forEach(function(o){var id=String(o.k).replace(/[^\w-]/g,"");
  if(o.E&&o.E>new Date()){ev(id+"-end",["DTSTART:"+gdt(new Date(o.E-30*60e3)),"DTEND:"+gdt(o.E)],"【締切】"+nm(o),o);
   L.push("BEGIN:VALARM","ACTION:DISPLAY","DESCRIPTION:もうすぐ締切","TRIGGER:-PT3H","END:VALARM","END:VEVENT")}
  if(o.A&&ymd(o.A)>=ymd(new Date())){var n=new Date(o.A.getFullYear(),o.A.getMonth(),o.A.getDate()+1);
   ev(id+"-ann",["DTSTART;VALUE=DATE:"+gday(o.A),"DTEND;VALUE=DATE:"+gday(n)],"【結果発表】"+nm(o),o);
   L.push("BEGIN:VALARM","ACTION:DISPLAY","DESCRIPTION:今日が結果発表","TRIGGER:PT9H","END:VALARM","END:VEVENT")}});
 L.push("END:VCALENDAR");return L.join("\r\n")}
var ROWS=[];
function render(){var a=ld(),box=document.getElementById("ml");
 if(a===null){box.innerHTML='<p class="empty">このブラウザでは記録を読み込めませんでした（プライベートモードなど）。</p>';return}
 var ks=Object.keys(a);document.getElementById("mln").textContent=ks.length;
 if(!ks.length){box.innerHTML='<p class="empty">まだ「応募した」の印をつけた抽選はありません。<br>抽選の一覧や個別ページの「☐ 応募した」を押すと、ここに並びます。</p>';return}
 var now=new Date(),T=ymd(now),rows=ks.map(function(k){var o=a[k];if(typeof o!=="object"||!o)o={t:o};o.k=k;o.E=o.end?new Date(o.end):null;o.A=annDate(o);
  o.g=o.A&&ymd(o.A)===T?0:o.A&&ymd(o.A)<T?3:o.E&&o.E>now?1:2;return o});
 rows.sort(function(x,y){return x.g-y.g||((x.A||x.E||0)-(y.A||y.E||0))});ROWS=rows;
 var cn=rows.filter(function(o){return (o.E&&o.E>now)||(o.A&&ymd(o.A)>=T)}).length,cb=document.getElementById("mlcal");
 var cnn=document.getElementById("mlcaln");if(cnn)cnn.hidden=!cn;if(cb){cb.hidden=!cn;cb.textContent="📅 "+cn+"件の抽選の締切・結果発表をカレンダーに入れる"}
 var H={0:"🎉 今日が結果発表",1:"受付中（締切が近い順）",2:"締切済み・結果待ち",3:"結果発表日を過ぎた抽選"},h="",cur=-1;
 rows.forEach(function(o){if(o.g!==cur){if(cur>=0)h+="</ul>";h+='<h2 class="g'+o.g+'">'+H[o.g]+'</h2><ul>';cur=o.g}
  var name=o.store?esc(o.store)+"「"+esc(o.series||o.product||"")+"」":"（抽選の情報を記録していません）";
  var link=o.lpath?'/'+esc(o.lpath):(o.url?esc(o.url):"");
  h+='<li class="g'+o.g+'"><div class="t">'+(link?'<a href="'+link+'">'+name+'</a>':name)+'</div><div class="m">'+
   (o.E?'<span>締切 '+md(o.E)+' '+("0"+o.E.getHours()).slice(-2)+':'+("0"+o.E.getMinutes()).slice(-2)+'</span>':'')+
   (o.announce?'<span class="an">結果発表 '+esc(/^\d{4}-/.test(o.announce)&&o.A?md(o.A):o.announce)+'</span>':'<span>結果発表日は告知で確認</span>')+
   '</div><div class="cl">'+(o.E&&o.E>now?'<a target="_blank" rel="noopener" href="'+esc(gcal(o,"end"))+'">＋締切をGoogleカレンダーへ</a>':'')+
   (o.A&&ymd(o.A)>=T?'<a target="_blank" rel="noopener" href="'+esc(gcal(o,"ann"))+'">＋発表日をGoogleカレンダーへ</a>':'')+'</div>'+
   '<button type="button" data-k="'+esc(o.k)+'">外す</button></li>'});
 box.innerHTML=h+"</ul>";}
document.getElementById("ml").addEventListener("click",function(e){var b=e.target.closest("button[data-k]");if(!b)return;var a=ld()||{};delete a[b.dataset.k];sv(a);render();});
var cb=document.getElementById("mlcal");if(cb)cb.addEventListener("click",function(){
 var blob=new Blob([ics(ROWS)],{type:"text/calendar;charset=utf-8"}),u=URL.createObjectURL(blob),x=document.createElement("a");
 x.href=u;x.download="toreca-chusen.ics";document.body.appendChild(x);x.click();setTimeout(function(){URL.revokeObjectURL(u);x.remove()},1500);});
render();})();
"""


def mylist_page(site=""):
    """応募したリスト（/mylist/）：このブラウザの中だけに記録した「応募した」抽選の一覧。検索には載せない"""
    css = CSS + """
.ml h1{font-size:22px;margin:16px 0 4px}.ml .lead{color:var(--ink-2);font-size:14px;margin:0 0 12px}
.ml h2{font-size:15px;margin:18px 0 6px}.ml h2.g0{color:var(--red)}
.ml ul{list-style:none;margin:0;padding:0;background:var(--card);border:1px solid var(--rule);border-radius:12px}
.ml li{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:10px 14px;border-top:1px solid var(--rule)}.ml li:first-child{border-top:0}
.ml li.g0{background:var(--red-soft)}.ml li.g3{opacity:.6}.ml .t{font-weight:700}.ml .t a{text-decoration:none}
.ml .m{grid-column:1;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;color:var(--ink-2)}.ml .an{font-weight:700;color:var(--ink)}
.ml li.g0 .an{color:var(--red)}.ml .cl{grid-column:1;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px}.ml .cl:empty{display:none}.ml .cl a{color:var(--ink-2)}
.ml .calbtn{display:block;width:100%;font:inherit;font-weight:700;font-size:14px;padding:11px;margin:0 0 6px;border-radius:10px;border:1px solid var(--ink);background:var(--card);color:var(--ink);cursor:pointer}
.ml .calnote{font-size:11.5px;color:var(--ink-2);margin:0 0 12px}.ml li button{grid-column:2;grid-row:1/3;align-self:center;font:inherit;font-size:12px;border:1px solid var(--rule);background:none;border-radius:6px;padding:3px 8px;color:var(--ink-2);cursor:pointer}
.ml .empty{background:var(--card);border:1px dashed var(--rule);border-radius:12px;padding:24px;text-align:center;color:var(--ink-2)}
.ml .small{font-size:11.5px;color:var(--ink-2);margin:14px 0 30px}"""
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>応募したリスト｜トレカ抽選ナビ</title><meta name="robots" content="noindex">'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=IBM+Plex+Mono:wght@500;600&display=swap">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap&text=%E3%83%88%E3%83%AC%E3%82%AB%E6%8A%BD%E9%81%B8%E3%83%8A%E3%83%93">'
            f'<style>{css}</style></head><body><header><div class="wrap"><a href="/" class="logo" aria-label="トレカ抽選ナビ トップへ">'
            '<small>TORECA LOTTERY NAVI</small><span class="w">トレカ<span class="t">抽選</span>ナビ</span></a></div></header>'
            '<main class="wrap ml"><h1>応募したリスト（<span id="mln">0</span>件）</h1>'
            '<p class="lead">「☐ 応募した」を押した抽選の、締切と結果発表日をまとめています。結果発表の日になると一番上に出ます。会員登録はいりません。</p>'
            '<button type="button" class="calbtn" id="mlcal" hidden></button>'
            '<p class="calnote" id="mlcaln" hidden>iPhoneはそのまま「カレンダーに追加」、Androidはダウンロードしたファイルを開くとカレンダーに入ります。締切の3時間前と発表日の朝9時に通知します。1件ずつならGoogleカレンダーのリンクも使えます。</p>'
            '<div id="ml"><p class="empty">読み込み中…</p></div>'
            '<p class="small">※記録はこのスマホ・パソコンのブラウザの中だけに保存しています（ほかの人には見えません）。'
            'ブラウザの履歴やサイトのデータを消したとき、プライベートモードのとき、別のブラウザ・別の端末では表示されません。'
            '結果は必ずお店の告知・メールで確認してください。</p>'
            '<p><a href="/">← 抽選の一覧にもどる</a></p></main>'
            f'<script>{MYLIST_JS}</script></body></html>')
