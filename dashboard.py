import pandas as pd
import io
import yfinance as yf
import time


def load_sbi_csv_fixed(file_path):
    # 一度テキストファイルとして読み込む
    with open(file_path, 'r', encoding='shift-jis') as f:
        lines = f.readlines()

    all_data = []
    extracting = False
    
    for line in lines:
        # 「銘柄コード」で始まる行を見つけたら抽出開始（ヘッダーとして認識）
        if line.startswith('"銘柄コード"') or line.startswith('銘柄コード'):
            header = line.strip().split(',')
            header = [h.replace('"', '') for h in header] # 引用符の除去
            extracting = True
            continue
        
        # 空行や次のセクションの区切り（「株式（...）合計」など）に来たら抽出停止
        if extracting:
            if line.strip() == "" or "合計" in line:
                extracting = False
                continue
            
            # データのパース
            row = line.strip().split(',')
            # 余分な引用符を除去し、ヘッダーの列数に合わせる
            row = [r.replace('"', '') for r in row]
            if len(row) >= len(header):
                all_data.append(row[:len(header)])

    # データフレーム化
    df = pd.DataFrame(all_data, columns=header)
    
    # 型変換とクリーニング
    df['保有株数'] = pd.to_numeric(df['保有株数'].str.replace(',', ''), errors='coerce')
    df['銘柄コード'] = df['銘柄コード'].astype(str)
    
    # 同一銘柄が特定とNISAに分かれている場合、株数を合算
    df_sum = df.groupby(['銘柄コード', '銘柄名称'], as_index=False)['保有株数'].sum()
    
    return df_sum

# 実行
try:
    df_portfolio = load_sbi_csv_fixed('SaveFile.csv')
    print("--- 読み込み成功 ---")
    print(df_portfolio)
except Exception as e:
    print(f"エラーが発生しました: {e}")


def get_dividend_data(df):
    print("配当データを取得中...")
    dividends = []
    
    for ticker_code in df['銘柄コード']:
        # 日本株のコード形式（XXXX.T）に変換
        symbol = f"{ticker_code}.T"
        stock = yf.Ticker(symbol)
        
        try:
            # 予想配当（1株あたり）を取得
            # yfinanceの仕様上、取得できない場合は0とする
            div_rate = stock.info.get('dividendRate', 0)
            
            # もしdividendRateがNoneなら、過去の実績配当（trailingAnnualDividendYield）などを参照する
            if div_rate is None or div_rate == 0:
                div_rate = stock.info.get('trailingAnnualDividendRate', 0)
                
            dividends.append(div_rate)
            print(f"取得完了: {symbol} -> {div_rate}円")
        except Exception as e:
            print(f"取得失敗: {symbol} ({e})")
            dividends.append(0)
        
        # サーバー負荷軽減のため少し待機
        time.sleep(0.5)

    df['1株配当予測'] = dividends
    # 年間配当見込み額を計算
    df['年間配当見込み'] = df['保有株数'] * df['1株配当予測']
    
    return df

# 実行
df_result = get_dividend_data(df_portfolio)
print("\n--- 配当見込み集計結果 ---")
print(df_result[['銘柄名称', '保有株数', '1株配当予測', '年間配当見込み']])
print(f"\n総年間配当見込み額: {df_result['年間配当見込み'].sum():,.0f}円")