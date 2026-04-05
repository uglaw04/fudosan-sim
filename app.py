import streamlit as st
import json
import gspread
import re
import pandas as pd
from google.oauth2.service_account import Credentials
import datetime

# ==========================================
# 🔐 設定・セキュリティ
# ==========================================
st.set_page_config(page_title="ユウジロウ専用プロ・シミュレーター", layout="wide")

st.sidebar.title("🔐 セキュリティ")
password = st.sidebar.text_input("パスワードを入力", type="password")
if password != st.secrets["app_password"]:
    st.warning("左側のメニューからパスワードを入れてください。")
    st.stop()

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1R0LcnpJUkvN0TbYy3QN3_P0VyxgaMF8K1201hONkvoc/edit#gid=0"

try:
    key_dict = json.loads(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(key_dict, scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive'])
    sheet = gspread.authorize(creds).open_by_url(SPREADSHEET_URL).sheet1
except:
    st.error("スプシ連携エラー：設定を確認してください。")
    st.stop()

# セッション状態
if 'prop_name' not in st.session_state: st.session_state.prop_name = ""
if 'price' not in st.session_state: st.session_state.price = 0.0
if 'yield_val' not in st.session_state: st.session_state.yield_val = 0.0
if 'built_year' not in st.session_state: st.session_state.built_year = 2000

# ==========================================
# 🏢 メイン：解析セクション
# ==========================================
st.title("🏢 ユウジロウ専用：プロ・不動産シミュレーター")

with st.expander("📝 STEP1：楽待テキストを解析して精密セット", expanded=True):
    raw_text = st.text_area("物件詳細テキストを貼り付け")
    if st.button("精密解析実行"):
        # 価格
        p_m = re.search(r'販売価格([0-9億万]+)円', raw_text)
        if p_m:
            s = p_m.group(1)
            o = int(re.search(r'(\d+)億', s).group(1)) if '億' in s else 0
            m = int(re.search(r'(\d+)万', s).group(1)) if '万' in s else 0
            st.session_state.price = float((o * 10000) + m)
        # 利回り
        y_m = re.search(r'表面利回り([0-9.]+)%', raw_text)
        if y_m: st.session_state.yield_val = float(y_m.group(1))
        # 築年
        b_m = re.search(r'築年数(\d+)年', raw_text)
        if b_m: st.session_state.built_year = int(b_m.group(1))
        # 物件名
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        if len(lines) > 2: st.session_state.prop_name = lines[2]
        st.rerun()

st.divider()

# ==========================================
# ⚙️ STEP2：詳細条件・税金・出口設定
# ==========================================
st.subheader("⚙️ STEP2：プロ設定（手修正）")
c1, c2, c3, c4 = st.columns(4)

with c1:
    f_name = st.text_input("物件名", value=st.session_state.prop_name)
    f_price = st.number_input("価格（万円）", value=st.session_state.price, step=100.0)
    f_yield = st.number_input("利回り（％）", value=st.session_state.yield_val, step=0.1)

with c2:
    f_rate = st.number_input("金利（％）", value=2.0, step=0.1)
    f_years = st.number_input("融資期間（年）", value=30, step=1)
    f_built = st.number_input("築年数（年）", value=st.session_state.built_year, step=1)

with c3:
    st.write("**🏚️ 経年リスク設定**")
    f_rent_drop = st.slider("家賃下落率（年/％）", 0.0, 3.0, 1.0)
    f_exp_rate = st.slider("経費率（％）", 10, 50, 20)

with c4:
    st.write("**💰 税金・出口設定**")
    f_tax_rate = st.selectbox("所得税率（住民税込）", [20, 30, 40, 50], index=1)
    f_exit_cap = st.number_input("出口利回り（％）", value=f_yield + 1.0, step=0.1)

# ==========================================
# 📊 精密計算ロジック
# ==========================================
# 簡易的な減価償却の計算（RC造：法定47年）
remaining_life = max(1, 47 - f_built)
depreciation_rate = 1 / remaining_life if remaining_life > 0 else 0
building_value = f_price * 0.7 # 建物比率7割と仮定

years = []
cfs_pre_tax = []
cfs_post_tax = []

for y in range(1, int(f_years + 20) + 1):
    years.append(y)
    # 1. 家賃下落を考慮
    current_rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop/100) ** (y-1))
    noi = current_rent * (1 - f_exp_rate/100)
    
    # 2. ローン計算（元利均等）
    m_rate = (f_rate / 100) / 12
    m_len = f_years * 12
    if y <= f_years:
        if m_rate > 0:
            m_pay = (f_price * m_rate * ((1 + m_rate)**m_len)) / (((1+m_rate)**m_len) - 1)
        else:
            m_pay = f_price / m_len
        ads = m_pay * 12
        # 利息（残債から概算）
        interest = (f_price * (1 - (y-1)/f_years)) * (f_rate/100)
    else:
        ads = 0
        interest = 0
    
    # 3. キャッシュフロー（税前）
    pre_tax_cf = noi - ads
    cfs_pre_tax.append(pre_tax_cf)
    
    # 4. 税金計算（NOI - 利息 - 減価償却）
    current_dep = building_value * depreciation_rate if y <= remaining_life else 0
    taxable_income = noi - interest - current_dep
    tax = max(0, taxable_income * (f_tax_rate / 100))
    
    # 5. キャッシュフロー（税後）
    cfs_post_tax.append(pre_tax_cf - tax)

df_long = pd.DataFrame({
    "年数": years,
    "税前CF": cfs_pre_tax,
    "税後CF": cfs_post_tax
})

# 出口価格の計算
exit_rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop/100) ** (f_years-1))
exit_price = exit_rent / (f_exit_cap / 100)

# ==========================================
# 📋 グラフと解説
# ==========================================
st.divider()
st.subheader("📊 長期収支シミュレーション（税金・下落考慮）")
st.line_chart(df_long.set_index("年数"))

col_exp, col_exit = st.columns(2)
with col_exp:
    st.info("""
    **💡 税金の話と「デッドクロス」**
    - **税後CF（薄い青）**がガクッと下がる時期に注目してください。
    - 建物が古くなり「減価償却」が終わると、経費が減るため**税金が跳ね上がります**。
    - 手元の現金（CF）より払う税金が多くなるこの現象を**デッドクロス**と呼びます。
    """)

with col_exit:
    st.warning(f"""
    **🏠 出口（売却）の予測**
    - {f_years}年後に利回り **{f_exit_cap}%** で売れると仮定。
    - 推定売却価格: **{exit_price:,.0f}万円**
    - 購入価格との差: **{exit_price - f_price:,.0f}万円**
    """)

if st.button("この精密データをスプシに保存"):
    sheet.append_row([f_name, f_price, f_yield, f_tax_rate, cf_year1 if 'cf_year1' in locals() else cfs_post_tax[0], exit_price])
    st.balloons()
