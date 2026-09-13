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

# 2. Watchlist asiatica
ASIA_WATCHLIST = [
    "BABA",
    "JD",
    "PDD",
    "BIDU",
    "NTES",
    "NIO",
    "XPEV",
    "LI",
    "YUMC",
    "TME",
    "BILI",
    "ZTO",
    "BEKE",
    "TAL",
    "EDU",
    "TSM",
    "UMC",
    "ASX",
    "TM",
    "SONY",
    "HMC",
    "MUFG",
    "SMFG",
    "NMR",
    "INFY",
    "WIT",
    "RDY",
    "IBN",
    "HDB",
    "SE",
    "CPNG",
    "FXI",
    "MCHI",
    "KWEB",
    "ASHR",
    "EWJ",
    "EWY",
    "EWT",
    "INDA",
    "PIN",
    "AAXJ",
    "EEM",
]

ASIA_WATCHLIST = list(dict.fromkeys(ASIA_WATCHLIST))
QUANTITY_TO_TRADE = 2


def analyze_id_nr4(df, symbol=""):
  if len(df) < 5:
    return False, 0, 0

  df = df.copy()
  df["Range"] = df["High"] - df["Low"]

  curr_high = df["High"].iloc[-1]
  curr_low = df["Low"].iloc[-1]
  prev_high = df["High"].iloc[-2]
  prev_low = df["Low"].iloc[-2]

  last_4_ranges = df["Range"].iloc[-4:]

  is_inside = (curr_high < prev_high) and (curr_low > prev_low)
  is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()

  # Debug compatto
  print(
      f"  [CHECK] {symbol} -> Inside: {is_inside} | NR4: {is_nr4} (Oggi:"
      f" {df['Range'].iloc[-1]:.2f} vs Min4g: {last_4_ranges.min():.2f})"
  )

  return is_inside and is_nr4, curr_high, curr_low


def place_bracket_order(symbol, entry, sl, tp):
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
      f"--- Avvio Scansione ID/NR4 su {len(ASIA_WATCHLIST)} Asset Asiatici ---"
  )

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=25)).strftime("%Y-%m-%d")

  found_assets = []

  for ticker in ASIA_WATCHLIST:
    try:
      # Aggiungiamo un piccolo delay per non sovraccaricare le API di yfinance
      time.sleep(0.3)

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

          print(f"  📌 Pattern ID/NR4 TROVATO su: {ticker}!")
          print(
              f"     Livelli -> Entry: ${entry:.2f} | SL: ${sl:.2f} | TP:"
              f" ${tp:.2f}"
          )

          success = place_bracket_order(ticker, entry, sl, tp)
          if success:
            found_assets.append(ticker)

    except Exception as e:
      print(f"  ⚠️ [AVVISO] Saltato {ticker} per problema dati: {e}")

  # --- RESOCONTO FINALE ---
  print("\n" + "=" * 50)
  print("         REPORT FINALE SCANSIONE MERCATO ASIATICO")
  print("=" * 50)
  if found_assets:
    print(
        f"🎉 Trovati e negoziati {len(found_assets)} asset asiatici con pattern"
        " ID/NR4:"
    )
    for asset in found_assets:
      print(f"   - {asset}")
  else:
    print(
        "📭 Nessun asset asiatico ha soddisfatto i criteri ID/NR4 nell'ultima"
        " seduta."
    )
  print("=" * 50)


if __name__ == "__main__":
  main()

