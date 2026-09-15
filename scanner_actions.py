from datetime import datetime, timedelta
import os
import time
import pandas as pd
import yfinance as yf

# Librerie ufficiali Alpaca
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
)

# 1. Autenticazione con i Secret di GitHub
API_KEY = os.getenv("ALPACA_API_KEY_ID")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

# 2. Watchlist massiccia di azioni US
STOCKS_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AMD", "INTC",
    "QCOM", "AVGO", "TXN", "ADBE", "CRM", "ORCL", "IBM", "NOW", "INTU", "AMAT",
    "LRCX", "MU", "ADI", "SNPS", "CDNS", "PANW", "CRWD", "KLAC", "MCHP", "FTNT",
    "PLTR", "SHOP", "SNOW", "UBER", "ABNB", "SQ", "COIN", "PYPL", "HOOD", "RBLX",
    "HD", "MCD", "NKE", "SBUX", "LOW", "TGT", "DIS", "BKNG", "MAR", "WMT",
    "COST", "PM", "KO", "PEP", "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY",
    "JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "SCHW", "SPGI", "CME",
    "XOM", "CVX", "COP", "EOG", "SLB", "OXY", "GE", "CAT", "DE", "RTX",
    "LMT", "BA", "HON", "UNP", "UPS", "FDX", "NEE", "DUK", "SO", "T", "VZ"
]

STOCKS_WATCHLIST = list(dict.fromkeys(STOCKS_WATCHLIST))
PORTFOLIO_ALLOCATION_PCT = 0.90

def analyze_stock(df, symbol=""):
    """Analizza il titolo restituendo lo stato IDNR4 rigoroso e i criteri di riserva (NR7)"""
    if len(df) < 20:
        return None

    df = df.copy()
    df["Range"] = df["High"] - df["Low"]

    curr_high = df["High"].iloc[-1]
    curr_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["Low"].iloc[-2]

    last_4_ranges = df["Range"].iloc[-4:]
    last_7_ranges = df["Range"].iloc[-7:]

    # Condizioni tecniche
    is_inside = (curr_high < prev_high) and (curr_low > prev_low)
    is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()
    is_nr7 = df["Range"].iloc[-1] == last_7_ranges.min()

    # Pattern primario (Rigoroso)
    is_idnr4 = is_inside and is_nr4
    
    # Pattern meno stringente di riserva (Basta Inside Day oppure NR7)
    is_fallback = is_inside or is_nr7

    # Momentum a 20 giorni per la classifica di forza relativa
    momentum_score = ((df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]) * 100

    candle_range = curr_high - curr_low
    if candle_range == 0:
        candle_range = 0.01 # Evita divisioni o range zero

    return {
        "ticker": symbol,
        "entry": curr_high,
        "sl": curr_low,
        "tp": curr_high + (candle_range * 2.0),
        "momentum": momentum_score,
        "is_idnr4": is_idnr4,
        "is_fallback": is_fallback
    }

def get_dynamic_quantity(entry_price):
    """Calcola la quantità per investire il 90% del portafoglio su Alpaca"""
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
        print(f"  ✅ [ALPACA] Ordine inviato per {symbol} | Qty: {qty} | ID: {order.id}")
        return True
    except Exception as e:
        print(f"  ❌ [ERRORE] Impossibile inviare ordine per {symbol}: {e}")
        return False

def main():
    print(f"--- Avvio Scansione (IDNR4 con Fallback Flessibile) su {len(STOCKS_WATCHLIST)} Azioni ---")

    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=35)).strftime("%Y-%m-%d")

    idnr4_candidates = []
    fallback_candidates = []

    for ticker in STOCKS_WATCHLIST:
        try:
            time.sleep(0.3)
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            if not data.empty and len(data) >= 20:
                res = analyze_stock(data, symbol=ticker)
                if res:
                    if res["is_idnr4"]:
                        idnr4_candidates.append(res)
                    elif res["is_fallback"]:
                        fallback_candidates.append(res)
        except Exception:
            pass

    print("\n" + "=" * 50)
    print("         SELEZIONE DEL MIGLIOR TITOLO")
    print("=" * 50)

    selected_stock = None
    selection_type = ""

    # 1. Cerchiamo prima tra i titoli IDNR4 perfetti
    if idnr4_candidates:
        idnr4_candidates.sort(key=lambda x: x["momentum"], reverse=True)
        selected_stock = idnr4_candidates[0]
        selection_type = "IDNR4 Rigido (Priorità Massima)"
    
    # 2. Se non ci sono IDNR4, ripieghiamo sul criterio meno stringente (Fallback)
    elif fallback_candidates:
        fallback_candidates.sort(key=lambda x: x["momentum"], reverse=True)
        selected_stock = fallback_candidates[0]
        selection_type = "Criterio di Riserva Flessibile (Inside/NR7)"

    if selected_stock:
        print(f"🏆 Trovato! Categoria: {selection_type}")
        print(f"   Titolo scelto: {selected_stock['ticker']} (Momentum: {selected_stock['momentum']:.2f}%)")
        
        qty_to_buy = get_dynamic_quantity(selected_stock["entry"])
        print(f"  📌 Allocazione 90% del capitale | Qty: {qty_to_buy} quote")
        print(f"     Entry: ${selected_stock['entry']:.2f} | SL: ${selected_stock['sl']:.2f} | TP: ${selected_stock['tp']:.2f}")

        place_bracket_order(
            selected_stock['ticker'], 
            selected_stock['entry'], 
            selected_stock['sl'], 
            selected_stock['tp'], 
            qty_to_buy
        )
    else:
        print("📭 Nessun titolo idoneo trovato neanche con i criteri di riserva.")
    print("=" * 50)

if __name__ == "__main__":
    main()
