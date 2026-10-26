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
textarea{width:100%;box-sizing:border-box;min-height:15em;border:1px solid var(--line);border-radius:8px;padding:10px;
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;background:transparent;color:var(--ink);resize:vertical}
.row{display:flex;gap:8px;margin-top:8px;align-items:center}
button{background:var(--accent);color:#fff;border:0;border-radius:999px;padding:10px 18px;font-size:15px;font-weight:bold}
button.ok{background:#2e7d32}
.xbtn{background:var(--ink);color:var(--bg);border-radius:999px;padding:10px 18px;font-size:15px;font-weight:bold;text-decoration:none}.len{color:var(--sub);font-size:13px}.len.over{color:var(--accent);font-weight:bold}
.empty{color:var(--sub);font-size:14px}
.now{display:inline-block;background:var(--accent);color:#fff;font-size:11px;border-radius:4px;padding:1px 6px;margin-right:6px;vertical-align:1px}
.card h2{gap:8px}.card h2 small{text-align:right;flex:none}
</style></head><body>
<h1>X投稿 下書き（非公開ページ）</h1>
<p class="sub">開いた時点の件数で作っています。「Xで開く」→ そのまま投稿、または閉じる時に「下書きを保存」。データ更新：<span id="upd"></span></p>
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
const name=i=>{if(i.series)return i.series;let p=(i.product||"");const q=p.match(/[「『]([^」』]{2,})[」』]/);if(q)p=q[1];
 p=p.replace(/[（(][^）)]{8,}[）)]/g,"").replace(/^(ポケモンカードゲーム|ONE PIECEカードゲーム|ドラゴンボール.{0,12}フュージョンワールド)\\s*/,"").replace(/^(MEGA\\s*)?(拡張パック|強化拡張パック|ブースターパック|プレミアムブースター)\\s*/,"").trim();
 return p.length>20?p.slice(0,20)+"…":p;};
const xlen=t=>{let n=0;for(const w of t.split(/(\\s+)/)){if(w.startsWith("http")){n+=23;continue;}for(const c of w){n+=/[^\\x00-\\x7F]/.test(c)?2:1;}}return n;};
const cards=[];
const hr=now.getHours();
const skey=i=>(i.store||"").replace(/[\\s　]/g,"");
// 同じ店舗の抽選は1行にまとめる（締切が一番早いものの時刻を出す）
const byStore=li=>{const m=new Map();for(const i of li){const k=skey(i);if(!m.has(k))m.set(k,{i,names:[]});const n=name(i);if(!m.get(k).names.includes(n))m.get(k).names.push(n);}return [...m.values()];};
const nm=x=>x.names.length>1?`${x.names[0]} ほか${x.names.length-1}種`:x.names[0];
// 投稿のおすすめ時間（時）。今の時間に合う下書きを上に並べる
const add=(h,hint,t,hours)=>{if(t)cards.push({h,hint,t,hot:(hours||[]).includes(hr)});};
// 280字（日本語は1字=2）に収まるまで行を足す
const fit=(head,lines,tail)=>{let body=[];const mk=b=>[head,"",...b,"",tail].join("\\n");for(const l of lines){if(xlen(mk([...body,l]))>280)break;body.push(l);}return body.length?mk(body):"";};
const foot=(cta,url,tags)=>`${cta}👇\\n${url}\\n\\n${tags}`;
const link=g=>`${SITE}/${SLUG[g]}/`;
const where=i=>i.channel==="store"?(i.area||"複数地域"):"ネット・発送";
const sameDay=(a,b)=>a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();
const tmr=new Date(now.getTime()+24*H);
const hm=e=>`${String(e.getHours()).padStart(2,"0")}:${String(e.getMinutes()).padStart(2,"0")}`;
const md=`${now.getMonth()+1}/${now.getDate()}`;
const REG=[["北海道・東北",/北海道|青森|岩手|宮城|秋田|山形|福島/],["関東",/東京|神奈川|埼玉|千葉|茨城|栃木|群馬/],["中部",/新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知/],["近畿",/三重|滋賀|京都|大阪|兵庫|奈良|和歌山/],["中国・四国",/鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知/],["九州・沖縄",/福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄/]];

// 1) 抽選速報（6時間以内に見つかった新しい抽選を1件ずつ。いちばん拡散されやすい型）
{
 const li=active.filter(i=>i.found_at&&now-new Date(i.found_at)<6*H&&(!end(i)||end(i)-now>2*H))
  .sort((a,b)=>new Date(b.found_at)-new Date(a.found_at))
  ;
 for(const x of byStore(li).slice(0,3)){const i=x.i;
  const t=`🚨抽選速報｜${GS[i.game]}\\n\\n「${nm(x)}」\\n\\n📍${i.store}（${where(i)}）\\n⏰${fmt(end(i))} 締切\\n\\n`+foot("応募条件・方法はこちら",i.spath?SITE+"/"+i.spath:link(i.game),TAG[i.game]);
  add(`速報：${i.store}`,"見つけてすぐ出すのが一番伸びる",t,[7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]);
 }
}
// 2) 本日締切（ゲーム別）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&sameDay(end(i),now)&&end(i)-now>1*H).sort((a,b)=>end(a)-end(b));
 if(!li.length)continue;
 add(`${GS[g]}：本日締切`,"昼〜夕方に（応募忘れの人向け）",
  fit(`⏰本日締切｜${GS[g]}の抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（${hm(end(x.i))}まで）\\n　${nm(x)}`),foot("まだ間に合います",link(g),TAG[g])),[11,12,13,14,15,16,17,18]);
}
// 3) 明日締切（ゲーム別。夜に出して「明日忘れずに」）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&sameDay(end(i),tmr)).sort((a,b)=>end(a)-end(b));
 if(!li.length)continue;
 add(`${GS[g]}：明日締切`,"夜に（翌日のリマインド）",
  fit(`📅明日締切｜${GS[g]}の抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（${hm(end(x.i))}まで）\\n　${nm(x)}`),foot("今夜のうちに応募しておこう",link(g),TAG[g])),[19,20,21,22,23]);
}
// 4) ネット抽選（発送）まとめ（全国の人が応募できるので反応が広い）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&i.channel==="online"&&(!end(i)||end(i)-now>1*H)).sort((a,b)=>(end(a)||9e15)-(end(b)||9e15));
 if(li.length<2)continue;
 add(`${GS[g]}：ネット抽選（発送）`,"全国の人に届く・いつでも",
  fit(`📦家から応募できる｜${GS[g]}のネット抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（〜${fmt(end(x.i))}）\\n　${nm(x)}`),foot("当選したら自宅に届きます",link(g),TAG[g])),[7,8,12,21,22]);
}
// 5) 地域別の店頭抽選（受付中が多い地域を上位3つ）
{
 const store=active.filter(i=>i.channel==="store"&&i.area&&(!end(i)||end(i)-now>1*H));
 const by=REG.map(([r,re])=>[r,store.filter(i=>re.test(i.area))]).filter(x=>x[1].length>=3).sort((a,b)=>b[1].length-a[1].length).slice(0,3);
 for(const [r,li] of by){
  li.sort((a,b)=>(end(a)||9e15)-(end(b)||9e15));
  add(`店頭抽選：${r}`,"地域名で検索する人に届く",
   fit(`🏪${r}の店頭抽選｜受付中 ${li.length}件`,byStore(li).map(x=>`・${x.i.area.replace(/[都府県]$/,"")}｜${x.i.store}（〜${fmt(end(x.i))}）`),foot("お近くの店舗を探す",SITE+"/",`#ポケカ抽選 #ワンピカード抽選 #${r.split("・")[0]}`)),[12,18,19,20]);
 }
}
// 6) まとめ
{
 const parts=[],tags=[];
 for(const g of Object.keys(GS)){const n=active.filter(i=>i.game===g).length;if(n){parts.push(`${GS[g]} ${n}件`);tags.push(TAG[g].split(" ")[0]);}}
 const soon=active.filter(i=>end(i)&&end(i)-now<24*H).length;
 if(parts.length){
  const t=`📋トレカ抽選まとめ｜${md} ${hr}時時点\\n\\n受付中の抽選\\n`+parts.map(x=>"・"+x).join("\\n")+(soon?`\\n\\n⏰24時間以内に締切：${soon}件`:"")+`\\n\\n`+foot("条件・締切・店舗を一覧でチェック",SITE+"/",tags.join(" "));
  add("まとめ投稿（サイトトップへ）","1日2〜3回おすすめ",t,[8,12,20]);
 }
}
// 7) ゲーム別 締切間近トップ5
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&end(i)-now>1*H).sort((a,b)=>end(a)-end(b)); // 1時間以内に締切のものは除く（投稿しても間に合わない）
 if(!li.length)continue;
 add(`${GS[g]}：締切間近トップ5`,"締切前の夕方〜夜に",
  fit(`⏳締切が近い抽選｜${GS[g]}`,byStore(li).slice(0,5).map(x=>`・${x.i.store}（〜${fmt(end(x.i))}）\\n　${nm(x)}`),foot(`受付中 全${active.filter(i=>i.game===g).length}件の一覧`,link(g),TAG[g])),[17,18,19,20,21]);
}
// 8) 弾ごと（受付中が多い弾を各ゲーム上位3つ。弾ページ＝アフィリンクのあるページへ送る）
for(const g of Object.keys(GS)){
 const by={};
 for(const i of active){if(i.game!==g||!i.series||!i.spath)continue;(by[i.series]=by[i.series]||[]).push(i);}
 const top=Object.entries(by).sort((a,b)=>b[1].length-a[1].length).slice(0,3);
 for(const [sr,li] of top){
  if(li.length<2)continue;
  const seen=new Set();const soon=li.filter(i=>end(i)&&end(i)-now>1*H).sort((a,b)=>end(a)-end(b)).filter(i=>!seen.has(skey(i))&&seen.add(skey(i)));
  add(`${GS[g]}：「${sr}」（弾ページへ）`,"狙ってる人が多い弾は反応◎",
   fit(`🎯「${sr}」の抽選まとめ\\n${GS[g]}｜受付中 ${li.length}件`,soon.map(i=>`・${i.store}（〜${fmt(end(i))}）`),foot("ほかの店舗・条件・応募方法",SITE+"/"+li[0].spath,TAG[g]))||`🎯「${sr}」の抽選まとめ\\n${GS[g]}｜受付中 ${li.length}件\\n\\n`+foot("店舗・条件・応募方法",SITE+"/"+li[0].spath,TAG[g]),[12,19,20,21]);
 }
}
// 9) 新着（24時間以内に見つかったもの）
{
 const li=active.filter(i=>i.found_at&&now-new Date(i.found_at)<24*H).sort((a,b)=>new Date(b.found_at)-new Date(a.found_at));
 if(li.length)add("新着まとめ（24時間以内）","朝に出すと反応が良い",
  fit(`🆕新着の抽選｜${md}（${li.length}件）`,byStore(li).map(x=>`・${x.i.store}（${GS[x.i.game]}）\\n　${nm(x)}`),foot("締切・条件・応募方法はこちら",SITE+"/","#ポケカ #ワンピカード")),[7,8,9]);
}
// 今の時間におすすめの下書きを上に（同じ中では元の順）
cards.sort((a,b)=>(b.hot?1:0)-(a.hot?1:0));
const root=document.getElementById("cards");
if(!cards.length)root.innerHTML='<p class="empty">いま受付中の抽選がありません。</p>';
for(const {h,hint,t,hot} of cards){
 const d=document.createElement("div");d.className="card";
 const n=xlen(t);
 d.innerHTML=`<h2><span>${hot?'<b class="now">今おすすめ</b>':""}${h}</span><small>${hint}</small></h2><textarea>${t.replace(/</g,"&lt;")}</textarea><div class="row"><a class="xbtn" target="_blank" rel="noopener">Xで開く</a><button>コピー</button><span class="len ${n>280?"over":""}">${n}/280${n>280?"（長いので削ってください）":""}</span></div>`;
 const ta=d.querySelector("textarea"),b=d.querySelector("button");
 const xa=d.querySelector(".xbtn");const setX=()=>{xa.href="https://x.com/intent/post?text="+encodeURIComponent(ta.value);};setX();
 b.onclick=async()=>{try{await navigator.clipboard.writeText(ta.value);}catch(e){ta.select();document.execCommand("copy");}b.textContent="コピーしました";b.className="ok";setTimeout(()=>{b.textContent="コピー";b.className="";},1500);};
 ta.oninput=()=>{setX();const m=xlen(ta.value);const s=d.querySelector(".len");s.textContent=m+"/280";s.className="len "+(m>280?"over":"");};
 root.appendChild(d);
}
</script></body></html>
"""


def build_x_draft(out, items, site, updated):
    """items: sitegen の items（受付中のみ）。/x-draft.html を書き出す"""
    from sitegen import series_path  # 弾ページのURL（sitegen から呼ばれるので読み込み済み）
    keep = ("game", "store", "product", "series", "end", "found_at", "channel", "area")
    data = []
    for i in items:
        row = {k: i.get(k) for k in keep}
        if i.get("series"):
            row["spath"] = series_path(i["game"], i["series"])
        data.append(row)
    html = (TEMPLATE.replace("__SITE__", json.dumps(site or ""))
            .replace("__ITEMS__", json.dumps(data, ensure_ascii=False))
            .replace("__UPDATED__", json.dumps(updated or "")))
    (out / "x-draft.html").write_text(html, encoding="utf-8")
