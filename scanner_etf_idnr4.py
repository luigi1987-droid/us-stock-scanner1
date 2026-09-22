from datetime import datetime, timedelta
import os
import time
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# Autenticazione con i Secret di GitHub
API_KEY = os.getenv("ALPACA_API_KEY_ID")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

PORTFOLIO_ALLOCATION_PCT = 0.90

ETF_WATCHLIST = [
    # Mercato Generale / Indici Principali
    "SPY", "QQQ", "IWM", "MDY", "DIA", "VTI", "IVV", "RSP",
    # Settori USA (SPDR)
    "XLE", "XLF", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE", "XLC",
    # Sottosettori e Industrie ad alta volatilità
    "SMH", "IGV", "ARKK", "XBI", "ITA", "KRE", "XHB", "XRT", "XME", "XOP", "IYT", "KBE", "IBB",
    # Internazionali / Emergenti
    "EEM", "EFA", "EWJ", "EWG", "EWZ", "FXI", "INDA", "MCHI", "VGK",
    # Fattori e Smart Beta
    "SCHD", "VIG", "MTUM", "VLUE", "USMV",
    # Obbligazionari
    "TLT", "IEF", "SHY", "HYG", "LQD", "EMB", "TIP",
    # Materie Prime e Valute
    "GLD", "SLV", "USO", "DBA", "UNG", "UUP"
]

log_output = []

def log_print(message):
    print(message)
    log_output.append(message)


def analyze_daily_etf(df, symbol=""):
    if len(df) < 25:
        return None, None, None

    df = df.copy()
    df["Range"] = df["High"] - df["Low"]
    df["Range_SMA"] = df["Range"].rolling(window=10).mean()
    df["SMA_10"] = df["Close"].rolling(window=10).mean()

    curr_high = df["High"].iloc[-1]
    curr_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["Low"].iloc[-2]
    curr_range = df["Range"].iloc[-1]

    # 1. IDNR4 Rigido
    last_4_ranges_strict = df["Range"].iloc[-4:]
    is_inside = (curr_high < prev_high) and (curr_low > prev_low)
    is_nr4_strict = curr_range == last_4_ranges_strict.min()
    is_idnr4 = is_inside and is_nr4_strict

    # 2. Compressione Crabel (Fallback)
    last_4_crabel = df["Range"].iloc[-5:-1]
    last_7_crabel = df["Range"].iloc[-8:-1]
    is_nr4_crabel = curr_range <= last_4_crabel.min()
    is_nr7_crabel = curr_range <= last_7_crabel.min()
    range_sma_val = df["Range_SMA"].iloc[-1]
    is_compressed = curr_range < range_sma_val if range_sma_val > 0 else False
    is_uptrend = df["Close"].iloc[-1] > df["SMA_10"].iloc[-1]

    is_crabel_setup = (is_nr4_crabel or is_nr7_crabel or is_compressed) and is_uptrend

    momentum_score = (
        (df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]
    ) * 100

    compression_score = (range_sma_val - curr_range) / range_sma_val if range_sma_val > 0 else 0

    candle_range = curr_high - curr_low
    if candle_range == 0:
        candle_range = 0.01

    base_dict = {
        "ticker": symbol,
        "entry": curr_high,
        "sl": curr_low,
        "tp": curr_high + (candle_range * 2.0),
        "momentum": momentum_score,
        "compression_score": compression_score,
    }

    idnr4_res = base_dict.copy() if is_idnr4 else None
    crabel_res = base_dict.copy() if (is_crabel_setup and not is_idnr4) else None
    
    momentum_res = None
    if is_uptrend:
        momentum_res = base_dict.copy()

    return idnr4_res, crabel_res, momentum_res


def analyze_intraday_orb(symbol, data_client):
    try:
        end_date = datetime.now() - timedelta(minutes=20)
        start_date = end_date - timedelta(days=3)

        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=start_date,
            end=end_date,
            feed=DataFeed.IEX
        )
        bars = data_client.get_stock_bars(request_params)
        if not bars or not hasattr(bars, 'df') or bars.df.empty:
            return None

        df = bars.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)

        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        df['Date'] = df.index.date
        last_date = df['Date'].iloc[-1]
        df_day = df[df['Date'] == last_date]

        if len(df_day) < 6:
            return None

        orb_window = df_day.iloc[:6]
        orb_high = orb_window["High"].max()
        orb_low = orb_window["Low"].min()
        
        risk = orb_high - orb_low
        if risk <= 0:
            risk = 0.01

        return {
            "ticker": symbol,
            "entry": orb_high,
            "sl": orb_low,
            "tp": orb_high + (risk * 2.0),
            "score": orb_high - orb_low
        }
    except Exception:
        return None


def get_dynamic_quantity(entry_price):
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        target_investment = equity * PORTFOLIO_ALLOCATION_PCT
        if entry_price <= 0:
            return 1
        return max(1, int(target_investment / entry_price))
    except Exception:
        return 1


def place_bracket_order(symbol, entry, sl, tp, qty, current_price):
    try:
        if entry <= current_price:
            entry = current_price * 1.002
            risk = entry - sl
            tp = entry + (risk * 2.0)

        order_data = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            stop_price=round(entry, 2),
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(tp, 2)),
            stop_loss=StopLossRequest(stop_price=round(sl, 2)),
        )
        order = trading_client.submit_order(order_data=order_data)
        log_print(f"  ✅ [ALPACA] Ordine inviato per {symbol} | Qty: {qty} | ID: {order.id}")
        return True
    except Exception as e:
        log_print(f"  ❌ [ERRORE ALPACA] Impossibile inviare ordine per {symbol}: {e}")
        return False


