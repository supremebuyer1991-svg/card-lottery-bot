"""
X手動投稿用の下書きページ（/x-draft.html）を作る。

・検索に載せない（noindex・robots.txtでDisallow・sitemap非掲載）
・件数や「◯時時点」はページを開いた時にブラウザ側で計算する（サイトは中身が変わった時しか再公開されないため）
・「コピー」ボタンで文面をそのままXアプリに貼れる。手動投稿はAPI料金がかからないのでリンクを自由に付けられる
"""
import json
import re
from html import escape

GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "DBフュージョンワールド"}
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}

TEMPLATE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<script>if(/\\.pages\\.dev$/.test(location.hostname))location.replace("https://tcg-chusen.com"+location.pathname+location.search)</script>
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
.tabs{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;padding:8px 0;margin:0 0 10px;background:var(--bg);scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:none;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:7px 12px;font-size:14px;font-weight:bold}
.tabs button span{margin-left:5px;font-size:12px;color:var(--sub);font-weight:normal}
.tabs button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.tabs button[aria-pressed="true"] span{color:#fff}
[hidden]{display:none!important}
.mk summary{font-weight:bold;cursor:pointer}.mk #mk-out .card{margin:12px 0 0}
.shot{margin:10px 0 0}.shot img{width:100%;max-width:200px;border-radius:10px;border:1px solid var(--line);display:block}.shot figcaption{color:var(--sub);font-size:12px;margin-top:4px}
.basis{color:var(--sub);font-size:13px;margin:8px 0 0}.basis a{color:var(--accent)}
.now{display:inline-block;background:var(--accent);color:#fff;font-size:11px;border-radius:4px;padding:1px 6px;margin-right:6px;vertical-align:1px}
.card h2{gap:8px}.card h2 small{text-align:right;flex:none}
</style></head><body>
<h1>X投稿 下書き（非公開ページ）</h1>
<p class="sub">開いた時点の件数で作っています。「Xで開く」→ そのまま投稿、または閉じる時に「下書きを保存」。データ更新：<span id="upd"></span></p>
<details class="card mk" id="mk"><summary>📈 今日の相場をつくる（スニダンの共有文を貼る）</summary>
<p class="sub">スニダンのアプリで商品ごとに「共有」→「コピー」して、ここにまとめて貼ってください。前日比は、前の日にここで貼った値段と比べます。</p>
<textarea id="mk-in" placeholder="ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」ボックス&#10;現在価格: ¥25,300~&#10;…&#10;https://snkrdunk.com/apparels/881421?ref=share"></textarea>
<div class="row"><button type="button" id="mk-go">相場の投稿をつくる</button><span class="len" id="mk-msg"></span></div>
<div id="mk-out"></div></details>
<div id="cards"></div>
<script>
const MKP=__MKPRODUCTS__;
const SITE=__SITE__, ITEMS=__ITEMS__, UPDATED=__UPDATED__, TRENDS=__TRENDS__, IMGS=new Set(__IMGS__), BUZZ=__BUZZ__, MARKET=__MARKET__;
const GS={pokemon:"ポケカ",onepiece:"ワンピースカード",dragonball:"DBフュージョンワールド"};
const SLUG={pokemon:"pokeka",onepiece:"onepiece",dragonball:"fusionworld"};
const TAG={pokemon:"#ポケカ #ポケカ抽選",onepiece:"#ワンピースカード #ワンピースカード抽選",dragonball:"#フュージョンワールド #DBFW"};
const W=["月","火","水","木","金","土","日"];
const now=new Date(); const H=3600*1000;
document.getElementById("upd").textContent=UPDATED?new Date(UPDATED).toLocaleString("ja-JP",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}):"-";
const end=i=>i.end?new Date(i.end):null;
const active=ITEMS.filter(i=>{const e=end(i);return !e||e>now;});
const fmt=e=>e?`${e.getMonth()+1}/${e.getDate()}(${W[(e.getDay()+6)%7]})${String(e.getHours()).padStart(2,"0")}:${String(e.getMinutes()).padStart(2,"0")}`:"公式で確認";
const name=i=>{if(i.series)return i.series;let p=(i.product||"");const q=p.match(/[「『]([^」』]{2,})[」』]/);if(q)p=q[1];
 p=p.replace(/[（(][^）)]{8,}[）)]/g,"").replace(/^(ポケモンカードゲーム|ONE PIECEカードゲーム|ドラゴンボール.{0,12}フュージョンワールド)\\s*/,"").replace(/^(MEGA\\s*)?(拡張パック|強化拡張パック|ブースターパック|プレミアムブースター)\\s*/,"").trim();
 return p.length>20?p.slice(0,20)+"…":p;};
