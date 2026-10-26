"""
X手動投稿用の下書きページ（/x-draft.html）を作る。

・検索に載せない（noindex・robots.txtでDisallow・sitemap非掲載）
・件数や「◯時時点」はページを開いた時にブラウザ側で計算する（サイトは中身が変わった時しか再公開されないため）
・「コピー」ボタンで文面をそのままXアプリに貼れる。手動投稿はAPI料金がかからないのでリンクを自由に付けられる
"""
import json
from html import escape

GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピカード", "dragonball": "DBフュージョンワールド"}
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}

TEMPLATE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>X投稿下書き｜トレカ抽選ナビ（非公開）</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1a1a;--sub:#666;--line:#e3e5e8;--accent:#C8102E}
@media (prefers-color-scheme:dark){:root{--bg:#121416;--card:#1c1f23;--ink:#f0f0f0;--sub:#9aa0a6;--line:#2c3036}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--sub);font-size:13px;margin:0 0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.card h2{font-size:15px;margin:0 0 8px;display:flex;justify-content:space-between;align-items:center}
.card h2 small{color:var(--sub);font-weight:normal;font-size:12px}
textarea{width:100%;box-sizing:border-box;min-height:9em;border:1px solid var(--line);border-radius:8px;padding:10px;
 font:15px/1.5 inherit;background:transparent;color:var(--ink);resize:vertical}
.row{display:flex;gap:8px;margin-top:8px;align-items:center}
button{background:var(--accent);color:#fff;border:0;border-radius:999px;padding:10px 18px;font-size:15px;font-weight:bold}
button.ok{background:#2e7d32}.len{color:var(--sub);font-size:13px}.len.over{color:var(--accent);font-weight:bold}
.empty{color:var(--sub);font-size:14px}
</style></head><body>
<h1>X投稿 下書き（非公開ページ）</h1>
<p class="sub">開いた時点の件数で作っています。「コピー」→ Xアプリに貼り付けて投稿。データ更新：<span id="upd"></span></p>
<div id="cards"></div>
<script>
const SITE=__SITE__, ITEMS=__ITEMS__, UPDATED=__UPDATED__;
const GS={pokemon:"ポケカ",onepiece:"ワンピカード",dragonball:"DBフュージョンワールド"};
const SLUG={pokemon:"pokeka",onepiece:"onepiece",dragonball:"fusionworld"};
const TAG={pokemon:"#ポケカ #ポケカ抽選",onepiece:"#ワンピカード #ワンピカード抽選",dragonball:"#フュージョンワールド #DBFW"};
const W=["月","火","水","木","金","土","日"];
const now=new Date(); const H=3600*1000;
document.getElementById("upd").textContent=UPDATED?new Date(UPDATED).toLocaleString("ja-JP",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}):"-";
const end=i=>i.end?new Date(i.end):null;
const active=ITEMS.filter(i=>{const e=end(i);return !e||e>now;});
const fmt=e=>e?`${e.getMonth()+1}/${e.getDate()}(${W[(e.getDay()+6)%7]})${String(e.getHours()).padStart(2,"0")}:${String(e.getMinutes()).padStart(2,"0")}`:"公式で確認";
const name=i=>{if(i.series)return i.series;let p=(i.product||"").replace(/[（(][^）)]{8,}[）)]/g,"").trim();return p.length>30?p.slice(0,30)+"…":p;};
const xlen=t=>{let n=0;for(const w of t.split(/(\\s+)/)){if(w.startsWith("http")){n+=23;continue;}for(const c of w){n+=/[^\\x00-\\x7F]/.test(c)?2:1;}}return n;};
const cards=[];
// 1) まとめ
{
 const parts=[],tags=[];
 for(const g of Object.keys(GS)){const n=active.filter(i=>i.game===g).length;if(n){parts.push(`${GS[g]} ${n}件`);tags.push(TAG[g].split(" ")[0]);}}
 const soon=active.filter(i=>end(i)&&end(i)-now<24*H).length;
 if(parts.length){
  const t=`【トレカ抽選まとめ｜${now.getMonth()+1}/${now.getDate()} ${now.getHours()}時時点】\\n受付中：${parts.join("／")}`+(soon?`\\n⏰締切24時間以内：${soon}件`:"")+`\\n条件・締切・店舗を一覧でチェック👇\\n${SITE}/\\n${tags.join(" ")}`;
  cards.push(["まとめ投稿（サイトトップへ）","1日2〜3回おすすめ",t]);
 }
}
// 2) ゲーム別 締切間近トップ5
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&end(i)-now>1*H).sort((a,b)=>end(a)-end(b)).slice(0,5); // 1時間以内に締切のものは除く（投稿しても間に合わない）
 if(!li.length)continue;
 const t=`【${GS[g]}｜締切が近い抽選 ${now.getMonth()+1}/${now.getDate()}】\\n`+li.map(i=>`・${i.store}／${name(i)}　〜${fmt(end(i))}`).join("\\n")+`\\n全${active.filter(i=>i.game===g).length}件の一覧👇\\n${SITE}/${SLUG[g]}/\\n${TAG[g]}`;
 cards.push([`${GS[g]}：締切間近トップ5`,"締切前の夕方〜夜に",t]);
}
// 3) 新着（24時間以内に見つかったもの）
{
 const li=active.filter(i=>i.found_at&&now-new Date(i.found_at)<24*H).sort((a,b)=>new Date(b.found_at)-new Date(a.found_at)).slice(0,5);
 if(li.length){
  const t=`【新着の抽選 ${now.getMonth()+1}/${now.getDate()}】\\n`+li.map(i=>`・${GS[i.game]}｜${i.store}／${name(i)}　〜${fmt(end(i))}`).join("\\n")+`\\n条件・応募方法はこちら👇\\n${SITE}/\\n#ポケカ #ワンピカード`;
  cards.push(["新着まとめ（24時間以内）","朝に出すと反応が良い",t]);
 }
}
const root=document.getElementById("cards");
if(!cards.length)root.innerHTML='<p class="empty">いま受付中の抽選がありません。</p>';
for(const [h,hint,t] of cards){
 const d=document.createElement("div");d.className="card";
 const n=xlen(t);
 d.innerHTML=`<h2>${h}<small>${hint}</small></h2><textarea>${t.replace(/</g,"&lt;")}</textarea><div class="row"><button>コピー</button><span class="len ${n>280?"over":""}">${n}/280${n>280?"（長いので削ってください）":""}</span></div>`;
 const ta=d.querySelector("textarea"),b=d.querySelector("button");
 b.onclick=async()=>{try{await navigator.clipboard.writeText(ta.value);}catch(e){ta.select();document.execCommand("copy");}b.textContent="コピーしました";b.className="ok";setTimeout(()=>{b.textContent="コピー";b.className="";},1500);};
 ta.oninput=()=>{const m=xlen(ta.value);const s=d.querySelector(".len");s.textContent=m+"/280";s.className="len "+(m>280?"over":"");};
 root.appendChild(d);
}
</script></body></html>
"""


def build_x_draft(out, items, site, updated):
    """items: sitegen の items（受付中のみ）。/x-draft.html を書き出す"""
    keep = ("game", "store", "product", "series", "end", "found_at")
    data = [{k: i.get(k) for k in keep} for i in items]
    html = (TEMPLATE.replace("__SITE__", json.dumps(site or ""))
            .replace("__ITEMS__", json.dumps(data, ensure_ascii=False))
            .replace("__UPDATED__", json.dumps(updated or "")))
    (out / "x-draft.html").write_text(html, encoding="utf-8")
