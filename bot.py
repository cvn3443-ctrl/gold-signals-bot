import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ================== الإعدادات ==================
TELEGRAM_TOKEN = "8993436999:AAFA3SeyZrbVlHlZ3Ffzy0dR7ZJHEsZezpg"
TELEGRAM_CHAT_ID = "-1004300703660"
TWELVE_DATA_API_KEY = "8542361c42e84dd68468a39366ca04a1"

SYMBOL = "XAU/USD"
TIMEFRAME = "15min"

# ================== جلب البيانات ==================
def get_data():
    print("=== جاري جلب البيانات ===")
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={TIMEFRAME}&outputsize=200&apikey={TWELVE_DATA_API_KEY}"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        if 'values' not in data:
            print(f"خطأ: {data.get('message', 'خطأ غير معروف')}")
            return None
        df = pd.DataFrame(data['values'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)
        print(f"تم جلب {len(df)} شمعة. آخر سعر: {df['close'].iloc[-1]:.2f}")
        return df
    except Exception as e:
        print(f"فشل جلب البيانات: {e}")
        return None

# ================== المؤشرات ==================
def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def is_clean_candle(df):
    last = df.iloc[-1]
    body = abs(last['close'] - last['open'])
    total_range = last['high'] - last['low']
    if total_range == 0:
        return False
    return (body / total_range) > 0.4

# ================== إرسال التوصية ==================
def send_signal(direction, entry, sl, tp, confidence):
    message = f"""
🔔 توصية جديدة - XAUUSD

📈 الاتجاه: {direction}
💰 سعر الدخول: {entry}
🛑 وقف الخسارة: {sl}
🎯 هدف الربح: {tp}

⏰ الوقت: {datetime.now().strftime('%H:%M')}
📊 الفريم: {TIMEFRAME}
🧠 نسبة الثقة: {confidence}%
📡 المصدر: Twelve Data

⚠️ المخاطرة المقترحة: 0.5% من رأس المال
"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
        print(f"✅ تم إرسال التوصية: {direction}")
    except Exception as e:
        print(f"❌ فشل إرسال التوصية: {e}")

# ================== التشغيل (مرة واحدة) ==================
def main():
    print("=== البوت بدأ العمل ===")
    df = get_data()
    if df is None or len(df) < 50:
        print("بيانات غير كافية.")
        return
    
    ema_50 = calculate_ema(df, 50)
    ema_200 = calculate_ema(df, 200)
    rsi = calculate_rsi(df, 14)
    atr = calculate_atr(df, 14)
    
    last_close = df['close'].iloc[-1]
    last_ema50 = ema_50.iloc[-1]
    last_ema200 = ema_200.iloc[-1]
    last_rsi = rsi.iloc[-1]
    last_atr = atr.iloc[-1]
    
    print(f"السعر: {last_close:.2f} | RSI: {last_rsi:.2f} | ATR: {last_atr:.2f}")
    
    if last_atr < 1.0:
        print("ATR صغير جداً، تجاهل.")
        return
    
    if not is_clean_candle(df):
        print("الشمعة غير نظيفة، تجاهل.")
        return
    
    buy_conditions = [
        last_close > last_ema200,
        last_close > last_ema50,
        30 < last_rsi < 70,
        last_atr > 1.0,
    ]
    
    sell_conditions = [
        last_close < last_ema200,
        last_close < last_ema50,
        30 < last_rsi < 70,
        last_atr > 1.0,
    ]
    
    buy_score = sum(buy_conditions)
    sell_score = sum(sell_conditions)
    
    print(f"نقاط الشراء: {buy_score}/4 | نقاط البيع: {sell_score}/4")
    
    if buy_score >= 2:
        confidence = int((buy_score / 4) * 100)
        entry = round(last_close, 2)
        sl = round(entry - (last_atr * 1.5), 2)
        tp = round(entry + (last_atr * 3), 2)
        send_signal("شراء (BUY)", entry, sl, tp, confidence)
    elif sell_score >= 2:
        confidence = int((sell_score / 4) * 100)
        entry = round(last_close, 2)
        sl = round(entry + (last_atr * 1.5), 2)
        tp = round(entry - (last_atr * 3), 2)
        send_signal("بيع (SELL)", entry, sl, tp, confidence)
    else:
        print("لا إشارة حالياً.")

if __name__ == "__main__":
    main()
