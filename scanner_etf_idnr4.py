from datetime import datetime, timedelta
import os
import time
import pandas as pd

# Librerie ufficiali Alpaca (Trading & Data)
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

# Inizializzazione corretta dei client separati
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

PORTFOLIO_ALLOCATION_PCT = 0.90

# Watchlist ampliata con circa 60 ETF liquidi (Broad Market, Settori, Internazionali, Fattori, Obbligazionari, Commodity)
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

    is_inside = (curr_high < prev_high) and (curr_low > prev_low)
    is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()
    is_nr7 = df["Range"].iloc[-1] == last_7_ranges.min()

    is_idnr4 = is_inside and is_nr4
    is_fallback = is_inside or is_nr7

    momentum_score = (
        (df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]
    ) * 100

    candle_range = curr_high - curr_low
    if candle_range == 0:
        candle_range = 0.01

    return {
        "ticker": symbol,
        "entry": curr_high,
        "sl": curr_low,
        "tp": curr_high + (candle_range * 2.0),
        "momentum": momentum_score,
        "is_idnr4": is_idnr4,
        "is_fallback": is_fallback,
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
        log_print(
            f"  ✅ [ALPACA] Ordine inviato con successo per ETF {symbol} | Qty: {qty}"
            f" | ID: {order.id}"
        )
        return True
    except Exception as e:
        log_print(f"  ❌ [ERRORE ALPACA] Impossibile inviare ordine per {symbol}: {e}")
        return False


def main():
    log_print("--- Avvio Scanner ID/NR4 su Watchlist ETF Ampliata ---")
    log_print(f"Data esecuzione: {datetime.today().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"Analisi in corso su {len(ETF_WATCHLIST)} ETF...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=35)

    idnr4_candidates = []
    fallback_candidates = []

    for ticker in ETF_WATCHLIST:
        try:
            time.sleep(0.1)
            
            # Richiesta dati storici tramite Alpaca Data API
            request_params = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date
            )
            bars = data_client.get_stock_bars(request_params)
            data = bars.df

            if data.empty:
                continue

            # Pulizia dell'indice MultiIndex di Alpaca se presente
            if isinstance(data.index, pd.MultiIndex):
                data = data.xs(ticker, level=0)

            # Rinomina le colonne minuscole di Alpaca nel formato atteso dal codice
            data = data.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })

            if not data.empty and len(data) >= 20:
                res = analyze_etf(data, symbol=ticker)
                if res:
                    if res["is_idnr4"]:
                        idnr4_candidates.append(res)
                    elif res["is_fallback"]:
                        fallback_candidates.append(res)
        except Exception:
            continue

    log_print("\n" + "=" * 50)
    log_print("        ORDINAMENTO E GESTIONE SCALARE (ETF)")
    log_print("=" * 50)

    idnr4_candidates.sort(key=lambda x: x["momentum"], reverse=True)
    fallback_candidates.sort(key=lambda x: x["momentum"], reverse=True)
    all_candidates = idnr4_candidates + fallback_candidates

    order_sent = False

    if all_candidates:
        log_print(
            f"🏆 Trovati {len(all_candidates)} ETF candidati. Inizio iterazione dal migliore..."
        )

        for candidate in all_candidates:
            ticker = candidate["ticker"]
            c_type = (
                "IDNR4 Rigido" if candidate["is_idnr4"] else "Fallback Flessibile"
            )

            log_print(
                f"\n👉 Tentativo su ETF [{ticker}] | Tipo: {c_type} | Momentum:"
                f" {candidate['momentum']:.2f}%"
            )

            qty_to_buy = get_dynamic_quantity(candidate["entry"])
            success = place_bracket_order(
                ticker,
                candidate["entry"],
                candidate["sl"],
                candidate["tp"],
                qty_to_buy,
            )

            if success:
                log_print(
                    f"🎉 Missione compiuta: operazione aperta con successo sull'ETF {ticker}!"
                )
                order_sent = True
                break
            else:
                log_print(f"🔄 Fallito per {ticker}. Scorro al successivo in classifica...")
                continue

        if not order_sent:
            log_print("\n❌ Tutti i candidati ETF in classifica hanno fallito l'ordine.")
    else:
        log_print(
            "\n📭 Nessun ETF idoneo trovato con il pattern nell'ultima seduta."
        )
    log_print("=" * 50)

    # Scrive il log su file per eventuale tracciamento
    try:
        with open("execution_summary.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(log_output))
    except Exception:
        pass


if __name__ == "__main__":
    main()
