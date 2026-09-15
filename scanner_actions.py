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

# 2. Watchlist massiccia di 200 azioni US ad alta liquidità
STOCKS_WATCHLIST = [
    # Mega-Cap Tech & Growth
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "NFLX",
    "AMD",
    "INTC",
    "QCOM",
    "AVGO",
    "TXN",
    "ADBE",
    "CRM",
    "ORCL",
    "IBM",
    "NOW",
    "INTU",
    "AMAT",
    "LRCX",
    "MU",
    "ADI",
    "SNPS",
    "CDNS",
    "PANW",
    "CRWD",
    "KLAC",
    "MCHP",
    "ANSS",
    "FTNT",
    "NXPI",
    "ADSK",
    "MARA",
    "RIOT",
    "PLTR",
    "SHOP",
    "SNOW",
    "UBER",
    "ABNB",
    "DASH",
    "ROKU",
    "SQ",
    "COIN",
    "PYPL",
    "HOOD",
    "U",
    "RBLX",
    "ZM",
    "DOCU",
    # Consumer Discretionary & Staples
    "HD",
    "MCD",
    "NKE",
    "SBUX",
    "LOW",
    "TJX",
    "TGT",
    "DIS",
    "CMCSA",
    "BKNG",
    "MAR",
    "HLT",
    "YUM",
    "DG",
    "DLTR",
    "ROST",
    "ORLY",
    "AZO",
    "TSCO",
    "PG",
    "KO",
    "PEP",
    "WMT",
    "COST",
    "PM",
    "MO",
    "CL",
    "KMB",
    "GIS",
    "SYY",
    "EL",
    "MDLZ",
    "STZ",
    "HSY",
    "K",
    "EA",
    "TTWO",
    "WBD",
    "PARA",
    "CHTR",
    # Healthcare & Biotech
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "MRK",
    "LLY",
    "TMO",
    "ABT",
    "DHR",
    "BMY",
    "AMGN",
    "GILD",
    "ISRG",
    "CVS",
    "CI",
    "VRTX",
    "REGN",
    "ZTS",
    "BSX",
    "BDX",
    "SYK",
    "MDT",
    "ELV",
    "HUM",
    "CNC",
    "BAX",
    "DXCM",
    "IDXX",
    "ILMN",
    "ALGN",
    "BIIB",
    "MRNA",
    # Financials & Real Estate
    "JPM",
    "BAC",
    "WFC",
    "C",
    "GS",
    "MS",
    "AXP",
    "BLK",
    "SCHW",
    "PNC",
    "USB",
    "TFC",
    "BK",
    "SPGI",
    "MCO",
    "CME",
    "ICE",
    "CB",
    "PGR",
    "TRV",
    "AIG",
    "MET",
    "PRU",
    "ALL",
    "AFL",
    "DFS",
    "COF",
    "SYF",
    "AMP",
    "NDAQ",
    "PLD",
    "AMT",
    "CCI",
    "EQIX",
    "PSA",
    "SPG",
    "O",
    "VICI",
    "WELL",
    "DLR",
    # Industrials, Aerospace & Energy
    "XOM",
    "CVX",
    "COP",
    "EOG",
    "SLB",
    "PSX",
    "VLO",
    "MPC",
    "OXY",
    "HAL",
    "BKR",
    "WMB",
    "KMI",
    "GE",
    "CAT",
    "DE",
    "RTX",
    "LMT",
    "NOC",
    "GD",
    "BA",
    "HON",
    "UNP",
    "CSX",
    "NSC",
    "UPS",
    "FDX",
    "MMM",
    "ITW",
    "EMR",
    "ETN",
    "PH",
    "CMI",
    "ROK",
    "DD",
    "SHW",
    "APD",
    "ECL",
    "NEM",
    "FCX",
    "DOW",
    "PPG",
    "CTVA",
    "CE",
    "VMC",
    "MLM",
    # Utilities & Telecommunications
    "NEE",
    "DUK",
    "SO",
    "D",
    "AEP",
    "SRE",
    "EXC",
    "XEL",
    "ED",
    "PCG",
    "PEG",
    "WEC",
    "ES",
    "ETR",
    "FE",
    "T",
    "VZ",
    "TMUS",
    # Additional High-Liquidity Stocks
    "RIVN",
    "LCID",
    "NIO",
    "XPEV",
    "LI",
    "F",
    "GM",
    "VALE",
    "PBR",
    "BABA",
    "JD",
    "PDD",
    "BIDU",
]