// 予約投稿の画像に入れる「応募のしかた・受け取り方」と「必要なもの」（Claudeの予約作業が使う。条件が増えたらここだけ直す）
const STORECC=/ゴールドポイントカード・?プラス|ビックカメラSuica|イオンカード|エディオンカード|JQ\\s*CARD|(クレジット|クレカ)カード?.{0,4}(会員|をお持ち|お持ちの|所持|保有|限定|ご利用の方|入会)|(当社|店舗|提携)(の)?クレジット/;
window.condX=i=>{const tg=(i.tags||[]).join(" ");const m=(i.method||"")+" "+tg;const t=tg+" "+(i.conditions||"");
 const how=/SNS|X抽選|ポスト|リポスト/.test(m)?"SNS応募":/アプリ/.test(m)?"アプリ応募":/店頭|整理券|抽選券/.test(m)?"店頭応募":"Web応募";
 const get=i.channel==="store"?"店頭受取":"通販（発送）";const q=[];
 if(i.id_check===true)q.push("本人確認");
 if(i.member==="card"||/会員カード|会員証/.test(t))q.push("店の会員カード");else if(i.member==="account"||/会員登録|会員限定/.test(t))q.push("会員登録");
 if(/購入(履歴|実績|歴)|利用(履歴|実績)/.test(t))q.push("購入履歴");if(/レシート/.test(t))q.push("レシート");
 if(/店舗クレカ/.test(tg)||STORECC.test(t))q.push("店のクレカ");
 const unk=i.id_check==null||!i.member;
 return [how+"・"+get,q.length?"必要："+q.join("・")+(unk?"・ほか要確認":""):(unk?"条件は応募ページで確認":"")];};
