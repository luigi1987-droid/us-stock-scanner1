from datetime import datetime, timedelta
import pandas as pd
import requests
import yfinance as yf


def get_top_us_tickers(n=300):
  """Ottiene i primi n ticker dal listino S&P 500 aggirando il blocco 403"""
  try:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # Scarica la pagina HTML con i headers corretti
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    # Legge la tabella dal contenuto HTML scaricato
    table = pd.read_html(response.text)
    df = table[0]
    tickers = df["Symbol"].tolist()

    # Sostituisce il punto con il trattino per compatibilità con Yahoo Finance (es. BRK.B -> BRK-B)
    tickers = [t.replace(".", "-") for t in tickers]
    return tickers[:n]
  except Exception as e:
    print(f"Errore nel recupero della lista dei ticker: {e}")
    # Fallback esteso di emergenza con i principali titoli USA
    return [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "BRK-B",
        "UNH",
        "JNJ",
        "XOM",
        "JPM",
        "V",
        "PG",
        "MA",
        "HD",
        "CVX",
        "MRK",
        "ABBV",
        "PEP",
    ][:n]


def check_id_nr4(df):
  """Verifica se l'ultima barra disponibile soddisfa il pattern ID/NR4"""
  if len(df) < 5:
    return False

  df = df.copy()
  df["Range"] = df["High"] - df["Low"]

  curr_high = df["High"].iloc[-1]
  curr_low = df["Low"].iloc[-1]
  prev_high = df["High"].iloc[-2]
  prev_low = df["Low"].iloc[-2]

  # 1. Condizione Inside Day (ID): Massimo inferiore e minimo superiore al giorno precedente
  is_inside = (curr_high < prev_high) and (curr_low > prev_low)

  if not is_inside:
    return False

  # 2. Condizione Narrow Range 4 (NR4): Il range odierno è il più piccolo delle ultime 4 barre
  last_4_ranges = df["Range"].iloc[-4:]
  is_nr4 = df["Range"].iloc[-1] == last_4_ranges.min()

  return is_nr4


def main():
  print("--- Avvio Scanner ID/NR4 per la Borsa Americana ---")
  tickers = get_top_us_tickers(300)
  print(f"Analisi in corso su {len(tickers)} titoli...")

  matched_stocks = []
  end_date = datetime.today().strftime("%Y-%m-%d")
  start_date = (datetime.today() - timedelta(days=20)).strftime("%Y-%m-%d")

  for ticker in tickers:
    try:
      data = yf.download(ticker, start=start_date, end=end_date, progress=False)

      # Gestione della struttura dati di yfinance
      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

      if not data.empty and len(data) >= 5:
        if check_id_nr4(data):
          matched_stocks.append(ticker)
    except Exception:
      continue

  print("\n" + "=" * 40)
  print(" RISULTATI PATTERN ID/NR4")
  print("=" * 40)
  if matched_stocks:
    print(f"Trovati {len(matched_stocks)} titoli con il pattern:")
    for t in matched_stocks:
      print(f"  [TROVATO] {t}")
  else:
    print("Nessun titolo soddisfa il pattern ID/NR4 nell'ultima seduta.")
  print("=" * 40)


if __name__ == "__main__":
  main()