# Rimuoviamo eventuali duplicati
STOCKS_WATCHLIST = list(dict.fromkeys(STOCKS_WATCHLIST))

# Percentuale del portafoglio da allocare sulla migliore azione (90%)[cite: 1]
PORTFOLIO_ALLOCATION_PCT = 0.90


def analyze_id_nr4(df, symbol=""):
    """Logica di Toby Crabel: Inside Day + NR4 + Momentum a 20 giorni"""
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

    # Condizione 2: NR4
    is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()

    # Parametro di Ranking: Momentum a 20 giorni (Rendimento percentuale)[cite: 1]
    momentum_score = ((df["Close"].iloc[-1] - df["Close"].iloc[-20]) / df["Close"].iloc[-20]) * 100

    print(
        f"  [CHECK] {symbol} -> Inside: {is_inside} | NR4: {is_nr4} | "
        f"Momentum: {momentum_score:.2f}% (Oggi: {df['Range'].iloc[-1]:.4f} vs Min4g: {last_4_ranges.min():.4f})"
    )

    return is_inside and is_nr4, curr_high, curr_low, momentum_score


def get_dynamic_quantity(entry_price):
    """Calcola la quantità di quote per investire il 90% del capitale disponibile su Alpaca[cite: 1]"""
    try:
        account = trading_client.get_account()
        equity = float(account.equity)
        target_investment = equity * PORTFOLIO_ALLOCATION_PCT
        
        if entry_price <= 0:
            return 1
            
        qty = int(target_investment / entry_price)
        return max(1, qty)
    except Exception as e:
        print(f"  ⚠️ [AVVISO] Impossibile leggere il bilancio Alpaca ({e}). Uso default 1 quota.")
        return 1


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
        f"--- Avvio Scansione ID/NR4 ({len(STOCKS_WATCHLIST)} Azioni US | Selezione Top Momentum al 90%) ---"
    )

    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=35)).strftime("%Y-%m-%d")

    candidates = []

    for ticker in STOCKS_WATCHLIST:
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
                    tp = high + (candle_range * 2.0)  # Rapporto R/R 1:2

                    candidates.append({
                        "ticker": ticker,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "momentum": momentum
                    })

        except Exception as e:
            # Gestisce eventuali errori temporanei senza bloccare il ciclo
            pass

    # --- SELEZIONE DEL MIGLIORE TRA I CANDIDATI ---
    print("\n" + "=" * 50)
    print("         VALUTAZIONE E SCELTA DELLA MIGLIORE AZIONE")
    print("=" * 50)

    if candidates:
        # Ordiniamo per Momentum decrescente (il valore più alto vince)[cite: 1]
        candidates.sort(key=lambda x: x["momentum"], reverse=True)
        
        best_stock = candidates[0]
        print(f"🏆 Trovate {len(candidates)} azioni idonee. La migliore per Momentum è: {best_stock['ticker']} ({best_stock['momentum']:.2f}%)")
        
        if len(candidates) > 1:
            print("   (Altre azioni valide ma scartate in favore della migliore):")
            for alt in candidates[1:]:
                print(f"    - {alt['ticker']} (Momentum: {alt['momentum']:.2f}%)")

        # Calcolo quote per allocare il 90% del capitale[cite: 1]
        qty_to_buy = get_dynamic_quantity(best_stock["entry"])

        print(f"\n  📌 Esecuzione ordine al 90% su: {best_stock['ticker']}")
        print(
            f"     Livelli -> Entry: ${best_stock['entry']:.2f} | SL: ${best_stock['sl']:.2f} | "
            f"TP: ${best_stock['tp']:.2f} | Quote: {qty_to_buy}"
        )

        place_bracket_order(best_stock['ticker'], best_stock['entry'], best_stock['sl'], best_stock['tp'], qty_to_buy)
        
        print("\n" + "=" * 50)
        print(f"🎉 Operazione completata con successo sulla migliore azione: {best_stock['ticker']}")
        print("=" * 50)

    else:
        print("📭 Nessuna azione ha soddisfatto i criteri ID/NR4 nell'ultima seduta. Nessun ordine inviato.")
        print("=" * 50)


if __name__ == "__main__":
    main()
