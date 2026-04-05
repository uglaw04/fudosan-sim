import streamlit as st
import json
import gspread
import re
import pandas as pd
from google.oauth2.service_account import Credentials

# ==========================================
# 🔐 セキュリティ
# ==========================================
st.set_page_config(page_title="ユウジロウ専用：最強シミュレーター", layout="wide")
password = st.sidebar.text_input("パスワード", type="password")
if password != st.secrets["app_password"]:
    st.stop()

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1R0LcnpJUkvN0TbYy3QN3_P0VyxgaMF8K1201hONkvoc/edit#gid=0"

# --- 🌟 セッション状態の初期化 ---
if 'price' not in st.session_state: st.session_state.price = 0.0
if 'yield_val' not in st.session_state: st.session_state.yield_val = 0.0

# ==========================================
# 🏢 解析セクション
# ==========================================
st.title("🏢 ユウジロウ専用：楽待完全対応・トータル収支シミュレーター")

with st.expander("📝 楽待からテキスト解析", expanded=True):
    raw_text = st.text_area("物件詳細テキストを貼り付け")
    if st.button("解析実行"):
        p_m = re.search(r'販売価格([0-9億万]+)円', raw_text)
        if p_m:
            s = p_m.group(1)
            o = int(re.search(r'(\d+)億', s).group(1)) if '億' in s else 0
            m = int(re.search(r'(\d+)万', s).group(1)) if '万' in s else 0
            st.session_state.price = float((o * 10000) + m)
        y_m = re.search(r'表面利回り([0-9.]+)%', raw_text)
        if y_m: st.session_state.yield_val = float(y_m.group(1))
        st.rerun()

# ==========================================
# ⚙️ 条件入力
# ==========================================
st.subheader("⚙️ 条件設定")
c1, c2, c3 = st.columns(3)
with c1:
    f_price = st.number_input("価格（万円）", value=st.session_state.price)
    f_yield = st.number_input("表面利回り（％）", value=st.session_state.yield_val)
with c2:
    f_rate = st.number_input("金利（％）", value=2.0)
    f_years = st.number_input("融資期間（年）", value=30)
with c3:
    f_rent_drop = st.slider("家賃下落（年％）", 0.0, 2.0, 1.0)
    f_exit_cap = st.number_input("売却時の想定利回り（％）", value=f_yield + 1.0)

# ==========================================
# 📊 累計収支の精密計算
# ==========================================
years = list(range(1, 51))
annual_cfs = []
cumulative_cfs = [] # 楽待流：積み上げCF
net_assets = []     # 楽待流：売却した時の手残り

total_cf = 0
for y in years:
    # 収入 - 経費 (簡易版)
    rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop/100) ** (y-1))
    noi = rent * 0.8
    # 返済
    m_rate = (f_rate / 100) / 12
    m_len = f_years * 12
    if y <= f_years:
        if m_rate > 0:
            ads = ((f_price * m_rate * ((1+m_rate)**m_len)) / (((1+m_rate)**m_len)-1)) * 12
        else: ads = f_price / f_years
        loan_balance = f_price * (1 - y/f_years) # 簡易残債
    else:
        ads = 0
        loan_balance = 0
    
    cf = noi - ads
    total_cf += cf
    annual_cfs.append(cf)
    cumulative_cfs.append(total_cf)
    
    # 売却想定価格 (その年の収入 / 出口利回り)
    exit_price = rent / (f_exit_cap / 100)
    # 売却した時の手残り (売却価格 - 残債)
    net_asset = exit_price - loan_balance
    net_assets.append(net_asset)

df_plot = pd.DataFrame({
    "年数": years,
    "単年CF": annual_cfs,
    "累計貯金額": cumulative_cfs,
    "売却した時の手残り": net_assets
})

# ==========================================
# 📈 グラフ表示
# ==========================================
st.divider()
st.subheader("🏁 トータル収支予測グラフ")
st.info("「累計貯金額（青）」と「売却した時の手残り（赤）」の合計が、あなたの真の利益です。")

# 2つの軸で表示
st.line_chart(df_plot.set_index("年数"))

st.subheader("💡 投資判断のポイント")
col_a, col_b = st.columns(2)
with col_a:
    st.write("**① 累計黒字化（回収期間）**")
    # 累計CFがプラスになる年を探す
    recovery_year = next((y for y, c in zip(years, cumulative_cfs) if c > 0), None)
    if recovery_year:
        st.success(f"投資元本は **{recovery_year}年目** に回収完了予定です。")
    else:
        st.error("50年以内には投資元本を回収できません。")

with col_b:
    st.write("**② 出口（売却）のタイミング**")
    st.warning(f"5年以降に売却すると、税率が半分（20％）に下がります。")
    st.write(f"10年目に売った場合の手残り: **約{net_assets[9]:,.0f}万円**")
