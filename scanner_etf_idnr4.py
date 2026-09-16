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

# Autenticazione con i Secret di GitHub
API_KEY = os.getenv("ALPACA_API_KEY_ID")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
PORTFOLIO_ALLOCATION_PCT = 0.90

# Watchlist dedicata agli ETF principali della borsa americana
ETF_WATCHLIST = [
    "SPY",
    "QQQ",
    "IWM",
    "MDY",
    "DIA",
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
    "SMH",
    "IGV",
    "ARKK",
    "XBI",
    "ITA",
    "KRE",
    "GLD",
    "SLV",
    "USO",
    "DBA",
    "TLT",
    "IEF",
    "HYG",
    "EEM",
]


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
    latest_trade = trading_client.get_latest_trade({"symbol": symbol})
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
    print(
        f"  ✅ [ALPACA] Ordine inviato con successo per ETF {symbol} | Qty: {qty}"
        f" | ID: {order.id}"
    )
    return True
  except Exception as e:
    print(f"  ❌ [ERRORE ALPACA] Impossibile inviare ordine per {symbol}: {e}")
    return False


def main():
  print("--- Avvio Scanner ID/NR4 su Watchlist ETF ---")
  print(f"Analisi in corso su {len(ETF_WATCHLIST)} ETF...")

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=35)).strftime("%Y-%m-%d")

  idnr4_candidates = []
  fallback_candidates = []

  for ticker in ETF_WATCHLIST:
    try:
      time.sleep(0.1)
      data = yf.download(ticker, start=start_date, end=end_date, progress=False)
      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

      if not data.empty and len(data) >= 20:
        res = analyze_etf(data, symbol=ticker)
        if res:
          if res["is_idnr4"]:
            idnr4_candidates.append(res)
          elif res["is_fallback"]:
            fallback_candidates.append(res)
    except Exception:
      continue

  print("\n" + "=" * 50)
  print("         ORDINAMENTO E GESTIONE SCALARE (ETF)")
  print("=" * 50)

  idnr4_candidates.sort(key=lambda x: x["momentum"], reverse=True)
  fallback_candidates.sort(key=lambda x: x["momentum"], reverse=True)
  all_candidates = idnr4_candidates + fallback_candidates

  order_sent = False

  if all_candidates:
    print(
        f"🏆 Trovati {len(all_candidates)} ETF candidati. Inizio iterazione"
        " dal migliore..."
    )

    for candidate in all_candidates:
      ticker = candidate["ticker"]
      c_type = (
          "IDNR4 Rigido" if candidate["is_idnr4"] else "Fallback Flessibile"
      )

      print(
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
        print(
            f"🎉 Missione compiuta: operazione aperta con successo sull'ETF"
            f" {ticker}!"
        )
        order_sent = True
        break
      else:
        print(f"🔄 Fallito per {ticker}. Scorro al successivo in classifica...")
        continue

    if not order_sent:
      print("\n❌ Tutti i candidati ETF in classifica hanno fallito l'ordine.")
  else:
    print(
        "\n📭 Nessun ETF idoneo trovato con il pattern nell'ultima seduta."
    )
  print("=" * 50)


if __name__ == "__main__":
  main()
