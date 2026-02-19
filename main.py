import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from datetime import datetime
import io
import csv
import re

# ページ設定
st.set_page_config(page_title="SBI配当可視化ツール", layout="wide")
st.title("📈 SBI証券 配当金見込みダッシュボード")

# --- 1. 実績データの読み込み (要件: 実績がある月はそのまま計上) ---
def load_dividend_history(file_content):
    text = file_content.decode("shift-jis")
    f = io.StringIO(text)
    reader = csv.reader(f, quoting=csv.QUOTE_ALL)
    lines = list(reader)
    header_idx = -1
    for i, row in enumerate(lines):
        if len(row) > 1 and "受渡日" in row and "銘柄名" in row:
            header_idx = i
            break
    if header_idx == -1: return [], set()

    header = lines[header_idx]
    data_rows = [row for row in lines[header_idx + 1:] if len(row) == len(header) and "/" in row[0]]
    
    df_hist = pd.DataFrame(data_rows, columns=header)
    df_hist["受渡日"] = pd.to_datetime(df_hist["受渡日"], errors='coerce')
    df_hist["受取額(税引後・円)"] = pd.to_numeric(df_hist["受取額(税引後・円)"].str.replace(",", ""), errors="coerce")
    
    # 2026年の実績を抽出
    df_2026 = df_hist[df_hist["受渡日"].dt.year == 2026].dropna(subset=["受取額(税引後・円)"])
    
    actual_list = []
    paid_codes_this_month = set()
    current_month = datetime.now().month

    for _, r in df_2026.iterrows():
        code_match = re.search(r'(\d{4})', r["銘柄名"])
        code = code_match.group(1) if code_match else ""
        
        # 実績として追加
        actual_list.append({
            "月": r["受渡日"].month,
            "銘柄名": r["銘柄名"],
            "金額": r["受取額(税引後・円)"],
            "コード": code,
            "区分": "実績(確定)"
        })
        # 今月すでに入金済みの銘柄コードを記録（要件2のため）
        if r["受渡日"].month == current_month:
            paid_codes_this_month.add(code)
            
    return actual_list, paid_codes_this_month

# --- 保有資産データの読み込み ---
def load_portfolio_csv(file_content):
    text = file_content.decode("shift-jis")
    f = io.StringIO(text)
    reader = csv.reader(f)
    all_data, header, extracting = [], [], False
    for row in reader:
        if not row: continue
        if "銘柄コード" in row[0]:
            header = row
            extracting = True
            continue
        if extracting:
            if "合計" in row[0] or not row[0]:
                extracting = False
                continue
            all_data.append(row)
    df = pd.DataFrame(all_data, columns=header)
    df["銘柄コード"] = df["銘柄コード"].astype(str).str.extract(r'(\d{4})')
    df["保有株数"] = pd.to_numeric(df["保有株数"].str.replace(",", ""), errors="coerce")
    return df.groupby(["銘柄コード", "銘柄名称"], as_index=False)["保有株数"].sum()

# --- メインロジック ---
st.sidebar.header("📁 CSVアップロード")
portfolio_file = st.sidebar.file_uploader("1. 保有証券一覧CSV", type="csv")
history_file = st.sidebar.file_uploader("2. 配当金実績CSV", type="csv")

if portfolio_file:
    df_p = load_portfolio_csv(portfolio_file.read())
    current_month = datetime.now().month
    
    actual_data_list, paid_codes_now = [], set()
    if history_file:
        actual_data_list, paid_codes_now = load_dividend_history(history_file.read())

    if st.sidebar.button("配当計算・更新を実行"):
        with st.spinner("要件に基づき計算中..."):
            final_list = actual_data_list.copy() # 要件1: 実績をそのまま計上
            ticker_yields = []
            progress = st.progress(0)
            
            for i, row in df_p.iterrows():
                code = row['銘柄コード']
                try:
                    tk = yf.Ticker(f"{code}.T")
                    div_rate = tk.info.get("trailingAnnualDividendRate") or tk.info.get("dividendRate") or 0
                    ticker_yields.append(div_rate)
                    
                    # 配当実績から権利月を取得
                    hist = tk.dividends
                    if not hist.empty:
                        # 権利月の3ヶ月後を入金月とする
                        div_months = sorted(list(set([(m + 3 - 1) % 12 + 1 for m in hist.index.month])))
                    else:
                        div_months = [6, 12] # 不明な場合は3,9月権利想定
                    
                    for pay_month in div_months:
                        # 要件2 & 3 の判定
                        # 未来の月、もしくは「今月かつ実績にまだない銘柄」のみ予測を計上
                        is_future = pay_month > current_month
                        is_current_unpaid = (pay_month == current_month and code not in paid_codes_now)
                        
                        if is_future or is_current_unpaid:
                            pred_val = (div_rate / len(div_months) * row['保有株数'])
                            if pred_val > 0:
                                final_list.append({
                                    "月": pay_month,
                                    "銘柄名": row['銘柄名称'],
                                    "金額": pred_val,
                                    "コード": code,
                                    "区分": "予測(未入金)"
                                })
                except: ticker_yields.append(0)
                progress.progress((i + 1) / len(df_p))

            # グラフ用データ作成
            df_all = pd.DataFrame(final_list)
            # 1月〜12月を確実に表示するためのダミーデータ
            dummy = pd.DataFrame([{"月": m, "金額": 0, "区分": "予測(未入金)"} for m in range(1, 13)])
            df_display = pd.concat([df_all, dummy], ignore_index=True)
            
            st.session_state['df_all'] = df_display
            st.session_state['df_summary'] = df_display.groupby(['月', '区分'])['金額'].sum().reset_index()
            st.rerun()

    if 'df_summary' in st.session_state:
        df_sum = st.session_state['df_summary']
        df_sum['月表示'] = df_sum['月'].astype(str) + "月"
        
        # 指標表示
        act_total = df_sum[df_sum['区分'] == '実績(確定)']['金額'].sum()
        pre_total = df_sum[df_sum['区分'] == '予測(未入金)']['金額'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("今年の実績(受渡ベース)", f"{act_total:,.0f} 円")
        c2.metric("今後の予測(未入金分)", f"{pre_total:,.0f} 円")
        c3.metric("年間着地見込み", f"{(act_total + pre_total):,.0f} 円")

        # グラフ
        fig = px.bar(df_sum, x="月表示", y="金額", color="区分",
                     category_orders={"月表示": [f"{m}月" for m in range(1, 13)]},
                     color_discrete_map={"実績(確定)": "#1f77b4", "予測(未入金)": "#00CC96"},
                     text_auto=".0f", barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

        # 内訳
        st.subheader("🔍 月別の詳細内訳")
        target_m = st.selectbox("確認したい月", [f"{m}月" for m in range(1, 13)], index=current_month-1)
        m_int = int(target_m.replace("月", ""))
        detail = st.session_state['df_all']
        month_detail = detail[(detail['月'] == m_int) & (detail['金額'] > 0)].sort_values("区分")
        st.dataframe(month_detail[["区分", "コード", "銘柄名", "金額"]].style.format({"金額": "{:,.0f}"}), use_container_width=True, hide_index=True)

else:
    st.info("サイドバーからCSVファイルを2つアップロードしてください。")