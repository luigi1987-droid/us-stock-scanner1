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

# 2. Watchlist estesa a 30 ETF di riferimento globale e settoriale
ETF_WATCHLIST = [
    # Indici Generali e Mercato USA
    "SPY",
    "QQQ",
    "IWM",
    "MDY",
    "DIA",
    # Settori S&P 500 (GICS)
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
    # Tematici e Crescita
    "SMH",
    "IGV",
    "ARKK",
    "XBI",
    "ITA",
    "KRE",
    # Materie Prime e Beni Rifugio
    "GLD",
    "SLV",
    "USO",
    "DBA",
    # Obbligazionario e Macro
    "TLT",
    "IEF",
    "HYG",
    "EEM",
]

# Rimuoviamo eventuali duplicati
ETF_WATCHLIST = list(dict.fromkeys(ETF_WATCHLIST))

# Percentuale del portafoglio da allocare sulmiglior ETF (90%)
PORTFOLIO_ALLOCATION_PCT = 0.90


def analyze_id_nr4(df, symbol=""):
    """Logica di Toby Crabel: Inside Day + NR4 con Debug integrato"""
    if len(df) < 5:
        return False, 0, 0, 0

    df = df.copy()
    df["Range"] = df["High"] - df["Low"]

    curr_high = df["High"].iloc[-1]
    curr_low = df["Low"].iloc[-1]
    prev_high = df["High"].iloc[-2]
    prev_low = df["High"].iloc[-2]

    # Preleviamo le ultime 4 sedute per il controllo NR4
    last_4_ranges = df["Range"].iloc[-4:]

    # Condizione 1: Inside Day
    is_inside = (curr_high < prev_high) and (curr_low > prev_low)

    # Condizione 2: NR4 (il range odierno è il minimo delle ultime 4)
    is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()

    # Parametro di ranking: Momentum a 20 giorni (Rendimento percentuale recente)
    # Serve a premiare l'ETF che mostra la forza relativa più alta tra i candidati
    momentum_score = ((df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]) * 100 if len(df) >= 20 else 0.0

    # --- STAMPA DI DEBUG ---
    print(
        f"  [CHECK] {symbol} -> Inside: {is_inside} | NR4: {is_nr4} | "
        f"Momentum 20g: {momentum_score:.2f}% (Oggi: {df['Range'].iloc[-1]:.4f} vs Min4g: {last_4_ranges.min():.4f})"
    )

    return is_inside and is_nr4, curr_high, curr_low, momentum_score


def get_dynamic_quantity(entry_price):
    """Calcola la quantità di quote per investire il 90% del capitale disponibile su Alpaca"""
    try:
        account = trading_client.get_account()
        # Usiamo il potere d'acquisto o il cash/equity disponibile nel conto paper
        equity = float(account.equity)
        target_investment = equity * PORTFOLIO_ALLOCATION_PCT
        
        if entry_price <= 0:
            return 1
            
        qty = int(target_investment / entry_price)
        # Assicuriamoci di comprare almeno 1 quota se il capitale lo permette
        return max(1, qty)
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
        f"--- Avvio Scansione ID/NR4 (Selezione Migliore al 90%) su {len(ETF_WATCHLIST)} ETF ---"
    )

    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=35)).strftime("%Y-%m-%d")

    candidates = []

    for ticker in ETF_WATCHLIST:
        try:
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
                    tp = high + (candle_reg * 2.0) if 'candle_reg' in locals() else high + (candle_range * 2.0)

                    candidates.append({
                        "ticker": ticker,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "momentum": momentum
                    })

        except Exception as e:
            print(f"  [ERRORE] Impossibile elaborare {ticker}: {e}")

    # --- SELEZIONE DEL MIGLIORE TRA I CANDIDATI TROVATI ---
    print("\n" + "=" * 50)
    print("         VALUTAZIONE E SCELTA DEL MIGLIOR ETF")
    print("=" * 50)

    if candidates:
        # Ordiniamo i candidati in base al Momentum decrescente (scegliamo quello più forte)
        candidates.sort(key=lambda x: x["momentum"], reverse=True)
        
        best_etf = candidates[0]
        print(f"🏆 Trovati {len(candidates)} candidati validi. Il migliore per Momentum è: {best_etf['ticker']} ({best_etf['momentum']:.2f}%)")
        
        # Mostriamo gli altri scartati per trasparenza nei log
        if len(candidates) > 1:
            print("   (Candidati alternativi scartati in questa sessione):")
            for alt in candidates[1:]:
                print(f"    - {alt['ticker']} (Momentum: {alt['momentum']:.2f}%)")

        # Calcoliamo la quantità per investire il 90% sul migliore
        qty_to_buy = get_dynamic_quantity(best_etf["entry"])

        print(f"\n  📌 Allocazione 90% sul vincitore: {best_etf['ticker']}")
        print(
            f"     Livelli -> Entry: ${best_etf['entry']:.2f} | SL: ${best_etf['sl']:.2f} | "
            f"TP: ${best_etf['tp']:.2f} | Quote calcolate: {qty_to_buy}"
        )

        place_bracket_order(best_etf['ticker'], best_etf['entry'], best_etf['sl'], best_etf['tp'], qty_to_buy)
        
        print("\n" + "=" * 50)
        print(f"🎉 Negoziato con successo il miglior ETF: {best_etf['ticker']}")
        print("=" * 50)

    else:
        print("📭 Nessun ETF ha soddisfatto i criteri ID/NR4 nell'ultima seduta. Nessun ordine inviato.")
        print("=" * 50)


if __name__ == "__main__":
    main()
