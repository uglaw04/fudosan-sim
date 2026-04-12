import streamlit as st
import json
import gspread
import re
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from google.oauth2.service_account import Credentials

# ==========================================
# 🔐 セキュリティ・ページ設定
# ==========================================
st.set_page_config(page_title="ユウジロウ専用：最強シミュレーター", layout="wide")

st.sidebar.title("🔐 セキュリティ")
password = st.sidebar.text_input("パスワードを入力", type="password")
if password != st.secrets["app_password"]:
    st.warning("左側のメニューからパスワードを入れてください。")
    st.stop()

# スプシ設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1R0LcnpJUkvN0TbYy3QN3_P0VyxgaMF8K1201hONkvoc/edit#gid=0"

try:
    key_dict = json.loads(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(key_dict, scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive'])
    sheet = gspread.authorize(creds).open_by_url(SPREADSHEET_URL).sheet1
except:
    st.error("スプシ連携エラー：設定を確認してください。")
    st.stop()

# セッション状態の初期化
if 'price' not in st.session_state: st.session_state.price = 10000.0 # 初期値1億円
if 'yield_val' not in st.session_state: st.session_state.yield_val = 7.0
if 'prop_name' not in st.session_state: st.session_state.prop_name = ""

# ==========================================
# 🏢 メイン：解析セクション
# ==========================================
st.title("🏢 ユウジロウ専用：CFO仕様プロ・シミュレーター")

with st.expander("📝 STEP1：楽待テキストを貼り付けて自動セット", expanded=True):
    raw_text = st.text_area("物件詳細のテキストを貼り付け", height=100)
    if st.button("精密解析を実行"):
        p_m = re.search(r'販売価格([0-9億万]+)円', raw_text)
        if p_m:
            s = p_m.group(1)
            o = int(re.search(r'(\d+)億', s).group(1)) if '億' in s else 0
            m = int(re.search(r'(\d+)万', s).group(1)) if '万' in s else 0
            st.session_state.price = float((o * 10000) + m)
        y_m = re.search(r'表面利回り([0-9.]+)%', raw_text)
        if y_m: st.session_state.yield_val = float(y_m.group(1))
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        if len(lines) > 2: st.session_state.prop_name = lines[2]
        st.success("解析完了！内容を確認・修正してください。")
        st.rerun()

st.divider()

# ==========================================
# ⚙️ STEP2：手修正・条件入力フォーム
# ==========================================
st.subheader("⚙️ STEP2：詳細・ストレス設定")
c1, c2, c3, c4 = st.columns(4)

with c1:
    f_name = st.text_input("物件名", value=st.session_state.prop_name)
    f_price = st.number_input("価格（万円）", value=st.session_state.price, step=100.0)
    f_yield = st.number_input("表面利回り（％）", value=st.session_state.yield_val, step=0.1)

with c2:
    f_down_payment = st.number_input("自己資金・頭金（万円）", value=1000.0, step=100.0)
    f_rate = st.number_input("融資金利（％）", value=1.5, step=0.1)
    f_years = st.number_input("融資期間（年）", value=30, step=1)

with c3:
    f_exp_rate = st.slider("基本経費率（％）", 10, 50, 20)
    f_rent_drop = st.slider("家賃下落率（年/％）", 0.0, 3.0, 1.0)
    st.caption("※経費率20%は固定的費用（管理・固定資産税等）")

with c4:
    f_exit_cap = st.number_input("出口想定利回り（％）", value=st.session_state.yield_val + 1.0, step=0.1)
    # 玉川理論ボタン（3.5年で退去、4.4ヶ月空室・原状回復費ロス = 年率約10.47%の損失）
    use_tamagawa = st.toggle("🚨 玉川式ストレス適用 (退去・修繕コスト年率10.5%減)", value=True)

# ==========================================
# 📊 計算ロジック（50年分）
# ==========================================
years = list(range(1, 51))
annual_cf_list = []
cumulative_cf_list = []
exit_hand_list = []
dcr_list = []

total_accumulated_cf = 0
loan_amount = f_price - f_down_payment

# 金融電卓ロジック（元利均等）
m_rate = (f_rate / 100) / 12
m_len = f_years * 12
if m_rate > 0:
    ads = ((loan_amount * m_rate * ((1 + m_rate)**m_len)) / (((1+m_rate)**m_len) - 1)) * 12
else:
    ads = (loan_amount / f_years) if f_years > 0 else 0

for y in years:
    # 家賃下落を反映したその年の家賃
    current_rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop/100) ** (y-1))
    
    # 経費と玉川ストレスの控除
    noi = current_rent * (1 - f_exp_rate/100)
    if use_tamagawa:
        noi -= current_rent * 0.1047 # ファミリー層の退去確率から算出した年平均ロス
    
    # 残債と返済額の計算（正確なアモチゼーション）
    if y <= f_years:
        rem_months = (f_years - y) * 12
        if m_rate > 0:
            loan_balance = (ads / 12) * ((1 - (1 + m_rate)**(-rem_months)) / m_rate)
        else:
            loan_balance = loan_amount * (rem_months / m_len)
        current_ads = ads
    else:
        loan_balance = 0
        current_ads = 0
        
    cf = noi - current_ads
    dcr = (noi / current_ads) if current_ads > 0 else 99.99
    
    total_accumulated_cf += cf
    
    annual_cf_list.append(cf)
    cumulative_cf_list.append(total_accumulated_cf)
    dcr_list.append(dcr)
    
    # 出口計算（売却額 - 残債 + 累積CF）- 便宜上、当初頭金を引いて実質手残りを算出
    exit_price = current_rent / (f_exit_cap / 100)
    hand_over = exit_price - loan_balance + total_accumulated_cf - f_down_payment
    exit_hand_list.append(hand_over)

