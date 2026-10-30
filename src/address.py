"""お店の住所を応募ページ（LivePocket・お店の告知ページなど）の本文から読み取る

・「住所」「所在地」「会場」「店舗」「〒」などの言葉のすぐ後ろにある住所だけを使う
  （ページの下にある運営会社の住所をお店の住所とまちがえないように）
・抽選に都道府県が分かっている時は、同じ都道府県の住所だけを使う
"""
import re
from urllib.parse import quote

PREFS = ("北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|"
         "新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|"
         "和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|"
         "大分県|宮崎県|鹿児島県|沖縄県")
ADDR = re.compile(r"(" + PREFS + r")\s*([^\s、。,，「」【】『』()（）:：/|｜<>]{2,45})")
HINT = re.compile(r"住所|所在地|会場|店舗|店頭|場所|アクセス|〒|受け?取り")
STOP = re.compile(r"(TEL|Tel|tel|電話|営業|定休|☎|📞|※|最寄|駅から|徒歩).*$")


LP_VENUE = re.compile(r"会場\s*[^\n()（）]{1,40}?[（(](" + PREFS + r")[）)]\s*([^\s、。,，「」【】『』()（）:：/|｜<>]{2,45})")


def find_address(text, area=None):
    """本文から住所を1つ。見つからなければ None"""
    t = text or ""
    # LivePocket の「会場 〇〇店 (大阪府) 枚方市宮之阪4-28-12」の形
    for m in LP_VENUE.finditer(t):
        pref, rest = m.group(1), STOP.sub("", m.group(2))
        if (not area or pref == area) and re.search(r"[市区町村郡]", rest) and re.search(r"[0-9０-９]", rest):
            return pref + re.sub(r"(?<=[0-9０-９])[‐－―ー−](?=[0-9０-９])", "-", rest).rstrip("-")
    for m in ADDR.finditer(t):
        pref, rest = m.group(1), STOP.sub("", m.group(2))
        if area and pref != area:
            continue
        if not re.search(r"[市区町村郡]", rest) or not re.search(r"[0-9０-９]", rest):
            continue  # 番地まで書いてあるものだけ
        if not HINT.search(t[max(0, m.start() - 60):m.start()]):
            continue
        rest = re.sub(r"(?<=[0-9０-９])[‐－―ー−](?=[0-9０-９])", "-", rest).rstrip("-")
        return pref + rest
    return None


def maps_url(store, address):
    """Googleマップでその住所をひらくリンク（地図の中身は載せない。リンクだけ）"""
    return "https://www.google.com/maps/search/?api=1&query=" + quote(f"{address} {store or ''}".strip())
