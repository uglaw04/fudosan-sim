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
if 'price' not in st.session_state: st.session_state.price = 0.0
if 'yield_val' not in st.session_state: st.session_state.yield_val = 0.0
if 'prop_name' not in st.session_state: st.session_state.prop_name = ""
if 'prop_address' not in st.session_state: st.session_state.prop_address = ""

# ==========================================
# 📐 ユーティリティ関数
# ==========================================

def calc_monthly_payment(principal, annual_rate_pct, years):
    """元利均等返済の月額返済額を計算"""
    if annual_rate_pct == 0:
        return principal / (years * 12) if years > 0 else 0
    r = (annual_rate_pct / 100) / 12
    n = years * 12
    return principal * r * (1 + r)**n / ((1 + r)**n - 1)

def calc_loan_balance(principal, annual_rate_pct, years_total, elapsed_years):
    """元利均等返済の残債を正確に計算（経過月数ベース）"""
    if elapsed_years >= years_total:
        return 0.0
    if annual_rate_pct == 0:
        return principal * (1 - elapsed_years / years_total)
    r = (annual_rate_pct / 100) / 12
    n_total = years_total * 12
    n_paid = elapsed_years * 12
    # 残債 = 元本 × [(1+r)^n_total - (1+r)^n_paid] / [(1+r)^n_total - 1]
    return principal * ((1 + r)**n_total - (1 + r)**n_paid) / ((1 + r)**n_total - 1)

# ==========================================
# 🏢 メイン：解析セクション
# ==========================================
st.title("🏢 ユウジロウ専用：トータル収支可視化シミュレーター")

with st.expander("📝 STEP1：楽待テキストを貼り付けて自動セット", expanded=True):
    raw_text = st.text_area("物件詳細のテキストを貼り付け", height=150)
    if st.button("精密解析を実行"):
        # 価格解析
        p_m = re.search(r'販売価格([0-9億万]+)円', raw_text)
        if p_m:
            s = p_m.group(1)
            o = int(re.search(r'(\d+)億', s).group(1)) if '億' in s else 0
            m = int(re.search(r'(\d+)万', s).group(1)) if '万' in s else 0
            st.session_state.price = float((o * 10000) + m)
        # 利回り解析
        y_m = re.search(r'表面利回り([0-9.]+)%', raw_text)
        if y_m: st.session_state.yield_val = float(y_m.group(1))

        # 住所・物件名解析
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        idx = -1
        for i, line in enumerate(lines):
            if "シミュレーション" in line:
                idx = i
                break
        if idx != -1 and len(lines) > idx + 2:
            st.session_state.prop_name = lines[idx + 1]
            st.session_state.prop_address = lines[idx + 2]

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
    f_address = st.text_input("物件住所", value=st.session_state.prop_address)
    f_price = st.number_input("価格（万円）", value=st.session_state.price, step=100.0)

with c2:
    f_yield = st.number_input("表面利回り（％）", value=st.session_state.yield_val, step=0.1)
    f_rate = st.number_input("融資金利（％）", value=2.0, step=0.1)
    f_years = st.number_input("融資期間（年）", value=30, step=1)

with c3:
    f_rent_drop = st.slider("家賃下落率（年/％）", 0.0, 3.0, 1.0)
    f_exp_rate = st.slider("経費率（管理費等/％）", 10, 50, 20)
    f_vacancy = st.slider("空室率（％）", 0.0, 30.0, 5.0,
                          help="想定空室による収入減。例：5%＝年間約18日分の空室")
    f_repair = st.number_input("修繕積立（万円/年）", value=0.0, step=5.0,
                               help="年間の修繕積立費。価格の0.5〜1%が目安")

with c4:
    f_tax_rate = st.selectbox("所得税率（住民税込／％）", [20, 30, 40, 50], index=1,
                              help="不動産所得に対する実効税率（源泉分離課税等は除く）")
    f_exit_cap = st.number_input("出口想定利回り（％）", value=st.session_state.yield_val + 1.0, step=0.1)
    st.caption("※古くなると売却利回りは上昇傾向")

# ==========================================
# 📊 計算ロジック（50年分）
# ==========================================
years = list(range(1, 51))

annual_cf_pretax_list = []   # 税引き前CF
annual_cf_aftertax_list = [] # 税引き後CF
cumulative_cf_list = []
exit_hand_list = []
total_accumulated_cf_aftertax = 0

monthly_payment = calc_monthly_payment(f_price, f_rate, int(f_years))
ads_annual = monthly_payment * 12  # 年間返済額（融資期間中）

