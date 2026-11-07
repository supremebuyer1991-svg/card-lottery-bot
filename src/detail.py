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
        "conditions", "tags", "url", "channel", "area", "address", "id_check", "member", "image", "img_url", "images", "spath", "found_at", "manual")


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
 font-size:17px;letter-spacing:.04em;padding:14px;border-radius:10px}.go-top{margin-top:12px}.pics{display:flex;gap:8px;justify-content:center;margin:12px 0 4px}.pics a,.pics span{display:block;width:150px;height:150px;border-radius:12px;background:#fff;border:1px solid var(--rule);overflow:hidden}.pics.n2 a,.pics.n2 span{width:120px;height:120px}.pics.n3 a,.pics.n3 span,.pics.n4 a,.pics.n4 span{width:84px;height:84px}.pics img{width:100%;height:100%;object-fit:contain;display:block}.line-room{display:flex;align-items:center;gap:10px;margin:14px 0 6px;padding:10px 12px;border-radius:12px;background:#06c755;color:#fff;text-decoration:none}.line-room>b{flex:none;font-size:13px;font-weight:900;background:#fff;color:#06c755;border-radius:6px;padding:2px 6px}.line-room span{display:grid;gap:1px;min-width:0}.line-room strong{font-size:14.5px}.line-room small{font-size:11.5px;opacity:.9}.sq1{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;justify-content:center;margin:6px 0 10px;padding:8px 12px;border:1px solid var(--rule);border-radius:10px;text-decoration:none;color:var(--ink);font-size:13px}.sq1 b{font-size:17px;font-weight:800}.sq1 em{font-style:normal;font-size:12px;font-weight:700}.sq1 em.up{color:var(--red)}.sq1 em.down{color:#2563eb}.sq1 i{font-style:normal;font-weight:700;color:var(--red)}.go.off{background:var(--rule);color:var(--ink-2);pointer-events:none}
.followbox{margin:14px 0 0;border:1px solid var(--rule);border-radius:12px;padding:12px;background:#f8fafc;text-align:center}.followbox b{font-size:15px}.followbox p{margin:6px 0 10px;font-size:13px;color:#475569}.fbtns{display:grid;gap:8px}.fbtns a{display:block;border-radius:10px;padding:10px 6px;font-weight:700;font-size:14px;text-decoration:none;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fbtns .fx{background:#111}.fbtns .fl{background:#06c755}.sub-acts{display:grid;grid-template-columns:1fr 1fr;gap:8px}.sub-acts .apb,.calbox{grid-column:1/-1}.calbox{border:1px solid var(--rule);border-radius:10px;padding:10px 12px;display:grid;gap:8px;text-align:center}.calbox b{font-size:14px}.calbtns{display:grid;grid-template-columns:1fr 1fr;gap:8px}.calbox .calsub-l{border:0;padding:0;font-size:13px;color:var(--red);text-decoration:underline}.apb{font:inherit;font-weight:700;font-size:14px;border:1px solid var(--rule);border-radius:10px;padding:9px;background:#fff;cursor:pointer}.apb.on{color:#15803d;border-color:#15803d}.mlk{display:block;text-align:center;font-size:13px;margin-top:8px}.sub-acts a{display:block;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border:1px solid var(--rule);border-radius:10px;padding:9px;text-decoration:none;font-weight:700;font-size:14px}
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
.b-rak{background:#bf0000;color:#fff!important;border-color:#bf0000!important}.b-amz{background:#ffd814;color:#0f1111!important;border-color:#fcd200!important}.b-ymd{background:#e60012;color:#fff!important;border-color:#e60012!important}
.ad-pr{font-size:10px;letter-spacing:.08em;color:#fff;background:#6b7280;border-radius:3px;padding:1px 5px}.ad .ad-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.nextgo{display:block;margin:0 0 14px;padding:14px 16px;border-radius:12px;background:var(--red,#c8102e);color:#fff;font-weight:700;font-size:16px;text-decoration:none;text-align:center}.nextgo b{margin-left:4px}
.ad.lose{border:2px solid #f3d9a4;background:#fffaf0}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .ad.lose{background:#2a2214;border-color:#5a4520}:root:not([data-theme="light"]) .lose-l li{border-top-color:#3a3020}}.lose-sub{margin:4px 0 8px;font-size:13px;color:var(--ink-2)}.lose-l{list-style:none;margin:0;padding:0}
.lose-l li{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;border-top:1px solid #f0e2c4}.lose-l li:first-child{border-top:0}
.lose-l small{display:block;font-size:12px;color:var(--ink-2)}.lose-l a{flex:none;font-size:13px;font-weight:700;padding:8px 12px;border-radius:8px;text-decoration:none}
.lose-l .b-rakb{background:#bf0000;color:#fff!important}.ad-note{font-size:11px;color:var(--ink-2);margin:6px 0 0}
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


def cal_event(i, store, name, canon, stamp=None):
    """締切の1時間前〜締切の予定1件（VEVENT の行のリスト）。締切が無ければ None"""
    from datetime import timedelta, timezone
    e = parse_dt(i.get("end"))
    if not e:
        return None
    st = e - timedelta(hours=1)
    z = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda x: x.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    title = f"【抽選締切】{store}「{name}」"
    det = f"応募はお早めに。くわしくは {canon}" if canon else "応募はお早めに"
    ev = ["BEGIN:VEVENT", f"UID:{(i.get('key') or 'x')[:16]}@tcg-chusen.com", f"DTSTAMP:{z(stamp or st)}",
          f"DTSTART:{z(st)}", f"DTEND:{z(e)}", "SUMMARY:" + esc(title), "DESCRIPTION:" + esc(det)]
    if canon:
        ev.append("URL:" + canon)
    return ev + ["BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", "DESCRIPTION:" + esc(title), "END:VALARM", "END:VEVENT"]


def _fold(line):
    """.ics の1行は75バイトまで（長い行は折り返す）"""
    b, out = line.encode("utf-8"), []
    while len(b) > 73:
        n = 73
        while n and (b[n] & 0xC0) == 0x80:  # 文字の途中で切らない
            n -= 1
        out.append(b[:n].decode("utf-8"))
        b = b[n:]
    out.append(b.decode("utf-8"))
    return "\r\n ".join(out)


def ics_wrap(events, cal_name=None):
    """VEVENT をまとめて1つの .ics に。cal_name があれば購読用（名前・6時間ごとに更新）"""
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tcg-chusen//JP", "CALSCALE:GREGORIAN"]
    if cal_name:
        head += ["METHOD:PUBLISH", "X-WR-CALNAME:" + cal_name, "X-WR-TIMEZONE:Asia/Tokyo",
                 "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    lines = head + [l for ev in events for l in ev] + ["END:VCALENDAR"]
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def cal_ics(i, store, name, canon):
    """締切の1時間前〜締切の予定（.ics）。無ければ None"""
    ev = cal_event(i, store, name, canon)
    return ics_wrap([ev]) if ev else None


_XACC = []


def _x_account():
    if not _XACC:
        try:
            from common import load_settings
            _XACC.append((load_settings().get("x_account") or "").strip().lstrip("@"))
        except Exception:
            _XACC.append("")
    return _XACC[0]


def _cal_links(i, store, name, canon):
    """締切をカレンダーに入れるボタン（Googleカレンダー／iPhone・Androidのカレンダー＝同じフォルダの shimekiri.ics）"""
    from datetime import timedelta, timezone
    e = parse_dt(i.get("end"))
    if not e:
        return ""
    st = e - timedelta(hours=1)
    z = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = f"【抽選締切】{store}「{name}」"
    det = f"応募はお早めに。くわしくは {canon}" if canon else "応募はお早めに"
    g = ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + quote(title) +
         f"&dates={z(st)}/{z(e)}&details=" + quote(det))
    return ('<div class="calbox"><b>📅 締切をカレンダーに入れる</b><div class="calbtns">'
            f'<a href="{escape(g)}" target="_blank" rel="noopener">Googleカレンダー</a>'
            '<a href="shimekiri.ics">iPhone・スマホ</a></div>'
            '<a class="calsub-l" href="/calendar/#sub">🔔 これからの締切も自動で入れる →</a></div>')


def render(i, *, site, path, verify, now_dt, ended=False, redirect=None, aff="", related=(), updated="", souba=None, noindex=False, next_link=None):
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
    # 同じお店・同じ弾で中身だけ違う商品（御三家カードセットの各組み合わせなど）は、カッコの中身もタイトルに入れて区別する（11/3 タイトル重複の対策）
    _v = re.search(r"（([^（）]{2,30})）\s*$", i.get("product") or "")
    tname = name + (f"（{_v.group(1)}）" if _v and _v.group(1) not in name and not re.search(r"円|税込|BOX|名様|抽選|お一人|1人|まで|送料", _v.group(1)) else "")
    store_t = re.sub(r"\s*[（(][^）)]*[）)]", "", store).strip() or store  # タイトルはカッコ書きを省いて短く（本文はそのまま。11/7 Fable）
    title = f"{store_t}の{gshort}抽選「{tname}」" + (f"【{end_s}締切】" if end_s else "") + "｜トレカ抽選ナビ"
    desc = (f"{store}で受付中の{gshort}の抽選販売「{name}」。" + ((f"応募期間 {start_s}〜{end_s}。" if start_s else f"応募締切 {end_s}。") if end_s else "") +
            "応募方法・応募条件・対象商品・当選発表日をまとめています。")
    if is_end:
        title = f"【受付終了】{store_t}の{gshort}抽選「{tname}」" + (f"（{end_s}締切）" if end_s else "") + "｜トレカ抽選ナビ"
        desc = (f"{store}の{gshort}の抽選「{name}」は受付を終了しました。" +
                (f"{next_link[0].replace('を見る', '')}。" if next_link else "いま受付中の抽選は一覧からさがせます。"))

    rows = []

    def row(k, v, raw=False):
        if v:
            rows.append(f"<div><dt>{escape(k)}</dt><dd>{v if raw else escape(str(v))}</dd></div>")
    period = (f"{start_s} 〜 " if start_s else "") + (end_s or "締切は告知でご確認ください")
    row("応募期間" if start_s else "応募締切", (period + "まで") if end_s and not start_s else period)
    row("当選発表", i.get("announce") if not parse_dt(i.get("announce")) else re.sub(r"\s*00:00$", "", fmt(i.get("announce"))))  # 時刻が分からない日付は「00:00」を出さない
    row("購入期間", i.get("buy"))
    row("受け取り", ch + (f"｜{i['area']}" if i.get("channel") == "store" and i.get("area") else ""))
    if i.get("channel") == "store" and i.get("address"):
        from address import maps_url
        row("お店の住所", f'{escape(i["address"])} <a href="{escape(maps_url(store, i["address"]))}" target="_blank" rel="noopener">Googleマップで見る</a>', raw=True)
    row("応募方法", i.get("method"))
    row("応募条件", i.get("conditions"))
    from common import needs_of
    req, unk = needs_of(i)
    row("必要なもの", ("・".join(req) + ("（ほかの条件は応募ページで確認してください）" if unk else "")) if req
        else "応募ページで確認してください" if unk else "とくになし（告知に書かれていた範囲）")
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
    cal_btn = _cal_links(i, store, name, canon) if not is_end else ""
    acts = (f'<div class="acts">{btn}<div class="sub-acts">{ap_btn}{cal_btn}<a href="{escape(share_url)}" target="_blank" rel="noopener">Xでシェア</a>'
            f'<a href="/{GAME_SLUG.get(g, "")}/">ほかの抽選を見る</a></div>'
            '<p class="note">情報は変わることがあります。応募前に必ず公式の告知をご確認ください。</p></div>')
    # 検索から来た人をフォロワーにする（11/3 SNS集客プラン）：同じ弾の次の抽選・締切をXで受け取れることを案内
    acct = _x_account()
    what = f"「{i.get('series')}」" if i.get("series") else f"{gshort}"
    follow = (f'<div class="followbox"><b>🔔 {escape(what)}の次の抽選を見逃さない</b>'
              f'<p>新しい抽選が始まったとき・締切が近いときに、Xでお知らせしています。</p>'
              f'<div class="fbtns"><a class="fx" href="https://x.com/{escape(acct)}" target="_blank" rel="noopener">𝕏 @{escape(acct)} をフォローする</a></div></div>') if acct else ""
    acts = acts + follow

    rel = "".join(f'<a href="{escape(h)}">{escape(t)}</a>' for t, h in related)
    rel_html = f'<nav class="more" aria-label="関連ページ"><h2>ほかの抽選もチェック</h2>{rel}</nav>' if rel else ""
    trail = [("トップ", ""), (f"{gshort}の抽選", f"{GAME_SLUG.get(g, '')}/"), (f"{store}「{name}」", path)]
    crumbs = '<nav class="crumbs" aria-label="パンくず">' + " › ".join(
        (f'<a href="/{escape(p)}">{escape(n)}</a>' if k < len(trail) - 1 else f"<span>{escape(n)}</span>")
        for k, (n, p) in enumerate(trail)) + "</nav>"
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": k + 1, "name": n, "item": f"{site}/{p}"} for k, (n, p) in enumerate(trail)]}]
    # ページの公開日・更新日（検索で「新しい情報」と分かるように）
    ld.append({"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc, "url": canon or None,
               "inLanguage": "ja", **({"datePublished": i["found_at"]} if i.get("found_at") else {}),
               **({"dateModified": updated} if updated else {}),
               "publisher": {"@type": "Organization", "name": "トレカ抽選ナビ", "url": f"{site}/"}})

    og = f"{site}/og.png" if site else "/og.png"
    head = [f"<title>{escape(title)}</title>", f'<meta name="description" content="{escape(desc)}">',
            f'<meta property="og:title" content="{escape(title)}">', f'<meta property="og:description" content="{escape(desc)}">',
            '<meta property="og:type" content="article">', '<meta property="og:site_name" content="トレカ抽選ナビ">',
            '<meta property="og:locale" content="ja_JP">', f'<meta property="og:image" content="{escape(og)}">',
            '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:image" content="{escape(og)}">',
            '<meta name="theme-color" content="#c8102e">', '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
            '<link rel="icon" href="/favicon.png" sizes="48x48">', '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
            f'<meta name="robots" content="{"noindex,follow" if is_end or redirect or noindex else "index,follow,max-image-preview:large"}">']
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
    if is_end and next_link:  # 終わった抽選のページに検索から来た人を、いま受付中の抽選へ（11/7 検索：終了ページの表示が多くクリック率1%）
        ended_note += (f'<a class="nextgo" href="{escape(next_link[1])}">{escape(next_link[0])} <b>→</b></a>')
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' + "\n".join(head) +
            '</head><body><header><div class="wrap"><p style="margin:0;padding-top:4px;font-size:12px;line-height:1.4;color:var(--ink);text-align:right">本ページはプロモーションを含みます</p><a href="/" class="logo" aria-label="トレカ抽選ナビ トップへ">'
            '<small>TORECA LOTTERY NAVI</small><span class="w">トレカ<span class="t">抽選</span>ナビ</span></a></div></header>'
            f'<main class="wrap">{crumbs}{ended_note}<article class="tk"><div class="tk-h"><div class="chips">{"".join(chips)}</div>'
            f'<h1>{escape(name)}</h1><p class="store">{escape(store)}</p>{_pics(i, name)}{_sq(souba)}{cd_html}{top_go}</div>'
            f'<dl>{"".join(rows)}</dl>{acts}</article>{aff}{rel_html}'
            f'<footer>{escape(foot)}　トレカ抽選ナビは抽選情報をまとめているサイトです。応募・購入は各店舗のページで行われます。　<a href="/privacy.html">プライバシーポリシー</a></footer></main>'
            f'<script>{JS}</script></body></html>')


def _sq(sb):
    """写真の下：この弾のBOX相場（押すと弾ページの相場の欄へ）"""
    if not sb:
        return ""
    return (f'<a class="sq1" href="{escape(sb["url"])}"><span>📈 BOX相場（{escape(sb["date"])}）</span><b>{escape(sb["price"])}</b>'
            + (f'<em class="{sb["cls"]}">{escape(sb["diff"])}</em>' if sb.get("diff") else "") + '<i>相場を見る ›</i></a>')


def _pics(i, name):
    """店名と残り時間の間：商品の写真（押すと楽天の商品ページ・アフィリエイト）。複数の商品の抽選は4枚まで"""
    lst = i.get("images") if len(i.get("images") or []) > 1 else ([{"src": i["image"], "url": i.get("img_url")}] if i.get("image") else [])
    if not lst:
        return ""
    one = lambda x: (f'<a href="{escape(x["url"])}" target="_blank" rel="nofollow sponsored noopener" title="楽天市場で見る">'
                     f'<img src="{escape(x["src"])}" alt="{escape(name)}" loading="lazy"></a>' if x.get("url")
                     else f'<span><img src="{escape(x["src"])}" alt="{escape(name)}" loading="lazy"></span>')
    return f'<div class="pics n{min(len(lst), 4)}">' + "".join(one(x) for x in lst[:4]) + '</div>'


def snapshot(i):
    return {k: i.get(k) for k in KEEP if i.get(k) not in (None, "", [])}


MYLIST_JS = r"""
(function(){var K="lot_applied",W="日月火水木金土",RU="https://rakuten-watch.supreme-buyer-1991.workers.dev/report";
function uid(){try{var u=localStorage.getItem("lot_uid");if(!u){u=(crypto.randomUUID?crypto.randomUUID():String(Math.random()).slice(2)+Date.now());localStorage.setItem("lot_uid",u)}return u}catch(e){return""}}
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
// 落選・当選と報告した直後に出す案内（11/7）：落選→まだ買える方法、当選→開封前にそろえたいもの。リンクは広告（PR表記）
function rk(u){var a=(window.MLCFG||{}).raff;return a?"https://hb.afl.rakuten.co.jp/hgc/"+a+"/?pc="+encodeURIComponent(u)+"&m="+encodeURIComponent(u):u}
function az(q){var t=(window.MLCFG||{}).tag;return "https://www.amazon.co.jp/s?k="+encodeURIComponent(q)+(t?"&tag="+encodeURIComponent(t):"")}
function qn(o){return (/ONE PIECE|ワンピ/.test((o.product||"")+(o.store||""))?"ONE PIECEカードゲーム ":"ポケモンカードゲーム ")+(o.series||o.product||"")}
var REL='target="_blank" rel="nofollow sponsored noopener"';
function offerLose(o){var q=qn(o),sb=null,S=(window.MLCFG||{}).souba||{};for(var k in S){if(o.series&&k.indexOf("|"+o.series)>0){sb=S[k];break}}
 return '<div class="off"><b>抽選には外れても、まだ買えます</b> <span class="pr">PR</span>'+
  '<small style="flex-basis:100%">在庫はタッチの差で復活することがあるので、こまめにチェックがおすすめです。</small>'+
  '<a '+REL+' href="'+esc(rk("https://books.rakuten.co.jp/search?sitem="+encodeURIComponent(q)))+'">楽天ブックスの在庫をチェック</a>'+
  '<a '+REL+' href="'+esc(az(q))+'">Amazonの在庫・招待リクエストをチェック</a>'+
  '<a '+REL+' href="'+esc(rk("https://search.rakuten.co.jp/search/mall/"+encodeURIComponent(q)+"/"))+'">楽天市場でさがす'+(sb?'（相場 ¥'+Number(sb[0]).toLocaleString()+'）':'')+'</a></div>'}
function offerWin(o){var g=/ONE PIECE|ワンピ/.test((o.product||"")+(o.store||""))?"ONE PIECEカードゲーム ":"ポケモンカードゲーム ";
 return '<div class="off win"><b>🎉 当選おめでとうございます！開封前にそろえたいもの</b> <span class="pr">PR</span>'+
  ["スリーブ","ローダー","デッキケース","ストレージ"].map(function(k){return '<a '+REL+' href="'+esc(rk("https://search.rakuten.co.jp/search/mall/"+encodeURIComponent(g+k)+"/"))+'">'+k+'（楽天）</a>'}).join("")+'</div>'}
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
   (o.g!==1&&o.res==="lose"?offerLose(o):'')+(o.g!==1&&o.res==="win"?offerWin(o):'')+
   (o.g!==1?'<div class="rp">'+(o.res?'<span>'+(o.res==="win"?"🎉 当選と報告しました":"落選と報告しました")+'</span><a href="#" data-r="none" data-rk="'+esc(o.k)+'">取り消す</a>'
    :'<span>結果は？</span><a href="#" class="w" data-r="win" data-rk="'+esc(o.k)+'">🎉 当選した</a><a href="#" data-r="lose" data-rk="'+esc(o.k)+'">落選した</a>')+'</div>':'')+
   '<button type="button" data-k="'+esc(o.k)+'">外す</button></li>'});
 box.innerHTML=h+"</ul>";}
document.getElementById("ml").addEventListener("click",function(e){var r=e.target.closest("a[data-rk]");
 if(r){e.preventDefault();var a0=ld()||{},k0=r.dataset.rk,o0=a0[k0];if(!o0||typeof o0!=="object")return;var v=r.dataset.r;
  if(v==="none")delete o0.res;else o0.res=v;sv(a0);render();
  try{fetch(RU,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({k:k0,res:v,uid:uid(),store:o0.store||"",series:o0.series||o0.product||"",game:o0.game||""})})}catch(_){}
  return}
 var b=e.target.closest("button[data-k]");if(!b)return;var a=ld()||{};delete a[b.dataset.k];sv(a);render();});
var cb=document.getElementById("mlcal");if(cb)cb.addEventListener("click",function(){
 var blob=new Blob([ics(ROWS)],{type:"text/calendar;charset=utf-8"}),u=URL.createObjectURL(blob),x=document.createElement("a");
 x.href=u;x.download="toreca-chusen.ics";document.body.appendChild(x);x.click();setTimeout(function(){URL.revokeObjectURL(u);x.remove()},1500);});
render();})();
"""


def mylist_page(site="", raff="", tag="", souba=None):
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
.ml .small{font-size:11.5px;color:var(--ink-2);margin:14px 0 30px}
.ml .rp{grid-column:1;display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:12.5px;margin-top:4px}.ml .rp a{padding:4px 10px;border:1px solid var(--rule);border-radius:999px;text-decoration:none;color:var(--ink)}
.ml .rp a.w{border-color:var(--red);color:var(--red);font-weight:700}
.ml .off{grid-column:1/3;display:flex;flex-wrap:wrap;gap:6px;align-items:center;background:#fff7e6;border:1px solid #f3d9a4;border-radius:10px;padding:10px;margin-top:6px;font-size:13px}
.ml .off b{flex-basis:100%}.ml .off.win{background:#ecfdf3;border-color:#a6e3c0}.ml .off a{background:#bf0000;color:#fff;border-radius:8px;padding:6px 10px;text-decoration:none;font-weight:700;font-size:12.5px}
.ml .off .pr{font-size:10px;background:#888;color:#fff;border-radius:3px;padding:0 4px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .ml .off{background:#2a2214;border-color:#5a4520;color:var(--ink)}:root:not([data-theme="light"]) .ml .off.win{background:#122a1d;border-color:#2b5c40}}
:root[data-theme="dark"] .ml .off{background:#2a2214;border-color:#5a4520;color:var(--ink)}:root[data-theme="dark"] .ml .off.win{background:#122a1d;border-color:#2b5c40}
.ml [hidden]{display:none!important}.ml .follow-ml{font-size:13px;background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:10px 12px;margin:12px 0}.ml .follow-ml a{font-weight:700}"""
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>応募したリスト｜トレカ抽選ナビ</title><meta name="robots" content="noindex">'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=IBM+Plex+Mono:wght@500;600&display=swap">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap&text=%E3%83%88%E3%83%AC%E3%82%AB%E6%8A%BD%E9%81%B8%E3%83%8A%E3%83%93">'
            f'<style>{css}</style></head><body><header><div class="wrap"><a href="/" class="logo" aria-label="トレカ抽選ナビ トップへ">'
            '<small>TORECA LOTTERY NAVI</small><span class="w">トレカ<span class="t">抽選</span>ナビ</span></a></div></header>'
            '<main class="wrap ml"><h1>応募したリスト（<span id="mln">0</span>件）</h1>'
            '<p class="lead">「☐ 応募した」を押した抽選の、締切と結果発表日をまとめています。結果発表の日になると一番上に出ます。会員登録はいりません。'
            '結果が出たら「当選した／落選した」を押してください。みんなの報告から<a href="/tousenritsu/">お店ごとの当選率</a>を出しています（名前などは送りません）。</p>'
            '<div id="pushbox"></div>'
            '<button type="button" class="calbtn" id="mlcal" hidden></button>'
            '<p class="calnote" id="mlcaln" hidden>iPhoneはそのまま「カレンダーに追加」、Androidはダウンロードしたファイルを開くとカレンダーに入ります。締切の3時間前と発表日の朝9時に通知します。1件ずつならGoogleカレンダーのリンクも使えます。</p>'
            '<div id="ml"><p class="empty">読み込み中…</p></div>'
            '<p class="follow-ml">🔔 再販・在庫復活は、楽天ブックス・Amazonを1〜2分おきに見て、買えるようになった瞬間にXで知らせています。'
            '<a href="https://x.com/pokepi_tcg" target="_blank" rel="noopener">@pokepi_tcg をフォロー</a></p>'
            '<p class="small">※記録はこのスマホ・パソコンのブラウザの中だけに保存しています（ほかの人には見えません）。'
            'ブラウザの履歴やサイトのデータを消したとき、プライベートモードのとき、別のブラウザ・別の端末では表示されません。'
            '結果は必ずお店の告知・メールで確認してください。</p>'
            '<p><a href="/">← 抽選の一覧にもどる</a></p></main>'
            f'<script>var MLCFG={json.dumps({"raff": raff, "tag": tag, "souba": souba or {}}, ensure_ascii=False)};</script>'
            f'<script>{MYLIST_JS}</script></body></html>')
