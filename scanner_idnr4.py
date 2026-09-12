from datetime import datetime, timedelta
import os
from io import StringIO
import pandas as pd
import requests
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

# paper=True garantisce che l'ordine vada sulla simulazione
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

# Parametri operativi
TICKER = "SPY"
QUANTITY_TO_TRADE = 10  # Numero di quote di SPY da negoziare


def analyze_id_nr4(df):
  """Logica di Toby Crabel: Inside Day + NR4"""
  if len(df) < 5:
    return False, 0, 0

  df = df.copy()
  df["Range"] = df["High"] - df["Low"]

  curr_high = df["High"].iloc[-1]
  curr_low = df["Low"].iloc[-1]
  prev_high = df["High"].iloc[-2]
  prev_low = df["Low"].iloc[-2]

  # Condizione 1: Inside Day (il range odierno è dentro quello di ieri)
  is_inside = (curr_high < prev_high) and (curr_low > prev_low)

  # Condizione 2: NR4 (il range odierno è il più basso delle ultime 4 sedute)
  is_nr4 = df["Range"].iloc[-1] == df["Range"].iloc[-4:].min()

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
        f"  [ALPACA] Ordine LONG inviato con successo per {symbol}! ID:"
        f" {order.id}"
    )
  except Exception as e:
    print(f"  [ERRORE ALPACA] Impossibile inviare l'ordine per {symbol}: {e}")


def main():
  print("--- Bot ID/NR4 su SPY con Esecuzione Automatica Alpaca ---")

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=20)).strftime("%Y-%m-%d")

  try:
    # Scarica i dati storici giornalieri di SPY
    data = yf.download(TICKER, start=start_date, end=end_date, progress=False)
    if isinstance(data.columns, pd.MultiIndex):
      data.columns = data.columns.droplevel(1)

    if not data.empty and len(data) >= 5:
      is_pattern, high, low = analyze_id_nr4(data)
      print(f"Analisi completata su {TICKER}: High={high:.2f}, Low={low:.2f}")

      if is_pattern:
        candle_range = high - low
        entry = high
        sl = low
        tp = high + (candle_range * 2.0)  # Rapporto Rischio/Rendimento 1:2

        print(f"\n📌 Pattern ID/NR4 rilevato su {TICKER}!")
        print(
            f"  -> Livelli calcolati: Entry (Buy Stop) ${entry:.2f} | SL"
            f" ${sl:.2f} | TP ${tp:.2f}"
        )

        # Invio dell'ordine automatico ad Alpaca
        place_bracket_order(TICKER, entry, sl, tp)
      else:
        print(
            f"Nessun pattern ID/NR4 riscontrato nell'ultima seduta su {TICKER}."
        )
    else:
      print("Dati storici insufficienti per l'analisi.")

  except Exception as e:
    print(f"Errore durante l'esecuzione dello script: {e}")


if __name__ == "__main__":
  main()