def main():
    log_print("--- Avvio Scanner Gerarchico a 4 Livelli (Con Fallback Sicuro IEX) ---")
    
    # Controllo di sicurezza: verifica se il mercato è aperto
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            log_print("❌ Mercato chiuso (Is Open: False). Interrompo l'esecuzione per evitare ordini rifiutati.")
            return
    except Exception as e:
        log_print(f"⚠️ Impossibile verificare lo stato del mercato: {e}")

    log_print(f"Data esecuzione: {datetime.today().strftime('%Y-%m-%d %H:%M:%S')}")

    end_date = datetime.now() - timedelta(minutes=20)
    start_date = end_date - timedelta(days=45)

    idnr4_candidates = []
    crabel_candidates = []
    orb_candidates = []
    momentum_candidates = []
    latest_prices = {}

    for ticker in ETF_WATCHLIST:
        try:
            time.sleep(0.1)
            request_params = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date,
                feed=DataFeed.IEX
            )
            bars = data_client.get_stock_bars(request_params)
            
            if bars and hasattr(bars, 'df') and not bars.df.empty:
                data = bars.df
                if isinstance(data.index, pd.MultiIndex):
                    data = data.xs(ticker, level=0)

                data = data.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                
                if not data.empty:
                    latest_prices[ticker] = float(data['Close'].iloc[-1])

                if len(data) >= 25:
                    res_idnr4, res_crabel, res_mom = analyze_daily_etf(data, symbol=ticker)
                    if res_idnr4:
                        idnr4_candidates.append(res_idnr4)
                    if res_crabel:
                        crabel_candidates.append(res_crabel)
                    if res_mom:
                        momentum_candidates.append(res_mom)

            res_orb = analyze_intraday_orb(ticker, data_client)
            if res_orb:
                orb_candidates.append(res_orb)

        except Exception as e:
            log_print(f"⚠️ Errore durante l'elaborazione del ticker {ticker}: {e}")
            continue

    log_print("\n" + "=" * 50)
    log_print("        GESTIONE GERARCHICA A 4 LIVELLI")
    log_print("=" * 50)

    idnr4_candidates.sort(key=lambda x: x["momentum"], reverse=True)
    crabel_candidates.sort(key=lambda x: x["compression_score"], reverse=True)
    orb_candidates.sort(key=lambda x: x["score"], reverse=True)
    momentum_candidates.sort(key=lambda x: x["momentum"], reverse=True)

    order_sent = False

    def try_send(candidate):
        ticker = candidate["ticker"]
        if ticker not in latest_prices:
            return False
        qty = get_dynamic_quantity(candidate["entry"])
        curr_price = latest_prices[ticker]
        return place_bracket_order(ticker, candidate["entry"], candidate["sl"], candidate["tp"], qty, curr_price)

    # LIVELLO 1: IDNR4
    if idnr4_candidates:
        log_print(f"🏆 Trovati {len(idnr4_candidates)} candidati IDNR4.")
        for candidate in idnr4_candidates:
            log_print(f"\n👉 [LIVELLO 1] IDNR4 [{candidate['ticker']}]")
            if try_send(candidate):
                order_sent = True
                break
    else:
        log_print("ℹ️ Livello 1 (IDNR4): Nessun candidato.")

    # LIVELLO 2: CRABEL DAILY
    if not order_sent and crabel_candidates:
        log_print(f"\n🏆 Trovati {len(crabel_candidates)} candidati Crabel Daily.")
        for candidate in crabel_candidates:
            log_print(f"\n👉 [LIVELLO 2] Crabel Daily [{candidate['ticker']}]")
            if try_send(candidate):
                order_sent = True
                break
    else:
        if not order_sent:
            log_print("ℹ️ Livello 2 (Crabel Daily): Nessun candidato.")

    # LIVELLO 3: INTRADAY ORB
    if not order_sent and orb_candidates:
        log_print(f"\n🏆 Trovati {len(orb_candidates)} candidati Intraday ORB.")
        for candidate in orb_candidates:
            log_print(f"\n👉 [LIVELLO 3] Intraday ORB [{candidate['ticker']}]")
            if try_send(candidate):
                order_sent = True
                break
    else:
        if not order_sent:
            log_print("ℹ️ Livello 3 (Intraday ORB): Nessun candidato.")

    # LIVELLO 4: FALLBACK ASSOLUTO MOMENTUM & TREND
    if not order_sent and momentum_candidates:
        log_print(f"\n🏆 Attivazione Livello 4 (Fallback Assoluto Momentum). Selezione del miglior ETF in trend...")
        for candidate in momentum_candidates:
            log_print(f"\n👉 [LIVELLO 4 - Fallback Trend/Momentum] {candidate['ticker']} | Momentum 20D: {candidate['momentum']:.2f}%")
            if try_send(candidate):
                order_sent = True
                break
    else:
        if not order_sent:
            log_print("ℹ️ Livello 4: Nessun candidato disponibile.")

    if not order_sent:
        log_print("\n❌ Impossibile inviare alcun ordine (Watchlist vuota o errore di connessione).")
    
    log_print("=" * 50)

    try:
        with open("execution_summary.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(log_output))
    except Exception:
        pass


