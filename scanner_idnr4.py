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

# paper=True garantisce che l'ordine vada sulla simulazione di Alpaca
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

# 2. Watchlist estesa esattamente a 30 ETF di riferimento globale e settoriale
ETF_WATCHLIST = [
    # Indici Generali e Mercato USA (5)
    "SPY",
    "QQQ",
    "IWM",
    "MDY",
    "DIA",
    # Settori S&P 500 - GICS (11)
    "XLE",
    "XLF",
    "XLK",
    "XLV",
    "XLI",
    "XLP",
    "XLY",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
    # Tematici e Crescita (6)
    "SMH",
    "IGV",
    "ARKK",
    "XBI",
    "ITA",
    "KRE",
    # Materie Prime e Beni Rifugio (4)
    "GLD",
    "SLV",
    "USO",
    "DBA",
    # Obbligazionario e Macro (4)
    "TLT",
    "IEF",
    "HYG",
    "EEM",
]

# Rimuoviamo eventuali duplicati per sicurezza
ETF_WATCHLIST = list(dict.fromkeys(ETF_WATCHLIST))

# Percentuale del portafoglio da allocare sul miglior ETF (90%)
PORTFOLIO_ALLOCATION_PCT = 0.90


def analyze_id_nr4(df, symbol=""):
    """Logica di Toby Crabel: Inside Day + NR4 + Parametro di Momentum a 20 giorni"""
    if len(df) < 20:
        return False, 0, 0, 0

    df = df.copy()
    df["Range"] = df["High"] - df["Low"]

    curr_high = df["High"].iloc[-1]
    curr_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["Low"].iloc[-2]

    # Preleviamo le ultime 4 sedute per il controllo NR4
    last_4_ranges = df["Range"].iloc[-4:]

    # Condizione 1: Inside Day
    is_inside = (curr_high < prev_high) and (curr_low > prev_low)

    # Condizione 2: NR4 (il range odierno è il minimo delle ultime 4)
    is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()

    # Parametro di Selezione/Ranking: Momentum a 20 giorni (Rendimento percentuale)
    momentum_score = ((df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]) * 100

    # --- STAMPA DI DEBUG ---
    print(
        f"  [CHECK] {symbol} -> Inside: {is_inside} | NR4: {is_nr4} | "
        f"Momentum: {momentum_score:.2f}% (Oggi: {df['Range'].iloc[-1]:.4f} vs Min4g: {last_4_ranges.min():.4f})"
    )

    return is_inside and is_nr4, curr_high, curr_low, momentum_score


def get_dynamic_quantity(entry_price):
    """Calcola la quantità di quote per investire il 90% del capitale totale disponibile su Alpaca"""
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        target_investment = equity * PORTFOLIO_ALLOCATION_PCT
        
        if entry_price <= 0:
            return 1
            
        qty = int(target_investment / entry_price)
        return max(1, qty)  # Almeno 1 quota garantita se il capitale lo consente
    except Exception as e:
        print(f"  ⚠️ [AVVISO] Impossibile leggere il bilancio Alpaca ({e}). Uso default 5 quote.")
        return 5


def place_bracket_order(symbol, entry, sl, tp, qty):
    """Invia un ordine di tipo Stop con protezione Bracket (SL e TP) su Alpaca"""
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
        print(
            f"  ✅ [ALPACA] Ordine inviato per {symbol} | Qty: {qty} quote | ID ordine: {order.id}"
        )
        return True
    except Exception as e:
        print(f"  ❌ [ERRORE ALPACA] Impossibile inviare l'ordine per {symbol}: {e}")
        return False


def main():
    print(
        f"--- Avvio Scansione ID/NR4 (30 ETF | Selezione Top Momentum al 90%) ---"
    )

    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=35)).strftime("%Y-%m-%d")

    candidates = []

    for ticker in ETF_WATCHLIST:
        try:
            # Pausa di sicurezza per evitare blocchi da parte di Yahoo Finance
            time.sleep(0.3)
            
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            if not data.empty and len(data) >= 20:
                is_pattern, high, low, momentum = analyze_id_nr4(data, symbol=ticker)

                if is_pattern:
                    candle_range = high - low
                    entry = high
                    sl = low
                    tp = high + (candle_range * 2.0)  # Rapporto R:R 1:2

                    candidates.append({
                        "ticker": ticker,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "momentum": momentum
                    })

        except Exception as e:
            print(f"  [ERRORE] Impossibile elaborare {ticker}: {e}")

    # --- SELEZIONE DEL MIGLIORE TRA I CANDIDATI ---
    print("\n" + "=" * 50)
    print("         VALUTAZIONE E SCELTA DEL MIGLIOR ETF")
    print("=" * 50)

    if candidates:
        # Ordiniamo per Momentum decrescente (il valore più alto vince)
        candidates.sort(key=lambda x: x["momentum"], reverse=True)
        
        best_etf = candidates[0]
        print(f"🏆 Trovati {len(candidates)} ETF idonei. Il migliore per Momentum è: {best_etf['ticker']} ({best_etf['momentum']:.2f}%)")
        
        if len(candidates) > 1:
            print("   (Altri candidati validi ma scartati in favore del migliore):")
            for alt in candidates[1:]:
                print(f"    - {alt['ticker']} (Momentum: {alt['momentum']:.2f}%)")

        # Calcolo quote per allocare il 90% del capitale
        qty_to_buy = get_dynamic_quantity(best_etf["entry"])

        print(f"\n  📌 Esecuzione ordine al 90% su: {best_etf['ticker']}")
        print(
            f"     Livelli -> Entry: ${best_etf['entry']:.2f} | SL: ${best_etf['sl']:.2f} | "
            f"TP: ${best_etf['tp']:.2f} | Quote: {qty_to_buy}"
        )

        place_bracket_order(best_etf['ticker'], best_etf['entry'], best_etf['sl'], best_etf['tp'], qty_to_buy)
        
        print("\n" + "=" * 50)
        print(f"🎉 Operazione completata con successo sul miglior ETF: {best_etf['ticker']}")
        print("=" * 50)

    else:
        print("📭 Nessun ETF ha soddisfatto i criteri ID/NR4 nell'ultima seduta. Nessun ordine inviato.")
        print("=" * 50)


if __name__ == "__main__":
    main()
