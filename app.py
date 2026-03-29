import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 1. スプレッドシート連携の設定 ---
# Streamlitの秘密の金庫(Secrets)から合鍵を読み込む
key_dict = json.loads(st.secrets["gcp_service_account"])
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
client = gspread.authorize(creds)

# ★ここにフェーズ1で作ったスプレッドシートのURLを入れます★
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1R0LcnpJUkvN0TbYy3QN3_P0VyxgaMF8K1201hONkvoc/edit?gid=0#gid=0"
sheet = client.open_by_url(SPREADSHEET_URL).sheet1

# --- 2. 計算関数 ---
def calc_ads(principal, annual_rate, years):
    if principal <= 0 or years <= 0: return 0
    r = annual_rate / 100 / 12
    n = years * 12
    if r == 0: return principal / years
    m = (principal * 10000 * r) / (1 - (1 + r) ** -n)
    return (m * 12) / 10000

# --- 3. 画面UIとロジック ---
st.set_page_config(page_title="不動産投資シミュレーター Pro+", layout="wide")
st.title("不動産投資シミュレーター Pro+ (クラウド保存版)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("物件・融資スペック")
    price = st.number_input("価格 (万円)", value=20000, step=1000)
    rent = st.number_input("家賃 (万円)", value=1200, step=100)
    struct_options = {"RC (耐用47年)": 47, "重量鉄骨 (耐用34年)": 34, "木造 (耐用22年)": 22}
    structure = struct_options[st.selectbox("構造", list(struct_options.keys()))]
    age = st.number_input("築年数 (年)", value=20, step=1)
    
    down_payment = st.number_input("頭金 (万円)", value=4000, step=500)
    opex_rate = st.number_input("経費率 (%)", value=25.0, step=1.0)
    stress_rate = st.number_input("ストレス金利 (%)", value=3.5, step=0.1)
    real_rate = st.number_input("実行金利 (%)", value=1.5, step=0.1)

term = max(10, structure - age)
loan = price - down_payment
noi = rent * (1 - opex_rate / 100)
stress_ads = calc_ads(loan, stress_rate, term)
real_ads = calc_ads(loan, real_rate, term)
dcr = (noi / stress_ads) if stress_ads > 0 else 0
cf = noi - real_ads

with col2:
    st.subheader("判定結果")
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("借入総額", f"{int(loan):,} 万円", f"期間: {term}年")
    mcol2.metric("審査用 DCR", f"{dcr:.2f}")
    mcol3.metric("リアル手残り (CF)", f"{int(cf):,} 万円/年")

    st.markdown("---")
    st.subheader("データ記録 (スプレッドシートへ保存)")
    memo = st.text_input("物件メモ（駅徒歩、特徴など）")
    
    if st.button("この物件を記録する", type="primary"):
        # スプレッドシートの最終行にデータを追加
        row_data = [
            datetime.now().strftime("%Y/%m/%d %H:%M"),
            price,
            round((rent/price)*100, 2) if price > 0 else 0,
            round(dcr, 2),
            int(cf),
            memo
        ]
        sheet.append_row(row_data)
        st.success("スプレッドシートに保存しました！")

# スプレッドシートのデータを読み込んで画面に表示
st.markdown("---")
st.subheader("過去の比較ログ")
try:
    records = sheet.get_all_records()
    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True)
    else:
        st.info("まだ記録がありません。")
except Exception as e:
    st.error("データの読み込みに失敗しました。")