# ==========================================
# 💡 投資判断アドバイス（最上部へ移動）
# ==========================================
st.subheader("💡 CFO判定：財務健全性スコア")
col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    first_cf = annual_cf_list[0]
    if first_cf >= 0:
        st.success(f"**単年収支 (1年目)**\n\n+ {first_cf:,.0f} 万円")
    else:
        st.error(f"**単年収支 (1年目)**\n\n▲ {abs(first_cf):,.0f} 万円")

with col_b:
    first_dcr = dcr_list[0]
    if first_dcr >= 1.2:
        st.success(f"**DCR (1年目)**\n\n{first_dcr:.2f} (安全圏)")
    elif 1.0 <= first_dcr < 1.2:
        st.warning(f"**DCR (1年目)**\n\n{first_dcr:.2f} (警戒圏)")
    else:
        st.error(f"**DCR (1年目)**\n\n{first_dcr:.2f} (破綻リスク)")

with col_c:
    recovery_year = next((y for y, c in zip(years, cumulative_cf_list) if c > f_down_payment), None)
    if recovery_year:
        st.info(f"**頭金回収期間**\n\n約 {recovery_year} 年")
    else:
        st.error("**頭金回収期間**\n\n50年以内不可")

with col_d:
    max_exit_year = exit_hand_list.index(max(exit_hand_list)) + 1
    st.info(f"**売却利益のピーク**\n\n築 +{max_exit_year} 年時点")

# ==========================================
# 📈 楽待風：2軸ハイブリッドグラフ
# ==========================================
st.divider()

bar_colors = ['lightblue' if cf >= 0 else 'lightpink' for cf in annual_cf_list]

fig = make_subplots(specs=[[{"secondary_y": True}]])

# 単年CF
fig.add_trace(
    go.Bar(x=years, y=annual_cf_list, name="単年度キャッシュフロー", marker_color=bar_colors, opacity=0.8),
    secondary_y=False,
)

# 累計CF
fig.add_trace(
    go.Scatter(x=years, y=cumulative_cf_list, name="累計キャッシュフロー（現金の蓄積）", line=dict(color='blue', width=3)),
    secondary_y=True,
)

# 売却時手残り
fig.add_trace(
    go.Scatter(x=years, y=exit_hand_list, name="今売却した時の手残り総額（頭金控除後）", line=dict(color='orange', width=2, dash='dot')),
    secondary_y=True,
)

fig.update_layout(
    title_text=f"{f_name} の長期収支予測（法人税引き前）",
    xaxis_title="経過年数",
    legend=dict(x=0, y=1.2, orientation="h"),
    height=500,
    margin=dict(t=100)
)
fig.update_yaxes(title_text="単年収支 (万円)", secondary_y=False)
fig.update_yaxes(title_text="累計・資産総額 (万円)", secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

if st.button("この最終条件をスプシに保存する"):
    try:
        sheet.append_row([f_name, f_price, f_yield, annual_cf_list[0], first_dcr, exit_hand_list[9]])
        st.balloons()
        st.success("スプシに保存しました！")
    except:
        st.error("スプシ保存に失敗しました。")
