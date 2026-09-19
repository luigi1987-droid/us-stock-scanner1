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
from alpaca.data.requests import StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

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


def analyze_etf(df, symbol=""):
    """
    Analisi combinata:
    1. Verifica IDNR4 Rigido (Inside Day + Narrow Range 4).
    2. Verifica Compressione Crabel (NR4/NR7 o Volatilità < Media + Trend SMA 10).
    """
    if len(df) < 25:
        return None

    df = df.copy()
    df["Range"] = df["High"] - df["Low"]
    df["Range_SMA"] = df["Range"].rolling(window=10).mean()
    df["SMA_10"] = df["Close"].rolling(window=10).mean()

    curr_high = df["High"].iloc[-1]
    curr_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["Low"].iloc[-2]
    curr_range = df["Range"].iloc[-1]

    # --- 1. CONTROLLO IDNR4 RIGIDO ---
    last_4_ranges_strict = df["Range"].iloc[-4:]
    is_inside = (curr_high < prev_high) and (curr_low > prev_low)
    is_nr4_strict = curr_range == last_4_ranges_strict.min()
    is_idnr4 = is_inside and is_nr4_strict

    # --- 2. CONTROLLO COMPRESSIONE CRABEL (FALLBACK) ---
    last_4_crabel = df["Range"].iloc[-5:-1]
    last_7_crabel = df["Range"].iloc[-8:-1]
    is_nr4_crabel = curr_range <= last_4_crabel.min()
    is_nr7_crabel = curr_range <= last_7_crabel.min()
    is_compressed = curr_range < df["Range_SMA"].iloc[-1]
    is_uptrend = df["Close"].iloc[-1] > df["SMA_10"].iloc[-1]

    is_crabel_setup = (is_nr4_crabel or is_nr7_crabel or is_compressed) and is_uptrend

    momentum_score = (
        (df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]
    ) * 100

    compression_score = (df["Range_SMA"].iloc[-1] - curr_range) / df["Range_SMA"].iloc[-1]

    candle_range = curr_high - curr_low
    if candle_range == 0:
        candle_range = 0.01

    return {
        "ticker": symbol,
        "entry": curr_high,
        "sl": curr_low,
        "tp": curr_high + (candle_range * 2.0),
        "momentum": momentum_score,
        "compression_score": compression_score,
        "is_idnr4": is_idnr4,
        "is_crabel": is_crabel_setup and not is_idnr4  # Escludiamo i doppioni se è già IDNR4
    }


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


def place_bracket_order(symbol, entry, sl, tp, qty):
    try:
        request_params = StockLatestTradeRequest(symbol_or_symbols=symbol)
        latest_trade = data_client.get_stock_latest_trade(request_params)
        
        if symbol not in latest_trade:
            return False
            
        current_price = float(latest_trade[symbol].price)

        if entry <= current_price:
            entry = current_price * 1.002
            risk = entry - sl
            tp = entry + (risk * 2.0)

        order_data = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            stop_price=round(entry, 2),
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(tp, 2)),
            stop_loss=StopLossRequest(stop_price=round(sl, 2)),
        )
        order = trading_client.submit_order(order_data=order_data)
        log_print(f"  ✅ [ALPACA] Ordine inviato con successo per ETF {symbol} | Qty: {qty} | ID: {order.id}")
        return True
    except Exception as e:
        log_print(f"  ❌ [ERRORE ALPACA] Impossibile inviare ordine per {symbol}: {e}")
        return False


def main():
    log_print("--- Avvio Scanner Gerarchico (IDNR4 prioritario -> Crabel Fallback) ---")
    log_print(f"Data esecuzione: {datetime.today().strftime('%Y-%m-%d %H:%M:%S')}")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)

    idnr4_candidates = []
    crabel_candidates = []

    for ticker in ETF_WATCHLIST:
        try:
            time.sleep(0.1)
            request_params = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date
            )
            bars = data_client.get_stock_bars(request_params)
            
            if not bars or not hasattr(bars, 'df') or bars.df.empty:
                continue

            data = bars.df

            if isinstance(data.index, pd.MultiIndex):
                data = data.xs(ticker, level=0)

            data = data.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })

            if len(data) >= 25:
                res = analyze_etf(data, symbol=ticker)
                if res:
                    if res["is_idnr4"]:
                        idnr4_candidates.append(res)
                    elif res["is_crabel"]:
                        crabel_candidates.append(res)
        except Exception:
            continue

    log_print("\n" + "=" * 50)
    log_print("        GESTIONE GERARCHICA DEGLI ORDINI")
    log_print("=" * 50)

    # Ordinamenti
    idnr4_candidates.sort(key=lambda x: x["momentum"], reverse=True)
    crabel_candidates.sort(key=lambda x: x["compression_score"], reverse=True)

    order_sent = False

    # 1. TENTA PRIMA CON I CANDIDATI IDNR4 RIGIDI
    if idnr4_candidates:
        log_print(f"🏆 Trovati {len(idnr4_candidates)} candidati con pattern IDNR4 perfetto. Tentativo d'ordine...")
        for candidate in idnr4_candidates:
            ticker = candidate["ticker"]
            log_print(f"\n👉 IDNR4 [{ticker}] | Momentum: {candidate['momentum']:.2f}%")
            qty = get_dynamic_quantity(candidate["entry"])
            if place_bracket_order(ticker, candidate["entry"], candidate["sl"], candidate["tp"], qty):
                log_print(f"🎉 Operazione aperta con successo sull'ETF IDNR4: {ticker}!")
                order_sent = True
                break
    else:
        log_print("ℹ️ Nessun IDNR4 perfetto trovato oggi. Procedo con il piano di riserva Crabel...")

    # 2. SE NESSUN IDNR4 HA FUNZIONATO, PASSA AL FALLBACK CRABEL (NR4/NR7 + SMA10)
    if not order_sent and crabel_candidates:
        log_print(f"\n🏆 Trovati {len(crabel_candidates)} candidati in compressione Crabel (con filtro SMA 10). Tentativo...")
        for candidate in crabel_candidates:
            ticker = candidate["ticker"]
            log_print(f"\n👉 Crabel Setup [{ticker}] | Compressione: {candidate['compression_score']:.2f}")
            qty = get_dynamic_quantity(candidate["entry"])
            if place_bracket_order(ticker, candidate["entry"], candidate["sl"], candidate["tp"], qty):
                log_print(f"🎉 Operazione aperta con successo sull'ETF Crabel: {ticker}!")
                order_sent = True
                break

    if not order_sent:
        log_print("\n❌ Nessun candidato idoneo (né IDNR4 né Crabel) ha superato l'invito dell'ordine oggi.")
    
    log_print("=" * 50)

    try:
        with open("execution_summary.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(log_output))
    except Exception:
        pass


if __name__ == "__main__":
    main()
