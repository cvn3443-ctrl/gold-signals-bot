import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
import threading
import os

# ================== إعداد خادم Flask ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ================== الإعدادات ==================
TELEGRAM_TOKEN = "8993436999:AAFA3SeyZrbVlHlZ3Ffzy0dR7ZJHEsZezpg"
TELEGRAM_CHAT_ID = "-1004300703660"
TWELVE_DATA_API_KEY = "8542361c42e84dd68468a39366ca04a1"

SYMBOL_TWELVE = "XAU/USD"
SYMBOL_BINANCE = "XAUUSDT"
TIMEFRAME = "15min"
MIN_TIME_BETWEEN_SIGNALS = 900  # 15 دقيقة

# ================== جلب البيانات من Twelve Data ==================
def get_data_twelve():
    print("=== جاري جلب البيانات من Twelve Data ===")
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL_TWELVE}&interval={TIMEFRAME}&outputsize=200&apikey={TWELVE_DATA_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if 'values' not in data:
            print(f"Twelve Data: {data.get('message', 'خطأ')}")
            return None
        df = pd.DataFrame(data['values'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)
        print(f"Twelve Data: تم جلب {len(df)} شمعة")
        return df
    except Exception as e:
        print(f"Twelve Data اتصال: {e}")
        return None

# ================== جلب البيانات من Binance ==================
def get_data_binance():
    print("=== جاري جلب البيانات من Binance ===")
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL_BINANCE}&interval=15m&limit=200"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if not isinstance(data, list):
            print("Binance: خطأ في البيانات")
            return None
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        print(f"Binance: تم جلب {len(df)} شمعة")
        return df
    except Exception as e:
        print(f"Binance اتصال: {e}")
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

# ================== فلتر الشمعة النظيفة ==================
def is_clean_candle(df):
    last = df.iloc[-1]
    body = abs(last['close'] - last['open'])
    total_range = last['high'] - last['low']
    if total_range == 0:
        return False
    body_ratio = body / total_range
    return body_ratio > 0.4

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
📡 المصادر: Twelve Data + Binance

⚠️ المخاطرة المقترحة: 0.5% من رأس المال
"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
        print(f"تم إرسال التوصية: {direction}")
    except Exception as e:
        print(f"فشل إرسال التوصية: {e}")

# ================== الحلقة الرئيسية ==================
def main():
    print("=== البوت بدأ العمل ===")
    last_signal_time = 0
    while True:
        try:
            df_twelve = get_data_twelve()
            df_binance = get_data_binance()
            
            print(f"Twelve Data: {'OK' if df_twelve is not None else 'فشل'} | Binance: {'OK' if df_binance is not None else 'فشل'}")
            
            if df_twelve is None or df_binance is None or len(df_twelve) < 50:
                print("بيانات غير كافية، إعادة المحاولة...")
                time.sleep(60)
                continue
            
            # التحقق المتقاطع
            price_twelve = df_twelve['close'].iloc[-1]
            price_binance = df_binance['close'].iloc[-1]
            price_diff = abs(price_twelve - price_binance) / price_twelve * 100
            
            if price_diff > 1.0:
                print(f"فرق كبير بين المصدرين: {price_diff:.2f}% - تجاهل الإشارة")
                time.sleep(900)
                continue
            
            # حساب المؤشرات
            ema_50 = calculate_ema(df_twelve, 50)
            ema_200 = calculate_ema(df_twelve, 200)
            rsi = calculate_rsi(df_twelve, 14)
            atr = calculate_atr(df_twelve, 14)
            
            last_close = df_twelve['close'].iloc[-1]
            last_ema50 = ema_50.iloc[-1]
            last_ema200 = ema_200.iloc[-1]
            last_rsi = rsi.iloc[-1]
            last_atr = atr.iloc[-1]
            
            # فلتر ATR
            if last_atr < 1.0:
                print(f"ATR صغير جداً ({last_atr:.2f})، تجاهل.")
                time.sleep(900)
                continue
            
            # فلتر الشمعة النظيفة
            if not is_clean_candle(df_twelve):
                print("الشمعة غير نظيفة، تجاهل.")
                time.sleep(900)
                continue
            
            # شروط الشراء
            buy_conditions = [
                last_close > last_ema200,
                last_close > last_ema50,
                30 < last_rsi < 70,
                last_atr > 1.0,
            ]
            
            # شروط البيع
            sell_conditions = [
                last_close < last_ema200,
                last_close < last_ema50,
                30 < last_rsi < 70,
                last_atr > 1.0,
            ]
            
            buy_score = sum(buy_conditions)
            sell_score = sum(sell_conditions)
            
            # طباعة تشخيصية
            print(f"السعر: {last_close:.2f} | RSI: {last_rsi:.2f} | ATR: {last_atr:.2f} | شراء: {buy_score}/4 | بيع: {sell_score}/4")
            
            current_time = time.time()
            time_since_last = current_time - last_signal_time
            
            if buy_score >= 2 and time_since_last >= MIN_TIME_BETWEEN_SIGNALS:
                confidence = int((buy_score / 4) * 100)
                entry = round(last_close, 2)
                sl = round(entry - (last_atr * 1.5), 2)
                tp = round(entry + (last_atr * 3), 2)
                send_signal("شراء (BUY)", entry, sl, tp, confidence)
                last_signal_time = current_time
            
            elif sell_score >= 2 and time_since_last >= MIN_TIME_BETWEEN_SIGNALS:
                confidence = int((sell_score / 4) * 100)
                entry = round(last_close, 2)
                sl = round(entry + (last_atr * 1.5), 2)
                tp = round(entry - (last_atr * 3), 2)
                send_signal("بيع (SELL)", entry, sl, tp, confidence)
                last_signal_time = current_time
            else:
                print("لا إشارة حالياً.")
            
            time.sleep(900)
        
        except Exception as e:
            print(f"حدث خطأ: {e}")
            time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    main()
