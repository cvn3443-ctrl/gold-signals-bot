import asyncio
import time
import numpy as np
from datetime import datetime
import requests
from pyquotex.stable_api import Quotex

# ======== إعدادات البوت ========
EMAIL = "db09015d84@emailnox.live"
PASSWORD = "NOOR@#0000"
ASSET = "EURUSD"
TRADE_AMOUNT = 1
TRADE_DURATION = 60
TIMEFRAME = 60
LOOKBACK = 200

is_trade_open = False
client = None
today_trades = 0
last_candle_time = 0

# ============================================================
# المصادر الموثوقة (كل مصدر يجيب شموع)
# ============================================================

def get_binance_candles(symbol="EURUSDT", interval="1m", limit=200):
    """Binance - شموع 1m"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if not isinstance(data, list):
            return None
        return [{"open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in data]
    except:
        return None

def get_okx_candles(symbol="EUR-USDT", interval="1m", limit=200):
    """OKX - شموع 1m (مصدر بديل ممتاز)"""
    try:
        url = "https://www.okx.com/api/v5/market/candles"
        params = {"instId": symbol, "bar": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if data.get("code") != "0":
            return None
        candles = []
        for c in reversed(data["data"]):
            candles.append({"open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])})
        return candles
    except:
        return None

def get_bybit_candles(symbol="EURUSDT", interval="1", limit=200):
    """Bybit - شموع 1m"""
    try:
        url = "https://api.bybit.com/v5/market/kline"
        params = {"category": "spot", "symbol": symbol, "interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if data.get("retCode") != 0:
            return None
        candles = []
        for c in reversed(data["result"]["list"]):
            candles.append({"open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])})
        return candles
    except:
        return None

def get_kucoin_candles(symbol="EUR-USDT", interval="1min", limit=200):
    """KuCoin - شموع 1m"""
    try:
        url = "https://api.kucoin.com/api/v1/market/candles"
        params = {"symbol": symbol, "type": interval}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if data.get("code") != "200000":
            return None
        candles = []
        for c in reversed(data["data"][:limit]):
            candles.append({"open": float(c[1]), "high": float(c[3]), "low": float(c[4]), "close": float(c[2]), "volume": float(c[5])})
        return candles
    except:
        return None

def get_gate_candles(symbol="EUR_USDT", interval="1m", limit=200):
    """Gate.io - شموع 1m"""
    try:
        url = "https://api.gateio.ws/api/v4/spot/candlesticks"
        params = {"currency_pair": symbol, "interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if not isinstance(data, list):
            return None
        candles = []
        for c in data:
            candles.append({"open": float(c[5]), "high": float(c[3]), "low": float(c[4]), "close": float(c[2]), "volume": float(c[6])})
        return candles
    except:
        return None

def get_external_prices():
    """أسعار لحظية من مصادر خارجية للتأكيد"""
    prices = []
    sources = []
    
    # ExchangeRate-API
    try:
        r = requests.get("https://open.er-api.com/v6/latest/EUR", timeout=5)
        p = float(r.json()["rates"]["USD"])
        prices.append(p)
        sources.append(f"er-api:{p:.5f}")
    except: pass
    
    # Frankfurter
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD", timeout=5)
        p = float(r.json()["rates"]["USD"])
        prices.append(p)
        sources.append(f"frank:{p:.5f}")
    except: pass
    
    # Fawaz
    try:
        r = requests.get("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/eur.json", timeout=5)
        p = float(r.json()["eur"]["usd"])
        prices.append(p)
        sources.append(f"fawaz:{p:.5f}")
    except: pass
    
    if not prices:
        return None, []
    return float(np.mean(prices)), sources

def send_telegram(message):
    BOT_TOKEN = "8872508056:AAFovhm1G1BRdUyOcoWeI6uFumoxTGCDBoc"
    CHAT_ID = "7761905067"
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
    except: pass

# ============================================================
# الاستراتيجيات (بدون مؤشرات)
# ============================================================

def strategy_breakout_retest(candles):
    """
    كسر وإعادة اختبار:
    - نحدد المقاومة والدعم من 20 شمعة
    - نشوف هل آخر شمعة كسرت المستوى
    - نشوف هل حصل إعادة اختبار
    """
    if len(candles) < 25:
        return 0, "لا توجد بيانات كافية"
    
    highs = [c["high"] for c in candles[-20:]]
    lows = [c["low"] for c in candles[-20:]]
    resistance = max(highs)
    support = min(lows)
    
    last = candles[-1]
    prev = candles[-2]
    
    score = 0
    reason = ""
    
    # كسر صعودي
    if prev["close"] <= resistance and last["close"] > resistance:
        score = 2
        reason = "كسر صعودي للمقاومة"
    # كسر هبوطي
    elif prev["close"] >= support and last["close"] < support:
        score = -2
        reason = "كسر هبوطي للدعم"
    # إعادة اختبار
    elif last["low"] <= resistance * 1.001 and last["close"] > resistance:
        score = 1.5
        reason = "إعادة اختبار المقاومة"
    elif last["high"] >= support * 0.999 and last["close"] < support:
        score = -1.5
        reason = "إعادة اختبار الدعم"
    
    return score, reason


def strategy_support_resistance(candles):
    """
    دعوم ومقاومة:
    - موقع السعر من النطاق
    """
    if len(candles) < 50:
        return 0, ""
    
    highs = [c["high"] for c in candles[-50:]]
    lows = [c["low"] for c in candles[-50:]]
    resistance = max(highs)
    support = min(lows)
    current = candles[-1]["close"]
    
    rng = resistance - support
    if rng == 0:
        return 0, ""
    
    pos = (current - support) / rng
    
    if pos < 0.10:
        return 2, "قرب الدعم بشكل كبير"
    elif pos < 0.20:
        return 1.5, "قرب الدعم"
    elif pos > 0.90:
        return -2, "قرب المقاومة بشكل كبير"
    elif pos > 0.80:
        return -1.5, "قرب المقاومة"
    return 0, ""


def strategy_price_action(candles):
    """
    حركة السعر:
    - شكل الشموع
    - الأنماط
    """
    if len(candles) < 3:
        return 0, ""
    
    last = candles[-1]
    prev = candles[-2]
    
    body = abs(last["close"] - last["open"])
    rng = last["high"] - last["low"]
    if rng == 0:
        return 0, ""
    
    strength = body / rng
    score = 0
    reason = ""
    
    # شمعة قوية
    if last["close"] > last["open"] and strength > 0.6:
        score = 1.5
        reason = "شمعة صاعدة قوية"
    elif last["close"] < last["open"] and strength > 0.6:
        score = -1.5
        reason = "شمعة هابطة قوية"
    
    # Engulfing
    if prev["close"] < prev["open"] and last["close"] > last["open"] and last["close"] > prev["open"] and last["open"] < prev["close"]:
        score = 2
        reason = "Bullish Engulfing"
    elif prev["close"] > prev["open"] and last["close"] < last["open"] and last["close"] < prev["open"] and last["open"] > prev["close"]:
        score = -2
        reason = "Bearish Engulfing"
    
    return score, reason


def strategy_market_structure(candles):
    """
    بنية السوق:
    - HH/HL أو LH/LL
    """
    if len(candles) < 10:
        return 0, ""
    
    highs = [c["high"] for c in candles[-10:]]
    lows = [c["low"] for c in candles[-10:]]
    
    fh = max(highs[:5]); sh = max(highs[5:])
    fl = min(lows[:5]); sl = min(lows[5:])
    
    if sh > fh and sl > fl:
        return 1.5, "HH/HL (صاعد)"
    elif sh < fh and sl < fl:
        return -1.5, "LH/LL (هابط)"
    return 0, ""


def strategy_momentum_candles(candles):
    """
    الزخم بناءً على 3 شموع متتالية
    """
    if len(candles) < 3:
        return 0, ""
    
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    
    if c1["close"] < c2["close"] < c3["close"]:
        return 2, "3 شموع صاعدة متتالية"
    elif c1["close"] > c2["close"] > c3["close"]:
        return -2, "3 شموع هابطة متتالية"
    return 0, ""


# ============================================================
# تجميع الاستراتيجيات على كل مصدر
# ============================================================

def analyze_source(name, candles):
    """تطبيق كل الاستراتيجيات على مصدر واحد"""
    if not candles or len(candles) < 50:
        return None
    
    s1, r1 = strategy_breakout_retest(candles)
    s2, r2 = strategy_support_resistance(candles)
    s3, r3 = strategy_price_action(candles)
    s4, r4 = strategy_market_structure(candles)
    s5, r5 = strategy_momentum_candles(candles)
    
    total = s1 + s2 + s3 + s4 + s5
    reasons = [r for r in [r1, r2, r3, r4, r5] if r]
    
    print(f"[{name}] شموع: {len(candles)} | Score: {total:+.1f} | {reasons[:3]}")
    
    return {
        "name": name,
        "score": total,
        "price": candles[-1]["close"],
        "reasons": reasons
    }


# ============================================================
# الحلقة الرئيسية
# ============================================================

async def connect_to_quotex():
    global client
    print("[BOT] 🔑 الاتصال بـ Quotex...")
    try:
        client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
        check, msg = await client.connect()
        if check:
            print("[BOT] ✅ تم الاتصال")
            return True
        print(f"[BOT] ⚠️ فشل: {msg}")
        return False
    except Exception as e:
        print(f"[BOT] خطأ: {e}")
        return False


async def execute_trade(direction):
    try:
        status, result = await client.buy(
            amount=TRADE_AMOUNT,
            asset=ASSET,
            direction=direction,
            duration=TRADE_DURATION
        )
        return status, result
    except Exception as e:
        return False, str(e)


async def main_loop():
    global is_trade_open, today_trades, client, last_candle_time
    
    print("=" * 65)
    print("   QUOTEX MULTI-SOURCE STRATEGY BOT")
    print("=" * 65)
    print(f"Asset      : {ASSET}")
    print(f"Amount     : ${TRADE_AMOUNT}")
    print(f"Duration   : {TRADE_DURATION}s")
    print(f"Timeframe  : {TIMEFRAME}s")
    print(f"Sources    : Binance, OKX, Bybit, KuCoin, Gate.io")
    print(f"Strategies : Breakout, S/R, Price Action, Structure, Momentum")
    print("=" * 65)
    
    if not await connect_to_quotex():
        return
    
    while True:
        try:
            # انتظار بداية دقيقة جديدة
            now = datetime.now()
            wait = 60 - now.second
            if wait < 0:
                wait += 60
            if wait > 1:
                print(f"[BOT] ⏳ انتظار {wait}ث...")
                await asyncio.sleep(wait)
            
            print(f"\n{'=' * 65}")
            print(f"[BOT] ⏰ {datetime.now().strftime('%H:%M:%S')} - بداية دقيقة")
            
            if is_trade_open:
                print("[BOT] ⏳ صفقة مفتوحة")
                continue
            
            # ============================================
            # جلب الشموع من كل المصادر
            # ============================================
            
            sources_data = []
            
            binance = get_binance_candles("EURUSDT", "1m", LOOKBACK)
            if binance:
                r = analyze_source("Binance", binance)
                if r: sources_data.append(r)
            
            okx = get_okx_candles("EUR-USDT", "1m", LOOKBACK)
            if okx:
                r = analyze_source("OKX", okx)
                if r: sources_data.append(r)
            
            bybit = get_bybit_candles("EURUSDT", "1", LOOKBACK)
            if bybit:
                r = analyze_source("Bybit", bybit)
                if r: sources_data.append(r)
            
            kucoin = get_kucoin_candles("EUR-USDT", "1min", LOOKBACK)
            if kucoin:
                r = analyze_source("KuCoin", kucoin)
                if r: sources_data.append(r)
            
            gate = get_gate_candles("EUR_USDT", "1m", LOOKBACK)
            if gate:
                r = analyze_source("Gate.io", gate)
                if r: sources_data.append(r)
            
            # ============================================
            # التحقق من السعر الخارجي
            # ============================================
            
            ext_price, ext_sources = get_external_prices()
            
            if not sources_data:
                print("[BOT] ⚠️ لم يتم جلب بيانات من أي مصدر")
                continue
            
            # ============================================
            # تجميع الأصوات من كل المصادر
            # ============================================
            
            total_score = sum(s["score"] for s in sources_data)
            avg_score = total_score / len(sources_data)
            
            print(f"\n[🎯 النتيجة النهائية]")
            print(f"عدد المصادر: {len(sources_data)}")
            print(f"مجموع الأصوات: {total_score:+.2f}")
            print(f"المتوسط: {avg_score:+.2f}")
            
            if ext_sources:
                print(f"التحقق الخارجي: {', '.join(ext_sources)}")
            
            # ============================================
            # القرار
            # ============================================
            
            if avg_score > 0.5:
                direction = "call"
                signal_name = "🟢 صعود"
                confidence = min(95, 60 + abs(avg_score) * 5)
            elif avg_score < -0.5:
                direction = "put"
                signal_name = "🔴 هبوط"
                confidence = min(95, 60 + abs(avg_score) * 5)
            else:
                print("[BOT] ⏳ لا توجد إشارة قوية (متوسط أقل من 0.5)")
                continue
            
            print(f"[BOT] 📊 القرار: {signal_name} (ثقة: {confidence:.0f}%)")
            
            # ============================================
            # تنفيذ الصفقة
            # ============================================
            
            status, result = await execute_trade(direction)
            
            if status:
                today_trades += 1
                is_trade_open = True
                print(f"[BOT] ✅ صفقة #{today_trades} مفتوحة")
                
                send_telegram(
                    f"✅ صفقة #{today_trades}\n"
                    f"{ASSET}\n"
                    f"{signal_name}\n"
                    f"الثقة: {confidence:.0f}%\n"
                    f"أصوات: {total_score:+.1f} ({len(sources_data)} مصادر)"
                )
                
                async def close_trade():
                    global is_trade_open
                    await asyncio.sleep(TRADE_DURATION - 5)
                    is_trade_open = False
                    print("[BOT] 🔓 جاهز للصفقة التالية")
                
                asyncio.create_task(close_trade())
            else:
                print(f"[BOT] ❌ فشل: {result}")

        except KeyboardInterrupt:
            print("\n[BOT] ⏹️ إيقاف")
            break
        except Exception as e:
            print(f"[BOT] ❌ خطأ: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main_loop())
