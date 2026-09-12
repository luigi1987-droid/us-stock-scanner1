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
    "TSLA",
    "AMZN",
    "HD",
    "MCD",
    "NKE",
    "SBUX",
    "LOW",
    "TJX",
    "TGT",
    "DIS",
    "NFLX",
    "CMCSA",
    "BKNG",
    "ABNB",
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

# Rimuoviamo eventuali duplicati derivanti da accorpamenti di settori
STOCKS_WATCHLIST = list(dict.fromkeys(STOCKS_WATCHLIST))

# Quantità prudenziale per azione (essendo 200 titoli, 1 quota per ordine riduce l'impatto sul margine)
QUANTITY_TO_TRADE = 1


def analyze_id_nr4(df):
  """Logica di Toby Crabel: Inside Day + NR4"""
  if len(df) < 5:
    return False, 0, 0

  df = df.copy()
  df["Range"] = df["High"] - df["Low"]

  curr_high = df["High"].iloc[-1]
  curr_low = df["High"].iloc[-1]
  prev_high = df["High"].iloc[-2]
  prev_low = df["High"].iloc[-2]

  # Condizione 1: Inside Day
  is_inside = (curr_high < prev_high) and (curr_low > prev_low)

  # Condizione 2: NR4
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
        f"  [ALPACA] Ordine LONG inviato con successo per l'azione {symbol}! ID:"
        f" {order.id}"
    )
  except Exception as e:
    print(
        f"  [ERRORE ALPACA] Impossibile inviare l'ordine per l'azione {symbol}:"
        f" {e}"
    )


def main():
  print(
      f"--- Bot ID/NR4 per Azioni ({len(STOCKS_WATCHLIST)} Titoli) con Alpaca"
      " ---"
  )

  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=25)).strftime("%Y-%m-%d")

  for ticker in STOCKS_WATCHLIST:
    print(f"Analisi in corso per l'azione: {ticker}...")
    try:
      data = yf.download(ticker, start=start_date, end=end_date, progress=False)
      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

      if not data.empty and len(data) >= 5:
        is_pattern, high, low = analyze_id_nr4(data)

        if is_pattern:
          candle_range = high - low
          entry = high
          sl = low
          tp = high + (candle_range * 2.0)  # Rapporto R/R 1:2

          print(f"  📌 Pattern ID/NR4 rilevato sull'azione {ticker}!")
          print(
              f"     Livelli -> Entry: ${entry:.2f} | SL: ${sl:.2f} | TP:"
              f" ${tp:.2f}"
          )

          # Invio dell'ordine automatico ad Alpaca
          place_bracket_order(ticker, entry, sl, tp)
      else:
        pass  # Evita di stampare troppi log vuoti per 200 titoli

    except Exception as e:
      print(f"  [ERRORE] Impossibile elaborare {ticker}: {e}")

  print("\n--- Scansione delle 200 Azioni completata ---")


if __name__ == "__main__":
  main()
