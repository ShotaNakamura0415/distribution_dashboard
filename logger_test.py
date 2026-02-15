import logging
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_portfolio_data(df):
    logger.info("=== CSV読み込み完了 ===")
    logger.info(f"合計銘柄数: {len(df)}")

def log_dividend_process(symbol, div_rate, months, amount):
    month_str = ", ".join([f"{m}月" for m in months]) if months else "不明(3/9月仮置き)"
    logger.info(f"[{symbol:^8}] 単価:{div_rate:>7} | 月:{month_str:<10} | 年間:{amount:>8,.0f}円")

def log_final_summary(monthly_df, df_result):
    logger.info("=== 集計完了報告 ===")
    if "年間配当見込み" in df_result.columns:
        total_sum = df_result["年間配当見込み"].sum()
        logger.info(f"総年間配当見込み額: {total_sum:,.0f}円")
    
    logger.info("--- 月別配当分布 ---")
    for _, row in monthly_df.iterrows():
        if row['配当金'] > 0:
            logger.info(f"  {row['月']}: {row['配当金']:>10,.0f}円")