const xlen=t=>{let n=0;for(const w of t.split(/(\\s+)/)){if(w.startsWith("http")){n+=23;continue;}for(const c of w){n+=/[^\\x00-\\x7F]/.test(c)?2:1;}}return n;};
const cards=[];
const hr=now.getHours();
const skey=i=>(i.store||"").replace(/[\\s　]/g,"");
// 同じ店舗の抽選は1行にまとめる（締切が一番早いものの時刻を出す）
const byStore=li=>{const m=new Map();for(const i of li){const k=skey(i);if(!m.has(k))m.set(k,{i,names:[]});const n=name(i);if(!m.get(k).names.includes(n))m.get(k).names.push(n);}return [...m.values()];};
const nm=x=>x.names.length>1?`${x.names[0]} ほか${x.names.length-1}種`:x.names[0];
// 投稿のおすすめ時間（時）。今の時間に合う下書きを上に並べる
const add=(h,hint,t,hours,img,src)=>{if(t)cards.push({h,hint,t,hot:(hours||[]).includes(hr),img,src:(src||[]).filter(i=>i.store&&t.includes(i.store))});};
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
  const t=`🚨抽選速報｜${GS[i.game]}\\n\\n「${nm(x)}」\\n\\n📍${i.store}（${where(i)}）\\n⏰${fmt(end(i))} 締切\\n\\n`+foot("応募条件・方法はこちら",i.lpath?SITE+"/"+i.lpath:i.spath?SITE+"/"+i.spath:link(i.game),TAG[i.game]);
  add(`速報：${i.store}`,"見つけてすぐ出すのが一番伸びる",t,[7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23],null,[i]);
 }
}
// 2) 本日締切（ゲーム別）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&sameDay(end(i),now)&&end(i)-now>1*H).sort((a,b)=>end(a)-end(b));
 if(!li.length)continue;
 add(`${GS[g]}：本日締切`,"昼〜夕方に（応募忘れの人向け）",
  fit(`⏰本日締切｜${GS[g]}の抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（${hm(end(x.i))}まで）\\n　${nm(x)}`),foot("まだ間に合います",link(g),TAG[g])),[11,12,13,14,15,16,17,18],`today-${g}`,li);
}
// 3) 明日締切（ゲーム別。夜に出して「明日忘れずに」）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&end(i)&&sameDay(end(i),tmr)).sort((a,b)=>end(a)-end(b));
 if(!li.length)continue;
 add(`${GS[g]}：明日締切`,"夜に（翌日のリマインド）",
  fit(`📅明日締切｜${GS[g]}の抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（${hm(end(x.i))}まで）\\n　${nm(x)}`),foot("今夜のうちに応募しておこう",link(g),TAG[g])),[19,20,21,22,23],`tomorrow-${g}`,li);
}
// 4) ネット抽選（発送）まとめ（全国の人が応募できるので反応が広い）
for(const g of Object.keys(GS)){
 const li=active.filter(i=>i.game===g&&i.channel==="online"&&(!end(i)||end(i)-now>1*H)).sort((a,b)=>(end(a)||9e15)-(end(b)||9e15));
 if(li.length<2)continue;
 add(`${GS[g]}：ネット抽選（発送）`,"全国の人に届く・いつでも",
  fit(`📦家から応募できる｜${GS[g]}のネット抽選 ${li.length}件`,byStore(li).map(x=>`・${x.i.store}（〜${fmt(end(x.i))}）\\n　${nm(x)}`),foot("当選したら自宅に届きます",link(g),TAG[g])),[7,8,12,21,22],`net-${g}`,li);
}
// 5) 地域別の店頭抽選（受付中が多い地域を上位3つ）
{
 const store=active.filter(i=>i.channel==="store"&&i.area&&(!end(i)||end(i)-now>1*H));
 const by=REG.map(([r,re])=>[r,store.filter(i=>re.test(i.area))]).filter(x=>x[1].length>=3).sort((a,b)=>b[1].length-a[1].length).slice(0,3);
 for(const [r,li] of by){
  li.sort((a,b)=>(end(a)||9e15)-(end(b)||9e15));
  add(`店頭抽選：${r}`,"地域名で検索する人に届く",
   fit(`🏪${r}の店頭抽選｜受付中 ${li.length}件`,byStore(li).map(x=>`・${x.i.area.replace(/[都府県]$/,"")}｜${x.i.store}（〜${fmt(end(x.i))}）`),foot("お近くの店舗を探す",SITE+"/",`#ポケカ抽選 #ワンピースカード抽選 #${r.split("・")[0]}`)),[12,18,19,20],null,li);
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
  fit(`⏳締切が近い抽選｜${GS[g]}`,byStore(li).slice(0,5).map(x=>`・${x.i.store}（〜${fmt(end(x.i))}）\\n　${nm(x)}`),foot(`受付中 全${active.filter(i=>i.game===g).length}件の一覧`,link(g),TAG[g])),[17,18,19,20,21],`soon-${g}`,li);
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
   fit(`🎯「${sr}」の抽選まとめ\\n${GS[g]}｜受付中 ${li.length}件`,soon.map(i=>`・${i.store}（〜${fmt(end(i))}）`),foot("ほかの店舗・条件・応募方法",SITE+"/"+li[0].spath,TAG[g]))||`🎯「${sr}」の抽選まとめ\\n${GS[g]}｜受付中 ${li.length}件\\n\\n`+foot("店舗・条件・応募方法",SITE+"/"+li[0].spath,TAG[g]),[12,19,20,21],null,li);
 }
}
// 9) 新着（24時間以内に見つかったもの）
{
 const li=active.filter(i=>i.found_at&&now-new Date(i.found_at)<24*H).sort((a,b)=>new Date(b.found_at)-new Date(a.found_at));
 if(li.length)add("新着まとめ（24時間以内）","朝に出すと反応が良い",
  fit(`🆕新着の抽選｜${md}（${li.length}件）`,byStore(li).map(x=>`・${x.i.store}（${GS[x.i.game]}）\\n　${nm(x)}`),foot("締切・条件・応募方法はこちら",SITE+"/","#ポケカ #ワンピースカード")),[7,8,9],"fresh",li);
}
// 0) 自分で追加した抽選（config/manual.yaml）。本文はリンクなし＋リプ欄に個別ページのURL
const GX={pokemon:"ポケカ",onepiece:"ワンピースカード",dragonball:"フュージョンワールド"};
const TGX={pokemon:"#ポケカ #ポケカ抽選",onepiece:"#ワンピースカード",dragonball:"#フュージョンワールド"};
const manualCards=[];
for(const i of active.filter(i=>i.manual&&i.lpath)){
 const st=(i.store||"").replace(/[（(].*$/,"").trim(),s0=i.start?new Date(i.start):null,e=end(i);
 const head=s0&&s0>now?(sameDay(s0,now)?`本日${s0.getHours()}時スタート🔥`:`${s0.getMonth()+1}/${s0.getDate()}(${W[(s0.getDay()+6)%7]})${s0.getHours()}時スタート`):e&&sameDay(e,now)?"⏰本日締切！":"受付中🔥";
 const L=[`【${st} ${GX[i.game]}抽選】`,head,""];
 L.push("🗓 応募期間",(s0?fmt(s0):"")+"〜"+fmt(e),"");
 if(i.conditions)L.push("📱 "+i.conditions,"");
 if((i.products||[]).length){L.push("📦 対象商品");for(const p of i.products)L.push("・"+p.replace(/^(ブースターパック|エクストラブースター|プレミアムブースター|拡張パック|強化拡張パック)\\s*/,""));L.push("");}
 else L.push("📦 "+(i.product||""),"");
 if(i.announce)L.push("🎯 当選発表："+i.announce);
 if(i.buy)L.push("🛒 購入期間："+i.buy);
 L.push("","詳細・応募ページはリプ欄👇","",TGX[i.game]+" #"+st.replace(/[\\s　]/g,"")+" #抽選");
 manualCards.push({h:`📝 ${st}（個別ページ付き）`,hint:"① 本文（リンクなし・長文）",t:L.join("\\n").replace(/\\n{3,}/g,"\\n\\n"),hot:true,long:true,src:[i]});
 manualCards.push({h:`↳ ${st}：リプ欄に貼る`,hint:"② 投稿したら自分のポストに返信",t:`📌詳細・応募ページはこちら👇\\n${SITE}/${i.lpath}`,hot:false});
}
// --- 今日の相場（スニダンの共有文から） ---
function mkCard(h,hint,t){
 const d=document.createElement("div");d.className="card";const n=xlen(t);
 d.innerHTML=`<h2><span>${h}</span><small>${hint}</small></h2><textarea></textarea><div class="row"><a class="xbtn" target="_blank" rel="noopener">Xで開く</a><button>コピー</button><span class="len ${n>280?"over":""}">${n}/280</span></div>`;
 const ta=d.querySelector("textarea"),b=d.querySelector("button"),xa=d.querySelector(".xbtn");ta.value=t;
 const setX=()=>{xa.href="https://x.com/intent/post?text="+encodeURIComponent(ta.value);};setX();
 b.onclick=async()=>{try{await navigator.clipboard.writeText(ta.value);}catch(e){ta.select();document.execCommand("copy");}b.textContent="コピーしました";setTimeout(()=>{b.textContent="コピー";},1500);};
 ta.oninput=()=>{setX();const m=xlen(ta.value);const s=d.querySelector(".len");s.textContent=m+"/280";s.className="len "+(m>280?"over":"");};
 return d;
}
function mkParse(src){
 const segs=src.split(/現在価格\\s*[:：]/);const out=[];
 for(let k=1;k<segs.length;k++){
  const before=segs[k-1].split("\\n").map(s=>s.trim()).filter(s=>s&&!s.startsWith("#")&&!/https?:|招待コード|商品詳細/.test(s));
  const raw=before[before.length-1]||"";const pm=segs[k].match(/[¥￥]\\s*([0-9,]+)/);const im=segs[k].match(/apparels\\/(\\d+)/);
  if(!pm)continue;
  const price=parseInt(pm[1].replace(/,/g,""),10);
  let p=MKP.find(x=>im&&x.id===im[1])||MKP.find(x=>raw.includes(x.name));
  const name=p?p.name:raw.replace(/ポケモンカードゲーム|ONE PIECEカードゲーム|MEGA|拡張パック|ブースターパック|[「」『』]/g,"").replace(/ボックス/g,"").trim();
  const game=p?p.game:(/ONE ?PIECE|ワンピ/i.test(raw)?"onepiece":"pokemon");
  out.push({key:p?p.name:name,name:p&&p.label?p.label:name,kind:p?p.kind:(/ボックス|BOX/i.test(raw)?"BOX":""),msrp:p?p.msrp:null,price,game});
 }
 return out;
}
document.getElementById("mk-go").onclick=()=>{
 const rows=mkParse(document.getElementById("mk-in").value),msg=document.getElementById("mk-msg"),box=document.getElementById("mk-out");box.innerHTML="";
 if(!rows.length){msg.textContent="「現在価格」が見つかりません。共有の文をそのまま貼ってください";return;}
 const _d=new Date(),today=`${_d.getFullYear()}-${String(_d.getMonth()+1).padStart(2,"0")}-${String(_d.getDate()).padStart(2,"0")}`;let hist={};try{hist=JSON.parse(localStorage.getItem("mk_hist")||"{}");}catch(e){}
 const prevDay=Object.keys(hist).filter(d=>d<today).sort().pop();const prev=prevDay?hist[prevDay]:{};
 hist[today]=Object.assign(hist[today]||{},Object.fromEntries(rows.map(r=>[r.key,r.price])));
 const keep=Object.keys(hist).sort().slice(-60);hist=Object.fromEntries(keep.map(d=>[d,hist[d]]));try{localStorage.setItem("mk_hist",JSON.stringify(hist));}catch(e){}
 const TG={pokemon:"#ポケカ #ポケカ相場",onepiece:"#ワンピースカード #ワンピースカード相場",dragonball:"#フュージョンワールド"};
 const sg=v=>v===0?"±0":(v>0?"+":"-")+Math.abs(v).toLocaleString();
 for(const g of Object.keys(GS)){
  const li=rows.filter(r=>r.game===g);if(!li.length)continue;
  const lines=li.map(r=>{const lb=(!r.kind||r.name.endsWith(r.kind))?r.name:`${r.name} ${r.kind}`;const df=prev[r.key]!=null?r.price-prev[r.key]:null;
   return lb+(r.msrp?`　定価${r.msrp.toLocaleString()}円`:"")+`\\n→ ${r.price.toLocaleString()}円`+(df!=null?`（前日比 ${sg(df)}）`:"");});
  const head=`📈今日の相場｜${GS[g]}（${now.getMonth()+1}/${now.getDate()}）`,tail=`スニダン調べ\\n\\n${TG[g]}`;
  const mk=b=>head+"\\n\\n"+b.join("\\n")+"\\n\\n"+tail;const parts=[[]];
  for(const l of lines){if(parts[parts.length-1].length&&xlen(mk([...parts[parts.length-1],l]))>280)parts.push([]);parts[parts.length-1].push(l);}
  parts.forEach((b,k)=>box.appendChild(mkCard(`📈今日の相場：${GS[g]}${parts.length>1?`（その${k+1}）`:""}`,"貼った値段から作成",mk(b))));
 }
 msg.textContent=`${rows.length}件の値段を読み取りました`+(prevDay?`（前日比は${prevDay.slice(5).replace("-","/")}と比較）`:"（前日比は明日から）");
};
// それぞれの情報をいつ見つけたか（古い情報を「速報」で出さないように）
const ago=d=>{const m=Math.round((now-d)/60000);return m<60?`${Math.max(m,0)}分前`:m<48*60?`${Math.floor(m/60)}時間前`:`${Math.floor(m/1440)}日前`;};
const fdt=d=>`${d.getMonth()+1}/${d.getDate()}(${W[(d.getDay()+6)%7]})${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
function foundHtml(src){
 const seen=new Set(),li=(src||[]).filter(i=>i.found_at&&!seen.has(skey(i))&&seen.add(skey(i))).map(i=>[i,new Date(i.found_at)]).sort((a,b)=>b[1]-a[1]);
 if(!li.length)return"";
 const one=([i,d])=>`${(i.store||"").replace(/</g,"&lt;")}：${fdt(d)}（${ago(d)}）`;
 if(li.length===1)return`<p class="basis">🕒 情報を見つけた時刻　${one(li[0])}</p>`;
 return`<details class="basis"><summary>🕒 情報を見つけた時刻　${fdt(li[li.length-1][1])}〜${fdt(li[0][1])}（${li.length}店）</summary>${li.map(x=>"<div>・"+one(x)+"</div>").join("")}</details>`;
}
// 今の時間におすすめの下書きを上に（同じ中では元の順）
cards.sort((a,b)=>(b.hot?1:0)-(a.hot?1:0));
// 話題ネタ（AIの下書き。リンクなし。内容を確認してから投稿）は一番上に
const tr=(TRENDS.items||[]).map((x,k)=>({...x,_k:k})).reverse();
for(const x of tr)cards.unshift({img:`trend-${x._k}`,h:`🔥話題ネタ：${(x.topic||"").replace(/</g,"&lt;")}`,hint:x.type,t:x.text,hot:false,trend:x});
// リンクなしの「ひとこと投稿」（今日の型が先頭）。話題ネタの次に並べる
const BN={ranking:"弾のランキング",question:"店舗数",numbers:"全国の件数",prefecture:"都道府県ランキング",aruaru:"あるある"};
cards.splice(tr.length,0,...MARKET.map(m=>({h:`📈今日の相場：${GS[m.game]}${m.part?`（その${m.part}）`:""}`,hint:"1日1回・朝〜昼に",t:m.t||m.text,hot:[8,9,10,11,12].includes(hr),img:`market-${m.game}`})));
cards.splice(tr.length+MARKET.length,0,...BUZZ.map((b,k)=>({h:`💬ひとこと：${BN[b.kind]||b.kind}`,hint:k?"リンクなし":"リンクなし・今日のおすすめ",t:b.text,hot:false,img:`buzz-${b.kind}`})));
cards.unshift(...manualCards);
const root=document.getElementById("cards");
const catOf=h=>/^(📝|↳)/.test(h)?"手動追加":/速報/.test(h)?"速報":/新着/.test(h)?"新着":/本日締切/.test(h)?"本日締切":/明日締切/.test(h)?"明日締切":/締切間近/.test(h)?"締切間近":
 /ネット抽選/.test(h)?"ネット":/店頭抽選：/.test(h)?"地域":/弾ページ/.test(h)?"弾":/相場/.test(h)?"相場":/ひとこと/.test(h)?"ひとこと":/話題ネタ/.test(h)?"話題":/まとめ投稿/.test(h)?"まとめ":"その他";
if(tr.length){const p=document.createElement("p");p.className="sub";p.innerHTML=`🔥話題ネタは、Xで反応が多いポストからAIが作った下書きです（${TRENDS.generated?new Date(TRENDS.generated).toLocaleString("ja-JP",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}):""}作成）。<b>元のポストを見て、内容が合っているか確認してから</b>投稿してください。`;root.before(p);}
if(!cards.length)root.innerHTML='<p class="empty">いま受付中の抽選がありません。</p>';
for(const {h,hint,t,hot,trend,img,long,src} of cards){
 const d=document.createElement("div");d.className="card";
 const n=xlen(t);
 d.innerHTML=`<h2><span>${hot?'<b class="now">今おすすめ</b>':""}${h}</span><small>${hint}</small></h2><textarea>${t.replace(/</g,"&lt;")}</textarea>${trend?`<p class="basis">元ネタ：${(trend.basis||"").replace(/</g,"&lt;")}${(trend.src||[]).map((u,k)=>` <a href="${u}" target="_blank" rel="noopener">元のポスト${k+1}</a>`).join("")}</p>`:""}${img&&IMGS.has(img)?`<figure class="shot"><img src="x-img/${img}.png?v=${encodeURIComponent(UPDATED)}" alt="投稿用の画像" loading="lazy"><figcaption>画像を長押し →「写真に保存」→ 投稿する時に添付</figcaption></figure>`:""}${foundHtml(src)}<div class="row"><a class="xbtn" target="_blank" rel="noopener">Xで開く</a><button>コピー</button><span class="len ${n>280&&!long?"over":""}">${long?n+"字（長文・Premium）":n+"/280"+(n>280?"（長いので削ってください）":"")}</span></div>`;
 const ta=d.querySelector("textarea"),b=d.querySelector("button");
 const xa=d.querySelector(".xbtn");const setX=()=>{xa.href="https://x.com/intent/post?text="+encodeURIComponent(ta.value);};setX();
 b.onclick=async()=>{try{await navigator.clipboard.writeText(ta.value);}catch(e){ta.select();document.execCommand("copy");}b.textContent="コピーしました";b.className="ok";setTimeout(()=>{b.textContent="コピー";b.className="";},1500);};
 ta.oninput=()=>{setX();const m=xlen(ta.value);const s=d.querySelector(".len");s.textContent=long?m+"字（長文・Premium）":m+"/280";s.className="len "+(m>280&&!long?"over":"");};
 d.dataset.cat=catOf(h);d.dataset.hot=hot?"1":"";
 root.appendChild(d);
}
// --- 種類ごとのタブ（押すとその種類の下書きだけ表示） ---
(function(){
 const all=[...root.querySelectorAll(".card")];if(!all.length)return;
 const order=["速報","新着","本日締切","明日締切","締切間近","ネット","地域","弾","まとめ","相場","ひとこと","手動追加","話題","その他"];
 const cnt={};all.forEach(c=>{cnt[c.dataset.cat]=(cnt[c.dataset.cat]||0)+1;});
 const hotN=all.filter(c=>c.dataset.hot).length;
 const tabs=[...(hotN?[["hot","今おすすめ",hotN]]:[]),...order.filter(k=>cnt[k]).map(k=>[k,k,cnt[k]]),["all","すべて",all.length]];
 const bar=document.createElement("nav");bar.className="tabs";
 bar.innerHTML=tabs.map(([k,l,n])=>`<button type="button" data-k="${k}">${l}<span>${n}</span></button>`).join("");
 root.before(bar);
 const show=k=>{all.forEach(c=>{c.hidden=!(k==="all"||(k==="hot"?c.dataset.hot:c.dataset.cat===k));});
  bar.querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.k===k)));
  try{localStorage.setItem("xd_tab",k);}catch(e){}};
 bar.onclick=e=>{const b=e.target.closest("button");if(!b)return;show(b.dataset.k);window.scrollTo({top:bar.offsetTop-8});};
 let first;try{first=localStorage.getItem("xd_tab");}catch(e){}
 if(!tabs.some(t=>t[0]===first))first=tabs[0][0];
 show(first);
})();
</script></body></html>
"""


def _trends():
    """話題ネタの下書き（2日以上前のものは出さない）"""
    from common import load_json, parse_dt, now
    d = load_json("x_trends.json", {})
    g = parse_dt(d.get("generated"))
    if not g or (now() - g).total_seconds() > 36 * 3600:
        return {}
    return {"generated": d["generated"], "items": d.get("items", [])}


WEEK = "月火水木金土日"


def _name(i):
    """JS の name() と同じ短い商品名"""
    import re
    if i.get("series"):
        return i["series"]
    p = i.get("product") or ""
    q = re.search(r"[「『]([^」』]{2,})[」』]", p)
    if q:
        p = q.group(1)
    p = re.sub(r"[（(][^）)]{8,}[）)]", "", p)
    p = re.sub(r"^(ポケモンカードゲーム|ONE PIECEカードゲーム|ドラゴンボール.{0,12}フュージョンワールド)\s*", "", p)
    p = re.sub(r"^(MEGA\s*)?(拡張パック|強化拡張パック|ブースターパック|プレミアムブースター)\s*", "", p).strip()
    return p[:20] + "…" if len(p) > 20 else p


def _rows(li, end_of):
    """同じ店は1行に。[(左の締切, 店名, 商品)]"""
    import re
    from common import now
    m = {}
    for i in li:
        k = re.sub(r"\s", "", i.get("store") or "")
        if k not in m:
            m[k] = (i, [])
        n = _name(i)
        if n not in m[k][1]:
            m[k][1].append(n)
    out, t = [], now()
    for i, names in m.values():
        e = end_of(i)
        if not e:
            left = "締切\n公式で確認"
        elif e.date() == t.date():
            left = f"今日\n{e:%H:%M}"
        elif (e.date() - t.date()).days == 1:
            left = f"明日\n{e:%H:%M}"
        else:
            left = f"{e.month}/{e.day}({WEEK[e.weekday()]})\n{e:%H:%M}"
        out.append((left, i.get("store") or "", names[0] + (f" ほか{len(names) - 1}種" if len(names) > 1 else "")))
    return out


def build_images(out, items):
    """下書きに付ける画像（/x-img/*.png）。キーは下書きページの JS と合わせる"""
    import ximage
    from datetime import timedelta
    from common import now, parse_dt, load_json
    d = out / "x-img"
    d.mkdir(exist_ok=True)
    for f in d.glob("*.png"):
        f.unlink()
    t = now()
    end = lambda i: parse_dt(i.get("end"))
    act = [i for i in items if not end(i) or end(i) > t]
    made = []

    def save(key, *a, **k):
        try:
            (d / f"{key}.png").write_bytes(ximage.render(*a, **k))
            made.append(key)
        except Exception as e:
            from common import log
            log(f"下書き画像 {key}: 失敗 {e}")

    for g, short in GAME_SHORT.items():
        gi = [i for i in act if i.get("game") == g]
        later = lambda i: end(i) and end(i) - t > timedelta(hours=1)
        for key, kick, cond, sub in (
                ("today", "本日締切", lambda i: later(i) and end(i).date() == t.date(), "まだ間に合う抽選（締切が早い順）"),
                ("tomorrow", "明日締切", lambda i: end(i) and end(i).date() == (t + timedelta(days=1)).date(), "今夜のうちに応募しておこう"),
                ("soon", "締切間近", later, "締切が早い順"),
                ("net", "ネット抽選", lambda i: i.get("channel") == "online" and (not end(i) or later(i)), "家から応募・当選したら発送")):
            li = sorted([i for i in gi if cond(i)], key=lambda i: end(i) or t + timedelta(days=999))
            rows = _rows(li, end)
            if rows:
                save(f"{key}-{g}", "list", f"{short}の抽選 {len(li)}件", rows, kicker=kick, sub=sub)
    fresh = sorted([i for i in act if parse_dt(i.get("found_at")) and t - parse_dt(i["found_at"]) < timedelta(hours=24)],
                   key=lambda i: parse_dt(i["found_at"]), reverse=True)
    if fresh:
        save("fresh", "list", f"新着の抽選 {len(fresh)}件", _rows(fresh, end), kicker="新着", sub="24時間以内に見つかった抽選")
    market = []
    try:  # 今日の相場（スニダン）
        import market as mk
        from xpost import x_len
        tags = {"pokemon": "#ポケカ #ポケカ相場", "onepiece": "#ワンピースカード #ワンピースカード相場", "dragonball": "#フュージョンワールド"}
        for g, short in GAME_SHORT.items():
            rows, d0 = mk.today_rows(g)
            if not rows:
                continue
            dd = parse_dt(d0 + "T00:00:00+09:00")
            sign = lambda v: "±0" if v == 0 else f"{v:+,}"
            label = lambda n, k: n if (not k or n.endswith(k)) else f"{n} {k}"
            lines = [label(n, k) + (f"　定価{m:,}円" if m else "") + f"\n→ {v:,}円" + (f"（前日比 {sign(df)}）" if df is not None else "")
                     for n, k, m, v, df, _ in rows]
            head, tail = f"📈今日の相場｜{short}（{dd.month}/{dd.day}）", f"スニダン調べ\n\n{tags.get(g, '')}"
            body = []
            mk_t = lambda b: head + "\n\n" + "\n".join(b) + "\n\n" + tail
            parts = [[]]  # 280字に入らなければ2つ目の投稿に分ける
            for l in lines:
                if parts[-1] and x_len(mk_t(parts[-1] + [l])) > 280:
                    parts.append([])
                parts[-1].append(l)
            texts = [mk_t(b) for b in parts]
            save(f"market-{g}", "list", f"{short}の今日の相場", [
                ("前日比\n" + (sign(df) if df is not None else "-"), label(n, k), f"相場 {v:,}円" + (f" ／ 定価 {m:,}円" if m else ""))
                for n, k, m, v, df, _ in rows], kicker="今日の相場", sub="スニダンの最安値（新品）")
            for k, tx in enumerate(texts):
                market.append({"game": g, "text": tx, "part": k + 1 if len(texts) > 1 else 0})
    except Exception as e:
        from common import log
        log(f"相場の下書き: 失敗 {e}")
    buzz = []
    try:  # リンクなしの「ひとこと投稿」（5つの型）
        import xbuzz
        from common import load_settings
        for kind, text, png in xbuzz.all_buzz(load_json("lotteries.json", {}), load_settings()):
            if png:
                (d / f"buzz-{kind}.png").write_bytes(png)
                made.append(f"buzz-{kind}")
            buzz.append({"kind": kind, "text": text})
    except Exception as e:
        from common import log
        log(f"ひとこと投稿の下書き: 失敗 {e}")
    for k, x in enumerate((load_json("x_trends.json", {}).get("items") or [])[:6]):
        lines = [l for l in x.get("text", "").split("\n") if l.strip() and not l.strip().startswith("#")]
        if lines:
            save(f"trend-{k}", "text", x.get("topic") or lines[0], lines[:4], kicker=x.get("type") or "話題")
    return made, buzz, market


def build_x_draft(out, items, site, updated):
    """items: sitegen の items（受付中のみ）。/x-draft.html を書き出す"""
    from sitegen import series_path  # 弾ページのURL（sitegen から呼ばれるので読み込み済み）
    keep = ("game", "store", "product", "series", "end", "found_at", "channel", "area", "lpath", "manual",
            "start", "products", "announce", "buy", "conditions", "id_check", "member", "method", "tags")  # 画像に応募条件を入れる
    data = []
    for i in items:
        row = {k: i.get(k) for k in keep}
        if i.get("series"):
            row["spath"] = series_path(i["game"], i["series"])
        data.append(row)
    try:
        imgs, buzz, market = build_images(out, items)
    except Exception as e:
        from common import log
        log(f"下書き画像: スキップ {e}")
        imgs, buzz, market = [], [], []
    try:
        import market as mk
        mkp = [{"game": p.get("game"), "name": p["name"], "label": p.get("label") or "", "kind": p.get("kind") or "",
                "msrp": p.get("msrp") or mk.msrp_from_lotteries(p["name"]),
                "id": (re.search(r"apparels/(\d+)", p.get("url") or "") or [None, None])[1]} for p in mk.products()]
    except Exception:
        mkp = []
    html = (TEMPLATE.replace("__MKPRODUCTS__", json.dumps(mkp, ensure_ascii=False))
            .replace("__SITE__", json.dumps(site or ""))
            .replace("__ITEMS__", json.dumps(data, ensure_ascii=False))
            .replace("__UPDATED__", json.dumps(updated or ""))
            .replace("__IMGS__", json.dumps(imgs))
            .replace("__MARKET__", json.dumps(market, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__BUZZ__", json.dumps(buzz, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__TRENDS__", json.dumps(_trends(), ensure_ascii=False).replace("</", "<\\/")))
    (out / "x-draft.html").write_text(html, encoding="utf-8")
