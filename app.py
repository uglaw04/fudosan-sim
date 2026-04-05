import streamlit as st
import json
import gspread
import re
from google.oauth2.service_account import Credentials

# ==========================================
# 🚨 パスワードロック機能 🚨
# ==========================================
st.sidebar.title("🔐 セキュリティ")
# パスワード入力欄（サイドバーに配置）
password = st.sidebar.text_input("パスワードを入力", type="password")

if password != st.secrets["app_password"]:
    st.warning("左側のメニューから正しいパスワードを入力してください。")
    st.stop()  # パスワードが違う場合はここで処理を完全ストップ

# ==========================================
# 1. スプシ（スプレッドシート）連携の設定
# ==========================================
# ユウジロウさんのスプシURLをセット済みです
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1R0LcnpJUkvN0TbYy3QN3_P0VyxgaMF8K1201hONkvoc/edit#gid=0"

try:
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    key_dict = json.loads(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(credentials)
    # URLからシートを開く
    sheet = client.open_by_url(SPREADSHEET_URL).sheet1
except Exception as e:
    st.error(f"スプシの連携に失敗しました。設定を確認してください: {e}")
    st.stop()

# ==========================================
# 🌟 初期値の設定（session_state）
# ==========================================
if 'auto_name' not in st.session_state:
    st.session_state['auto_name'] = ""
if 'auto_price' not in st.session_state:
    st.session_state['auto_price'] = 0.0
if 'auto_yield' not in st.session_state:
    st.session_state['auto_yield'] = 0.0

# ==========================================
# 🤖 楽待コピペ全自動解析機能
# ==========================================
st.title("🏢 ユウジロウ専用 物件シミュレーター")

with st.expander("📝 楽待の物件情報をコピペして自動入力", expanded=True):
    st.write("楽待の「シミュレーション画面」などのテキストを以下に貼り付けてください。")
    raw_text = st.text_area("物件情報のテキスト", height=150)
    
    if st.button("テキストを解析して自動セット！"):
        if raw_text:
            # ① 価格の抽出 (例: "販売価格2億200万円")
            price_match = re.search(r'販売価格([0-9億万]+)円', raw_text)
            if price_match:
                price_str = price_match.group(1)
                oku = int(re.search(r'(\d+)億', price_str).group(1)) if '億' in price_str else 0
                man = int(re.search(r'(\d+)万', price_str).group(1)) if '万' in price_str else 0
                
                # 億・万がない場合（数字のみ）の考慮
                if oku == 0 and man == 0 and price_str.isdigit():
                   total_price = int(price_str) * 10000
                else:
                   total_price = (oku * 100000000) + (man * 10000)
                
                st.session_state['auto_price'] = total_price / 10000  # 万円単位
                st.success(f"✅ 価格を抽出: {st.session_state['auto_price']} 万円")

            # ② 利回りの抽出 (例: "表面利回り4.30%")
            yield_match = re.search(r'表面利回り([0-9.]+)%', raw_text)
            if yield_match:
                st.session_state['auto_yield'] = float(yield_match.group(1))
                st.success(f"✅ 利回りを抽出: {st.session_state['auto_yield']} %")

            # ③ 物件名の抽出 (最初の行などから)
            # 「カオス目黒」のような物件名を探す
            name_match = re.search(r'シミュレーション\n\n(.*?)\n', raw_text)
            if name_match:
                st.session_state['auto_name'] = name_match.group(1).strip()
                st.success(f"✅ 物件名を抽出: {st.session_state['auto_name']}")
            else:
                # 別のパターンでの物件名抽出試行
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                if len(lines) > 1:
                    st.session_state['auto_name'] = lines[1]
                    st.success(f"✅ おそらく物件名: {st.session_state['auto_name']}")
        else:
            st.warning("テキストが空っぽです。")

st.divider()

# ==========================================
# 📊 シミュレーション入力フォーム
# ==========================================
st.subheader("⚙️ 条件確認・微調整")

col1, col2 = st.columns(2)

with col1:
    property_name = st.text_input("物件名", value=st.session_state['auto_name'])
    price_man = st.number_input("物件価格（万円）", value=float(st.session_state['auto_price']), step=100.0)
    gross_yield = st.number_input("表面利回り（％）", value=float(st.session_state['auto_yield']), step=0.1)

with col2:
    loan_rate = st.number_input("融資金利（％）", value=2.0, step=0.1)
    loan_years = st.number_input("融資期間（年）", value=30, step=1)
    expenses_rate = st.number_input("運営経費率（％）", value=20.0, step=1.0)

# ==========================================
# 🚀 計算とスプシ保存
# ==========================================
if st.button("計算してスプシに保存する"):
    # 年間家賃収入
    annual_rent = price_man * (gross_yield / 100)
    # 年間経費
    annual_expenses = annual_rent * (expenses_rate / 100)
    # NOI
    noi = annual_rent - annual_expenses
    
    # ローン返済額（元利均等）
    monthly_rate = (loan_rate / 100) / 12
    months = loan_years * 12
    if monthly_rate > 0:
        monthly_payment = (price_man * monthly_rate * ((1 + monthly_rate) ** months)) / (((1 + monthly_rate) ** months) - 1)
        annual_payment = monthly_payment * 12
    else:
        annual_payment = price_man / loan_years

    # 手残りCF
    btcf = noi - annual_payment

    # 結果表示
    st.write("### 💰 計算結果")
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("年間家賃収入", f"{annual_rent:.1f} 万円")
    res_col2.metric("年間返済額", f"{annual_payment:.1f} 万円")
    res_col3.metric("手残りCF", f"{btcf:.1f} 万円/年")

    # スプシへ書き込み
    try:
        row_data = [
            property_name,
            price_man,
            gross_yield,
            loan_rate,
            loan_years,
            annual_rent,
            noi,
            annual_payment,
            btcf
        ]
        sheet.append_row(row_data)
        st.balloons() # 成功の風船！
        st.info("✅ スプシにデータを書き込みました！")
    except Exception as e:
        st.error(f"スプシ保存エラー: {e}")
