import ccxt
import pandas as pd
import requests
import time, os, sys
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
EXCHANGE_ID   = "okx"
QUOTE_ASSET   = "USDT"
TOP_N_SYMBOLS = 200
EMA_FAST, EMA_SLOW = 20, 50
TZ_TR = timezone(timedelta(hours=3))
ARGS  = sys.argv[1:]

def now_tr():
    return datetime.now(TZ_TR).strftime("%d.%m.%Y %H:%M")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print(f"  TG: {r.status_code}")
    except Exception as e:
        print(f"  TG Hata: {e}")

def calc_rsi(closes, period=14):
    delta = closes.diff()
    gain  = delta.where(delta > 0, 0.0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.where(delta < 0, 0.0)).ewm(com=period-1, min_periods=period).mean()
    return round(float((100 - 100 / (1 + gain/loss.replace(0,1e-10))).iloc[-1]), 2)

def calc_ema(closes, period):
    return closes.ewm(span=period, adjust=False).mean()

def get_ohlcv(exchange, symbol, tf, limit=250):
    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        if len(raw) < 60: return None
        df = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume"])
        df[["close","volume"]] = df[["close","volume"]].astype(float)
        return df
    except:
        return None

def get_score(rsi, vol_x, price, e20, e50):
    s = 0
    if 40<=rsi<=55: s+=3
    elif rsi<=65: s+=2
    elif rsi<=75: s+=1
    if vol_x>=3: s+=3
    elif vol_x>=2: s+=2
    elif vol_x>=1.5: s+=1
    if ((price-e20)/e20)*100 <= 1: s+=2
    elif ((price-e20)/e20)*100 <= 3: s+=1
    if ((e20-e50)/e50)*100 <= 1: s+=2
    elif ((e20-e50)/e50)*100 <= 3: s+=1
    return s

def stars(s):
    return "⭐⭐⭐ GÜÇLÜ" if s>=8 else "⭐⭐ ORTA" if s>=5 else "⭐ ZAYIF"

def scan_all(exchange, symbols, tf, label):
    hits = []
    print(f"  [{label}] {len(symbols)} coin taranıyor...")
    for sym in symbols:
        df = get_ohlcv(exchange, sym, tf)
        if df is None: continue
        c=df["close"]; v=df["volume"]
        e20=calc_ema(c,EMA_FAST); e50=calc_ema(c,EMA_SLOW)
        try: rsi=calc_rsi(c)
        except: continue
        price=float(c.iloc[-1]); open_=float(df["open"].iloc[-1])
        vol_x=round(float(v.iloc[-1])/float(v.iloc[-20:].mean()),2)
        ev20=float(e20.iloc[-1]); ev50=float(e50.iloc[-1])
        if price>ev20*0.998 and 40<=rsi<=75 and ev20>=ev50*0.998 and vol_x>=1.2 and price>open_:
            sc=get_score(rsi,vol_x,price,ev20,ev50)
            hits.append({"symbol":sym.replace("/USDT",""),"price":price,"rsi":rsi,
                         "vol_x":vol_x,"score":sc,"stars":stars(sc),
                         "dist":round(((price-ev20)/ev20)*100,2),
                         "gap":round(((ev20-ev50)/ev50)*100,2)})
        time.sleep(0.06)
    print(f"  -> {len(hits)} sinyal")
    zaman = now_tr()
    if not hits:
        send_telegram(f"━━━━━━━━━━━━━━━━━━━━━━━\n🤖 *FETHİNHO AI* | OKX\n━━━━━━━━━━━━━━━━━━━━━━━\n📊 *{label}* [{tf}]\n🕐 {zaman} (UTC+3)\n\n❌ Sinyal yok.")
    else:
        hits=sorted(hits,key=lambda x:x["score"],reverse=True)
        lines=["━━━━━━━━━━━━━━━━━━━━━━━","🤖 *FETHİNHO AI* | OKX Tarama",
               "━━━━━━━━━━━━━━━━━━━━━━━",f"📊 *{label}* [{tf}]",
               f"🕐 {zaman} (UTC+3)",f"✅ *{len(hits)} Sinyal*","───────────────────────"]
        for h in hits:
            lines.append(f"{h['stars']}\n🔸 *{h['symbol']}*\n   💰 {h['price']:.4f} USDT  📈 RSI:{h['rsi']}  🔥{h['vol_x']}x\n   📐 EMA20:+{h['dist']}%  Gap:{h['gap']}%\n")
        lines+=["───────────────────────","📌 Erken sinyal sistemi","━━━━━━━━━━━━━━━━━━━━━━━"]
        send_telegram("\n".join(lines))

def main():
    print(f"🤖 FETHİNHO AI — {now_tr()} (UTC+3)")
    exchange=getattr(ccxt,EXCHANGE_ID)({"enableRateLimit":True})
    exchange.load_markets()
    all_syms=[s for s,m in exchange.markets.items()
              if m.get("quote")==QUOTE_ASSET and m.get("active")
              and m.get("type","spot")=="spot" and "/" in s and ":" not in s]
    try:
        tickers=exchange.fetch_tickers(all_syms[:400])
        syms=sorted([s for s in tickers if tickers[s].get("quoteVolume")],
                    key=lambda s:tickers[s]["quoteVolume"],reverse=True)[:TOP_N_SYMBOLS]
    except:
        syms=all_syms[:TOP_N_SYMBOLS]
    print(f"   {len(syms)} coin")
    tf_map={"1h":"Saatlik","4h":"4 Saatlik","1d":"Günlük"}
    if ARGS:
        tf=ARGS[0]; scan_all(exchange,syms,tf,tf_map.get(tf,tf))
    else:
        for tf,label in tf_map.items():
            scan_all(exchange,syms,tf,label); time.sleep(3)
    print(f"Tamamlandi — {now_tr()}")

main()
