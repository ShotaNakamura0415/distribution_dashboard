import pandas as pd
import yfinance as yf
import time

def test_dividend_details(ticker_code):
    symbol = f"{ticker_code}.T"
    stock = yf.Ticker(symbol)
    
    print(f"\n--- 診断: {symbol} ---")
    
    # 1. 基本的な配当額の確認
    info = stock.info
    div_rate = info.get('dividendRate')
    trailing_div = info.get('trailingAnnualDividendRate')
    print(f"  [info] dividendRate: {div_rate}")
    print(f"  [info] trailingAnnualDividendRate: {trailing_div}")

    # 2. main.py で失敗している 'calendar' の中身を確認
    print("  [calendar] 取得データ:")
    try:
        cal = stock.calendar
        print(f"    {cal}")
        # 権利落ち日や配当日の特定を試みる
        if isinstance(cal, dict):
            print(f"    - Dividend Date: {cal.get('Dividend Date')}")
            print(f"    - Ex-Dividend Date: {cal.get('Ex-Dividend Date')}")
    except Exception as e:
        print(f"    - calendar取得エラー: {e}")

    # 3. 過去の配当履歴から「月」を推測する（バックアッププラン）
    print("  [history] 過去の配当実績から月を判定:")
    try:
        div_history = stock.dividends
        if not div_history.empty:
            # 直近2回分（中間・期末）の月を確認
            recent_months = div_history.tail(2).index.month.tolist()
            print(f"    - 直近の配当月実績: {recent_months}")
        else:
            print("    - 配当履歴が見つかりません")
    except Exception as e:
        print(f"    - history取得エラー: {e}")

# テスト実行（お手持ちの銘柄コードをいくつか入れてください）
test_codes = ['3249', '3468', '7867'] # 例: NTT, オリックス, 郵船
for code in test_codes:
    test_dividend_details(code)
    time.sleep(1)