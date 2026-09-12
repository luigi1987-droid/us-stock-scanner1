from datetime import datetime, timedelta
import os
import pandas as pd
import requests
import yfinance as yf

# Librerie Alpaca
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
)

# Utilizziamo i nomi esatti dei tuoi Secret di GitHub
API_KEY = os.getenv("ALPACA_API_KEY_ID")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

# paper=True garantisce che si usi il conto di simulazione
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

# Imposta quanti titoli comprare per ogni segnale
QUANTITY_PER_TRADE = 2


def get_top_us_tickers(n=300):
  try:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    table = pd.read_html(response.text)
    tickers = table[0]["Symbol"].tolist()
    return [t.replace(".", "-") for t in tickers[:n]]
  except Exception as e:
    print(f"Errore nel recupero dei ticker: {e}")
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def analyze_id_nr4(df):
  if len(df) < 5:
    return False, 0, 0
  df = df.copy()
  df["Range"] = df["High"] - df["Low"]
  curr_high = df["High"].iloc[-1]
  curr_low = df["Low"].iloc[-1]
  prev_high = df["High"].iloc[-2]
  prev_low = df["Low"].iloc[-2]

  is_inside = (curr_high < prev_high) and (curr_low > prev_low)
  is_nr4 = df["Range"].iloc[-1] == df["Range"].iloc[-4:].min()

  return is_inside and is_nr4, curr_high, curr_low


def place_alpaca_bracket_order(ticker, entry, sl, tp, side):
  """Invia un ordine di tipo Stop con Bracket (SL e TP) su Alpaca"""
  try:
    order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL

    order_data = StopOrderRequest(
        symbol=ticker,
        qty=QUANTITY_PER_TRADE,
        side=order_side,
        stop_price=round(entry, 2),
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=round(tp, 2)),
        stop_loss=StopLossRequest(stop_price=round(sl, 2)),
    )

    order = trading_client.submit_order(order_data=order_data)
    print(
        f"  [ALPACA] Ordine {side} inviato con successo per {ticker}! ID:"
        f" {order.id}"
    )
  except Exception as e:
    print(f"  [ERRORE ALPACA] Impossibile inviare ordine per {ticker}: {e}")


def main():
  print("--- Bot ID/NR4 con Esecuzione Automatica su Alpaca ---")
  tickers = get_top_us_tickers(300)
  print(f"Analisi in corso su {len(tickers)} titoli...\n")

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=20)).strftime("%Y-%m-%d")
  found_count = 0

  for ticker in tickers:
    try:
      data = yf.download(ticker, start=start_date, end=end_date, progress=False)
      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

      if not data.empty and len(data) >= 5:
        is_pattern, high, low = analyze_id_nr4(data)
        if is_pattern:
          found_count += 1
          candle_range = high - low

          # Scegliamo di operare sul lato Long (rottura a rialzo del massimo)
          entry = high
          sl = low
          tp = high + (candle_range * 2.0)  # R:R 1:2

          print(f"\n📌 Pattern trovato: {ticker}")
          print(
              f"  -> Invio ordine LONG: Entry ${entry:.2f} | SL ${sl:.2f} | TP"
              f" ${tp:.2f}"
          )

          # Invio effettivo dell'ordine su Alpaca
          place_alpaca_bracket_order(ticker, entry, sl, tp, "LONG")

    except Exception:
      continue

  print(f"\nScansione completata. Totale ordini processati: {found_count}")


if __name__ == "__main__":
  main()
