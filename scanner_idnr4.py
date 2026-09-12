from datetime import datetime, timedelta
import os
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

# Quantità di quote predefinite per singolo ETF
QUANTITY_TO_TRADE = 5


def analyze_id_nr4(df, symbol=""):
  """Logica di Toby Crabel: Inside Day + NR4 con Debug integrato"""
  if len(df) < 5:
    return False, 0, 0

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

  # --- STAMPA DI DEBUG ---
  print(f"\n🔍 [DEBUG {symbol}] Ultime 4 sedute (Range):")
  for i, r in enumerate(last_4_ranges):
    giorno_label = f"Oggi (Giorno -{3-i})" if i == 3 else f"Giorno -{3-i}"
    print(f"    {giorno_label}: {r:.4f}")
  print(
      f"    -> Inside Day: {is_inside} | NR4: {is_nr4} (Oggi:"
      f" {df['Range'].iloc[-1]:.4f} vs Minimo 4gg: {last_4_ranges.min():.4f})"
  )

  return is_inside and is_nr4, curr_high, curr_low


def place_bracket_order(symbol, entry, sl, tp):
  """Invia un ordine di tipo Stop con protezione Bracket (SL e TP) su Alpaca"""
  try:
    order_data = StopOrderRequest(
        symbol=symbol,
        qty=QUANTITY_TO_TRADE,
        side=OrderSide.BUY,
        stop_price=round(entry, 2),
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=round(tp, 2)),
        stop_loss=StopLossRequest(stop_price=round(sl, 2)),
    )

    order = trading_client.submit_order(order_data=order_data)
    print(
        f"  ✅ [ALPACA] Ordine inviato per {symbol} | ID ordine: {order.id}"
    )
    return True
  except Exception as e:
    print(f"  ❌ [ERRORE ALPACA] Impossibile inviare l'ordine per {symbol}: {e}")
    return False


def main():
  print(
      f"--- Avvio Scansione ID/NR4 (con Debug) su {len(ETF_WATCHLIST)} ETF ---"
  )

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=25)).strftime("%Y-%m-%d")

  found_etfs = []

  for ticker in ETF_WATCHLIST:
    try:
      data = yf.download(ticker, start=start_date, end=end_date, progress=False)
      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

      if not data.empty and len(data) >= 5:
        is_pattern, high, low = analyze_id_nr4(data, symbol=ticker)

        if is_pattern:
          candle_range = high - low
          entry = high
          sl = low
          tp = high + (candle_range * 2.0)

          print(f"  📌 Pattern ID/NR4 TROVATO su ETF: {ticker}!")
          print(
              f"     Livelli -> Entry: ${entry:.2f} | SL: ${sl:.2f} | TP:"
              f" ${tp:.2f}"
          )

          success = place_bracket_order(ticker, entry, sl, tp)
          if success:
            found_etfs.append(ticker)

    except Exception as e:
      print(f"  [ERRORE] Impossibile elaborare {ticker}: {e}")

  # --- RESOCONTO FINALE ---
  print("\n" + "=" * 50)
  print("             REPORT FINALE SCANSIONE ETF")
  print("=" * 50)
  if found_etfs:
    print(f"🎉 Trovati e negoziati {len(found_etfs)} ETF con pattern ID/NR4:")
    for etf in found_etfs:
      print(f"   - {etf}")
  else:
    print("📭 Nessun ETF ha soddisfatto i criteri ID/NR4 nell'ultima seduta.")
  print("=" * 50)


if __name__ == "__main__":
  main()