for y in years:
    # ① 満室家賃（家賃下落考慮）
    full_rent = (f_price * (f_yield / 100)) * ((1 - f_rent_drop / 100) ** (y - 1))

    # ② 空室率考慮後の実効収入
    effective_rent = full_rent * (1 - f_vacancy / 100)

    # ③ NOI（経費控除後）
    noi = effective_rent * (1 - f_exp_rate / 100)

    # ④ 修繕積立を差し引き
    noi_after_repair = noi - f_repair

    # ⑤ 年間返済額（融資期間内のみ）
    if y <= f_years:
        ads = ads_annual
    else:
        ads = 0

    # ⑥ 税引き前CF
    cf_pretax = noi_after_repair - ads
    annual_cf_pretax_list.append(cf_pretax)

    # ⑦ 税引き後CF
    # 不動産所得への課税は、NOIから利息分（経費）と減価償却を差し引いた額に対して行うが、
    # ここでは簡易計算として「NOI - 利息分」に税率を適用する。
    # 利息分の概算（元利均等：初期は利息多、後半は元本返済多）
    if y <= f_years:
        loan_bal_prev = calc_loan_balance(f_price, f_rate, int(f_years), y - 1)
        interest_portion = loan_bal_prev * (f_rate / 100)  # 年間利息概算
    else:
        interest_portion = 0

    # 課税所得 = NOI - 利息（利息は経費算入可）
    taxable_income = noi_after_repair - interest_portion
    tax = taxable_income * (f_tax_rate / 100) if taxable_income > 0 else 0
    cf_aftertax = cf_pretax - tax
    annual_cf_aftertax_list.append(cf_aftertax)

    total_accumulated_cf_aftertax += cf_aftertax
    cumulative_cf_list.append(total_accumulated_cf_aftertax)

    # ⑧ 出口手残り（売却時）
    # 正確な残債で計算
    loan_balance = calc_loan_balance(f_price, f_rate, int(f_years), y)
    exit_price = effective_rent / (f_exit_cap / 100) if f_exit_cap > 0 else 0
    hand_over = exit_price - loan_balance + total_accumulated_cf_aftertax
    exit_hand_list.append(hand_over)

# ==========================================
# 📊 サマリー指標表示
# ==========================================
st.divider()
st.subheader("📋 主要指標サマリー")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("1年目税引き前CF（万円/年）", f"{annual_cf_pretax_list[0]:,.0f}")
with col2:
    st.metric("1年目税引き後CF（万円/年）", f"{annual_cf_aftertax_list[0]:,.0f}")
with col3:
    recovery_year = next((y for y, c in zip(years, cumulative_cf_list) if c > 0), "なし")
    st.metric("累計CF黒字転換（年目）", str(recovery_year))
with col4:
    st.metric("10年後売却手残り（万円）", f"{exit_hand_list[9]:,.0f}")

# ==========================================
# 📈 グラフ表示
# ==========================================
st.divider()
st.subheader("📊 50年間のトータル収支シミュレーション")

bar_colors = ['lightblue' if cf >= 0 else 'lightpink' for cf in annual_cf_aftertax_list]
fig = make_subplots(specs=[[{"secondary_y": True}]])

fig.add_trace(go.Bar(
    x=years, y=annual_cf_pretax_list,
    name="税引き前CF", marker_color='lightyellow', opacity=0.6
), secondary_y=False)

fig.add_trace(go.Bar(
    x=years, y=annual_cf_aftertax_list,
    name="税引き後CF（実態）", marker_color=bar_colors, opacity=0.9
), secondary_y=False)

fig.add_trace(go.Scatter(
    x=years, y=cumulative_cf_list,
    name="累計CF（税引き後）", line=dict(color='blue', width=3)
), secondary_y=True)

fig.add_trace(go.Scatter(
    x=years, y=exit_hand_list,
    name="今売却した時の手残り総額", line=dict(color='orange', width=2, dash='dot')
), secondary_y=True)

fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

fig.update_layout(
    title_text=f"{f_name} の予測チャート",
    xaxis_title="経過年数",
    legend=dict(x=0, y=1.2, orientation="h"),
    height=520,
    margin=dict(t=120),
    barmode='overlay'
)
fig.update_yaxes(title_text="単年収支 (万円)", secondary_y=False)
fig.update_yaxes(title_text="累計・資産総額 (万円)", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

# 残債推移も表示
st.subheader("🏦 ローン残債の推移")
loan_balances = [calc_loan_balance(f_price, f_rate, int(f_years), y) for y in years]
fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=years, y=loan_balances,
    name="ローン残債（正確計算）",
    fill='tozeroy', line=dict(color='red', width=2)
))
fig2.update_layout(
    xaxis_title="経過年数", yaxis_title="残債（万円）",
    height=300, margin=dict(t=30)
)
st.plotly_chart(fig2, use_container_width=True)

st.caption("※ 残債は元利均等返済の正確な計算式に基づきます（旧バージョンの直線近似より初期残債が大きくなります）")

# ==========================================
# 💾 保存ボタン
# ==========================================
if st.button("この最終条件をスプシに保存する"):
    try:
        sheet.append_row([
            f_name,
            f_address,
            f_price,
            f_yield,
            round(annual_cf_aftertax_list[0], 1),  # ★税引き後CFに変更
            recovery_year,
            round(exit_hand_list[9], 1)
        ])
        st.balloons()
        st.success(f"「{f_name}」のデータをスプシに保存しました！")
    except Exception as e:
        st.error(f"スプシ保存に失敗しました: {e}")
