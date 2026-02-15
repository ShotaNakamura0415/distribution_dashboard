import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import time
from datetime import datetime
import logger_test as dbg

# ページ設定
st.set_page_config(page_title="SBI配当可視化ツール", layout="wide")
st.title("📈 SBI証券 配当金見込みダッシュボード")

# CSV読み込み関数
def load_sbi_csv_fixed(file_content):
    lines = file_content.decode("shift-jis").splitlines()
    all_data = []
    extracting = False
    header = []

    for line in lines:
        if line.startswith('"銘柄コード"') or line.startswith("銘柄コード"):
            header = [h.replace('"', "") for h in line.strip().split(",")]
            extracting = True
            continue
        if extracting:
            if line.strip() == "" or "合計" in line:
                extracting = False
                continue
            row = [r.replace('"', "") for r in line.strip().split(",")]
            if len(row) >= len(header):
                all_data.append(row[: len(header)])

    df = pd.DataFrame(all_data, columns=header)
    df["保有株数"] = pd.to_numeric(df["保有株数"].str.replace(",", ""), errors="coerce")
    return df.groupby(["銘柄コード", "銘柄名称"], as_index=False)["保有株数"].sum()

# サイドバーでファイルアップロード
uploaded_file = st.sidebar.file_uploader(
    "SBI証券のCSVファイルをアップロードしてください", type="csv"
)

if uploaded_file is not None:
    if 'raw_df' not in st.session_state:
        st.session_state['raw_df'] = load_sbi_csv_fixed(uploaded_file.read())
    
    df_portfolio = st.session_state['raw_df']

    if st.sidebar.button("配当データを取得・更新"):
        dbg.log_portfolio_data(df_portfolio)
        with st.spinner("詳細な配当スケジュールを取得中..."):
            dividends_per_share = []
            monthly_data = {m: 0 for m in range(1, 13)}
            progress_bar = st.progress(0)

            for i, row in df_portfolio.iterrows():
                ticker = row["銘柄コード"]
                shares = row["保有株数"]
                symbol = f"{ticker}.T"
                stock = yf.Ticker(symbol)

                try:
                    info = stock.info
                    total_annual_div = info.get("trailingAnnualDividendRate") or info.get("dividendRate") or 0
                    
                    hist = stock.dividends
                    months = []
                    div_rate_calculated = 0

                    if not hist.empty:
                        last_year_divs = hist.tail(2)
                        months = last_year_divs.index.month.tolist()
                        div_rate_calculated = total_annual_div / len(months) if len(months) > 0 else total_annual_div
                    else:
                        cal = stock.calendar
                        ex_date = cal.get("Ex-Dividend Date") if isinstance(cal, dict) else None
                        if ex_date:
                            months = [ex_date.month]
                            div_rate_calculated = total_annual_div
                        else:
                            months = [3, 9] 
                            div_rate_calculated = total_annual_div / 2

                    dividends_per_share.append(div_rate_calculated)
                    total_div_amount = div_rate_calculated * shares * len(months)
                    
                    # ログ出力用に入金予定月（+3ヶ月）を計算
                    payment_months = [(m + 2) % 12 + 1 for m in months]
                    dbg.log_dividend_process(symbol, div_rate_calculated, payment_months, total_div_amount)

                    # 3. 入金月（権利確定月の3か月後）への振り分け
                    amount_per_event = div_rate_calculated * shares
                    if months:
                        for m in months:
                            # 3ヶ月シフトの計算: (m + 2) % 12 + 1 
                            # 例: 10月 -> (10+2)%12 + 1 = 1月 / 11月 -> (11+2)%12 + 1 = 2月
                            payment_month = (m + 2) % 12 + 1
                            monthly_data[payment_month] += amount_per_event

                except Exception as e:
                    st.error(f"{symbol} のデータ取得中にエラー: {e}")
                    dividends_per_share.append(0)

                progress_bar.progress((i + 1) / len(df_portfolio))
                time.sleep(0.05)

            df_portfolio["1株配当予測"] = dividends_per_share
            df_portfolio["年間配当見込み"] = df_portfolio["保有株数"] * df_portfolio["1株配当予測"] * (df_portfolio.index.map(lambda x: len(months) if 'months' in locals() else 2))
            
            st.session_state["df_result"] = df_portfolio
            st.session_state["monthly_div"] = pd.DataFrame(
                {
                    "月": [f"{m}月" for m in range(1, 13)],
                    "配当金": [monthly_data[m] for m in range(1, 13)],
                }
            )
            
            dbg.log_final_summary(st.session_state["monthly_div"], df_portfolio)
            st.rerun()

    if "df_result" in st.session_state:
        df = st.session_state["df_result"]
        df_monthly = st.session_state["monthly_div"]

        st.subheader("🗓️ 月別配当カレンダー（入金ベース）")
        fig_monthly = px.bar(
            df_monthly,
            x="月",
            y="配当金",
            text_auto=".0f",
            color_discrete_sequence=["#00CC96"],
        )
        fig_monthly.update_layout(xaxis_title="入金月", yaxis_title="配当金 (円)")
        st.plotly_chart(fig_monthly, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("銘柄別配当（年間）")
            st.plotly_chart(px.bar(df.sort_values("年間配当見込み"), x="年間配当見込み", y="銘柄名称", orientation="h"), use_container_width=True)
        with col2:
            st.subheader("配当構成比")
            st.plotly_chart(px.pie(df, values="年間配当見込み", names="銘柄名称"), use_container_width=True)

        st.subheader("詳細データ一覧")
        st.dataframe(df, use_container_width=True)