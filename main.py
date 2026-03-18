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

# 税率設定
TAX_RATE = 0.20315
NET_RATIO = 1 - TAX_RATE

# --- 1. 実績データの読み込み ---
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
    if header_idx == -1: 
        return [], set()

    header = lines[header_idx]
    data_rows = [row for row in lines[header_idx + 1:] if len(row) == len(header) and "/" in row[0]]
    df_hist = pd.DataFrame(data_rows, columns=header)
    df_hist["受渡日"] = pd.to_datetime(df_hist["受渡日"], errors='coerce')
    df_hist["受取額(税引後・円)"] = pd.to_numeric(df_hist["受取額(税引後・円)"].str.replace(",", ""), errors="coerce")
    df_hist["数量"] = pd.to_numeric(df_hist["数量"].str.replace(",", ""), errors="coerce")
    
    current_year = datetime.now().year
    df_current_year = df_hist[df_hist["受渡日"].dt.year == current_year].dropna(subset=["受取額(税引後・円)"])
    
    actual_list = []
    paid_codes_this_month = set()
    current_month = datetime.now().month

    for _, r in df_current_year.iterrows():
        code_match = re.search(r'(\d{4})', r["銘柄名"])
        code = code_match.group(1) if code_match else ""
        
        raw_acc = r["口座"]
        acc_label = "NISA" if "NISA" in raw_acc else "特定"
        
        after_tax = r["受取額(税引後・円)"]
        before_tax = after_tax / NET_RATIO if acc_label == "特定" else after_tax

        actual_list.append({
            "月": r["受渡日"].month,
            "コード": code,
            "銘柄名": f"[{acc_label}] {r['銘柄名']}",
            "数量": r["数量"],
            "税引前金額": before_tax,
            "入金額": after_tax,
            "区分": "実績(確定)",
            "口座": acc_label
        })
        if r["受渡日"].month == current_month:
            paid_codes_this_month.add(code)
            
    return actual_list, paid_codes_this_month

# --- 2. 保有資産データの読み取り ---
def load_portfolio_csv(file_content):
    text = file_content.decode("shift-jis")
    lines = text.splitlines()
    all_data = []
    current_account_type = "不明"
    
    for line in lines:
        if "株式（特定預り）" in line:
            current_account_type = "特定"
        elif "NISA" in line:
            current_account_type = "NISA"
        row = list(csv.reader([line]))[0]
        if len(row) > 0 and re.match(r'^\d{4}$', row[0].replace('"', '')):
            all_data.append({
                "銘柄コード": row[0].replace('"', ''),
                "銘柄名称": row[1].replace('"', ''),
                "保有株数": pd.to_numeric(row[2].replace(',', ''), errors='coerce'),
                "口座区分": current_account_type
            })
    df = pd.DataFrame(all_data)
    return df.groupby(["銘柄コード", "銘柄名称", "口座区分"], as_index=False)["保有株数"].sum()

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
        with st.spinner("数量を含めた詳細データを生成中..."):
            final_list = actual_data_list.copy()
            progress = st.progress(0)
            
            for i, row in df_p.iterrows():
                code = row['銘柄コード']
                acc_type = row['口座区分']
                count = row['保有株数']
                try:
                    tk = yf.Ticker(f"{code}.T")
                    div_rate = tk.info.get("trailingAnnualDividendRate") or tk.info.get("dividendRate") or 0
                    hist = tk.dividends
                    div_months = sorted(list(set([(m + 3 - 1) % 12 + 1 for m in hist.index.month]))) if not hist.empty else [6, 12]
                    
                    for pay_month in div_months:
                        if pay_month > current_month or (pay_month == current_month and code not in paid_codes_now):
                            before = (div_rate / len(div_months) * count)
                            ratio = NET_RATIO if acc_type == "特定" else 1.0
                            after = before * ratio
                            
                            if before > 0:
                                final_list.append({
                                    "月": pay_month,
                                    "コード": code,
                                    "銘柄名": f"[{acc_type}] {row['銘柄名称']}",
                                    "数量": count,
                                    "税引前金額": before,
                                    "入金額": after,
                                    "区分": "予測(未入金)",
                                    "口座": acc_type
                                })
                except Exception as e: 
                    print(f"【取得失敗】コード {code} のデータが yfinance から取得できませんでした。({e})")
                    pass
                progress.progress((i + 1) / len(df_p))

            df_all = pd.DataFrame(final_list)
            dummy = pd.DataFrame([{"月": m, "数量": 0, "税引前金額": 0, "入金額": 0, "区分": "予測(未入金)"} for m in range(1, 13)])
            st.session_state['df_all'] = pd.concat([df_all, dummy], ignore_index=True)
            st.session_state['df_summary'] = st.session_state['df_all'].groupby(['月', '区分'])['入金額'].sum().reset_index()
            st.rerun()

    if 'df_summary' in st.session_state:
        df_sum = st.session_state['df_summary']
        df_sum['月表示'] = df_sum['月'].astype(str) + "月"
        detail = st.session_state['df_all']
        
        # 指標
        act_t = detail[detail['区分'] == '実績(確定)']['入金額'].sum()
        pre_t = detail[detail['区分'] == '予測(未入金)']['入金額'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("今年の実績 (入金済み)", f"{act_t:,.0f} 円")
        c2.metric("今後の予測 (手取り)", f"{pre_t:,.0f} 円")
        c3.metric("合計着地予想", f"{(act_t + pre_t):,.0f} 円")

        # グラフ
        fig = px.bar(df_sum, x="月表示", y="入金額", color="区分",
                     category_orders={"月表示": [f"{m}月" for m in range(1, 13)]},
                     color_discrete_map={"実績(確定)": "#1f77b4", "予測(未入金)": "#00CC96"},
                     text_auto=".0f", barmode="stack")
        st.plotly_chart(fig, width='stretch')

        # --- 詳細テーブル ---
        st.subheader("🔍 月別の詳細内訳")
        target_m = st.selectbox("表示月を選択", [f"{m}月" for m in range(1, 13)], index=current_month-1)
        m_int = int(target_m.replace("月", ""))
        
        month_detail = detail[(detail['月'] == m_int) & ((detail['入金額'] > 0) | (detail['税引前金額'] > 0))].copy()
        month_detail = month_detail.sort_values(["区分", "入金額"], ascending=[False, False])
        
        if not month_detail.empty:
            # 数量列を追加した並び順
            disp_df = month_detail[["区分", "口座", "コード", "銘柄名", "数量", "税引前金額", "入金額"]]
            st.dataframe(
                disp_df.style.format({
                    "数量": "{:,.0f}",
                    "税引前金額": "{:,.0f}", 
                    "入金額": "{:,.0f}"
                }),
                width='stretch', hide_index=True
            )
        else:
            st.info(f"{target_m} のデータはありません。")
else:
    st.info("CSVファイルをアップロードしてください。")