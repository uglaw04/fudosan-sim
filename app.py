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

# サイドバー：パスワードロック
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
if 'price' not in st.session_state: st.session_state.price = 0.0
if 'yield_val' not in st.session_state: st.session_state.yield_val = 0.0
if 'prop_name' not in st.session_state: st.session_state.prop_name = ""

# ==========================================
# 🏢 メイン：解析セクション
# ==========================================
st.title("🏢 ユウジロウ専用：トータル収支可視化シミュレーター")

with st.expander("📝 STEP1：楽待テキストを貼り付けて自動セット", expanded=True):
    raw_text = st.text_area("物件詳細のテキストを貼り付け", height=150)
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
st.subheader("⚙️ STEP2：詳細条件設定")
c1, c2, c3, c4 = st.columns(4)

with c1:
    f_name = st.text_input("物件名", value=st.session_state.prop_name)
    f_price = st.number_input("価格（万円）", value=st.session_state.price, step=100.0)
    f_yield = st.number_input("表面利回り（％）", value=st.session_state.yield_val, step=0.1)

with c2:
    f_rate = st.number_input("融資金利（％）", value=2.0, step=0.1)
    f_years = st.number_input("融資期間（年）", value=30, step=1)
    f_exp_rate = st.slider("経費率（％）", 10, 50, 20)

with c3:
    f_rent_drop = st.slider("家賃下落率（年/％）", 0.0, 3.0, 1.0)
    f_tax_rate = st.selectbox("所得税率（住民税込％）", [20, 30, 40, 50], index=1)

with c4:
    f_exit_cap = st.number_input("出口想定利回り（％）", value=st.session_state.yield_val + 1.0, step=0.1)
    st.caption("※古くなると売却利回りは上がります（＝価格は下がる）")

# ==========================================
# 📊 計算ロジック（50年分）
# ==========================================
years = list(range(1, 51))
annual_cf_list = []
cumulative_cf_list = []
exit_hand_list = [] # ○年目に売った時の手残り総額

total_accumulated_cf = 0

for y in years:
    # 1. 収入計算（家賃下落考慮）
    current_rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop/100) ** (y-1))
    noi = current_rent * (1 - f_exp_rate/100)
    
    # 2. 返済計算
    m_rate = (f_rate / 100) / 12
    m_len = f_years * 12
    if y <= f_years:
        ads = ((f_price * m_rate * ((1 + m_rate)**m_len)) / (((1+m_rate)**m_len) - 1)) * 12
        loan_balance = f_price * (1 - (y / f_years)) # 簡易的な元金減少
    else:
        ads = 0
        loan_balance = 0
        
    # 3. 単年CF計算
    cf = noi - ads
    total_accumulated_cf += cf
    
    annual_cf_list.append(cf)
    cumulative_cf_list.append(total_accumulated_cf)
    
    # 4. 出口想定（その年に売却したと仮定）
    exit_price = current_rent / (f_exit_cap / 100)
    hand_over = exit_price - loan_balance + total_accumulated_cf
    exit_hand_list.append(hand_over)

# ==========================================
# 📈 楽待風：2軸ハイブリッドグラフ（Plotly）
# ==========================================
st.divider()
st.subheader("📊 50年間のトータル収支シミュレーション")

# グラフ作成
fig = make_subplots(specs=[[{"secondary_y": True}]])

# 棒グラフ：単年CF（左軸）
fig.add_trace(
    go.Bar(x=years, y=annual_cf_list, name="単年度キャッシュフロー", marker_color='lightblue', opacity=0.7),
    secondary_y=False,
)

# 折れ線グラフ：累計CF（右軸）
fig.add_trace(
    go.Scatter(x=years, y=cumulative_cf_list, name="累計キャッシュフロー（貯金額）", line=dict(color='blue', width=3)),
    secondary_y=True,
)

# 折れ線グラフ：売却時手残り（右軸）
fig.add_trace(
    go.Scatter(x=years, y=exit_hand_list, name="今売却した時の手残り総額", line=dict(color='orange', width=2, dash='dot')),
    secondary_y=True,
)

# レイアウト調整
fig.update_layout(
    title_text=f"{f_name} の長期収支予測",
    xaxis_title="経過年数",
    legend=dict(x=0, y=1.2, orientation="h"),
    height=500
)

fig.update_yaxes(title_text="単年収支 (万円)", secondary_y=False)
fig.update_yaxes(title_text="累計・資産総額 (万円)", secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 💡 投資診断アドバイス
# ==========================================
st.subheader("💡 ユウジロウさんのための投資判断データ")
col_a, col_b, col_c = st.columns(3)

with col_a:
    st.write("**💰 単年度の健康状態**")
    if annual_cf_list[0] >= 0:
        st.success(f"1年目から黒字です！ (+{annual_cf_list[0]:,.0f}万円/年)")
    else:
        st.error(f"1年目は赤字です (▲{abs(annual_cf_list[0]):,.0f}万円/年)")
    st.caption("※経費・返済後の手残り額")

with col_b:
    st.write("**🏁 累計CFのプラス転換**")
    recovery_year = next((y for y, c in zip(years, cumulative_cf_list) if c > 0), None)
    if recovery_year:
        st.info(f"**{recovery_year}年目** に累計CFが黒字化します。")
    else:
        st.warning("50年以内に累計CFは黒字化しません。")

with col_c:
    st.write("**🏠 出口戦略の目安**")
    max_exit_year = exit_hand_list.index(max(exit_hand_list)) + 1
    st.warning(f"**{max_exit_year}年目** の売却がトータル利益最大です。")
    st.caption(f"10年目の売却手残り: {exit_hand_list[9]:,.0f}万円")

if st.button("この精密解析結果をスプシに保存する"):
    sheet.append_row([f_name, f_price, f_yield, annual_cf_list[0], recovery_year, exit_hand_list[9]])
    st.balloons()
