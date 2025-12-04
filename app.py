import streamlit as st
import pandas as pd
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# [중요] 분리된 DB 및 함수 임포트
from mapping_db import get_commission, is_target_unit, TARGET_UNITS

st.set_page_config(page_title="연세대학교 선거 현황", layout="wide")


# ==============================================================================
# [UI 디자인] CSS
# ==============================================================================
def apply_custom_css():
    st.markdown("""
    <style>
        html, body, [class*="css"] {
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
        }

        table.custom-table {
            width: auto !important;
            min-width: 50%; 
            margin-left: auto;
            margin-right: auto;
            border-collapse: collapse;
            font-size: 13px;
            margin-bottom: 20px;
            border: 1px solid #dee2e6;
        }
        table.custom-table th {
            background-color: #003876 !important;
            color: #ffffff !important;
            font-weight: bold;
            padding: 10px 15px;
            text-align: center !important;
            border-bottom: 2px solid #002b5e;
            white-space: nowrap;
        }
        table.custom-table td {
            padding: 8px 15px;
            text-align: center !important;
            border-bottom: 1px solid #dee2e6;
            vertical-align: middle;
            white-space: nowrap;
            color: #333333;
        }
        tr.success-row { background-color: #e3f9e5 !important; }
        tr.warning-row { background-color: #fffbeb !important; }
        tr.default-row { background-color: #ffffff; }
        tr.default-row:hover { background-color: #f1f3f5; }

        table.summary-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 10px;
            background-color: white;
            border: 2px solid #003876;
        }
        table.summary-table th {
            background-color: #003876;
            color: white;
            padding: 6px 4px;
            text-align: center;
            font-weight: bold;
            white-space: nowrap;
        }
        table.summary-table td {
            padding: 6px 4px;
            text-align: center;
            font-weight: bold;
            border-bottom: 1px solid #dee2e6;
            color: #e11d48; 
        }

        .update-time-box {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 42px;
            background-color: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #003876;
            color: #003876;
            font-weight: bold;
            font-size: 14px;
            transform: translateY(-1px);
        }

        div.stButton > button {
            width: 100%;
            height: 42px;
            background-color: #003876 !important;
            border: 1px solid #003876 !important;
            border-radius: 8px !important;
            margin-top: 2px;
        }
        div.stButton > button, div.stButton > button * {
            color: #ffffff !important;
            font-weight: bold !important;
        }
        div.stButton > button:hover {
            background-color: #00254d !important;
            border-color: #00254d !important;
        }
        div.stButton > button:active {
            background-color: #001833 !important;
        }

        div[data-testid="stMarkdownContainer"] p {
            font-weight: bold;
            color: #333;
            font-size: 14px;
        }
        .target-highlight {
            color: #003876;
            font-weight: 900;
            text-decoration: underline;
            text-decoration-color: #a5d8ff;
            text-decoration-thickness: 3px;
        }
    </style>
    """, unsafe_allow_html=True)


apply_custom_css()

# ==============================================================================
# [레이아웃] 타이틀 + 요약 표
# ==============================================================================
col_header, col_summary = st.columns([2, 1.2], vertical_alignment="center")

with col_header:
    st.title("🦅 연세대학교 선거 실시간 현황")

if 'data' in st.session_state and not st.session_state['data'].empty:
    df_sum = st.session_state['data']
    if '증가' in df_sum.columns:
        inc_total = df_sum[df_sum['선거 단위'] == '총학생회']['증가'].sum()

        mask_college = (
                df_sum['선거 단위'].str.endswith(('대학', '계열', '총동아리연합회')) &
                (df_sum['선거 단위'] != '총학생회') &
                (df_sum['선거 단위'] != '외국인 학생회')
        )
        inc_college = df_sum[mask_college]['증가'].sum()

        mask_dept = ((df_sum['선거 단위'] != '총학생회') & (~mask_college))
        inc_dept = df_sum[mask_dept]['증가'].sum()

        row_total_sa = df_sum[df_sum['선거 단위'] == '총학생회']
        if not row_total_sa.empty:
            rem_total = row_total_sa['투표 성사 잔여 인원'].values[0]
            rem_total = max(0, rem_total) if pd.notna(rem_total) else 0
        else:
            rem_total = 0

        mask_target = df_sum['선거 단위'].apply(is_target_unit)
        target_df = df_sum[mask_target]
        rem_target_sum = target_df['투표 성사 잔여 인원'].apply(lambda x: max(0, x) if pd.notna(x) else 0).sum()
        value_val = rem_total - rem_target_sum

        summary_html = f"""
        <table class="summary-table">
            <thead>
                <tr>
                    <th>총학생회</th>
                    <th>단과대</th>
                    <th>학과</th>
                    <th style="background-color: #00254d;">value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>▲ {int(inc_total):,}</td>
                    <td>▲ {int(inc_college):,}</td>
                    <td>▲ {int(inc_dept):,}</td>
                    <td style="color: #b91c1c; font-weight: 900;">{int(value_val):,}</td>
                </tr>
            </tbody>
        </table>
        """
        with col_summary:
            st.markdown(summary_html, unsafe_allow_html=True)

st.markdown("---")


def get_data_from_server():
    url = "https://election.yonsei.ac.kr/votes"

    options = webdriver.ChromeOptions()
    # [서버 환경 필수 옵션]
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # 봇 탐지 우회
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # [핵심 수정] 서버에 설치된 Chromium과 Driver의 경로를 직접 지정
    try:
        # Streamlit Cloud의 Chromium 기본 설치 경로
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")

        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        # 로컬(내 컴퓨터)에서 실행할 때를 대비한 예외 처리
        try:
            # 로컬에서는 기존 방식대로 시도
            from webdriver_manager.chrome import ChromeDriverManager
            # binary_location 설정 해제 (로컬 크롬 사용)
            options.binary_location = ""
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e2:
            print(f"Driver Init Error: {e}, {e2}")
            return pd.DataFrame()

    try:
        driver.get(url)
        try:
            # 로딩 대기
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "card-custom")))
            time.sleep(1)
        except:
            pass

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')

        all_cards = soup.find_all('div', class_='card-custom')
        data_list = []

        for card in all_cards:
            if not card.find('h4'): continue

            prev_header = card.find_previous('h3')
            if prev_header and "진행중" in prev_header.get_text(strip=True):
                raw_name = card.find('h4').get_text(strip=True)

                clean_name = re.sub(r"연세대학교|제\d+대", "", raw_name).strip()

                if "총학생회" in clean_name:
                    clean_name = "총학생회"
                elif "총동아리연합회" in clean_name:
                    clean_name = "총동아리연합회"
                elif "외국인" in clean_name:
                    clean_name = "외국인 학생회"
                elif "아동" in clean_name and "가족" in clean_name:
                    clean_name = "아동가족학과"
                elif "상경·경영대학" in clean_name:
                    if "총투표" in clean_name:
                        pass
                    else:
                        clean_name = "상경·경영대학"
                else:
                    remove_list = ["이과대학", "2026년도", "2026학년도", "선거운동본부", "학생회 선거", "학생회", "선거"]
                    for word in remove_list:
                        clean_name = clean_name.replace(word, "")

                clean_name = " ".join(clean_name.split())

                commission_name = get_commission(clean_name)
                if commission_name == "기타/공통":
                    commission_name = get_commission(raw_name)

                rate, voted, total, remaining = None, None, None, None

                labels = card.find_all('p', class_='text-black-50')
                for label in labels:
                    text = label.get_text(strip=True)
                    val_tag = label.find_next_sibling('h5')
                    if val_tag:
                        val = val_tag.get_text(strip=True)
                        if "투표율" in text:
                            if '(' in val:
                                parts = val.split('(')
                                try:
                                    rate = float(parts[0].replace('%', '').strip())
                                    voted = int(parts[1].replace('명', '').replace(')', '').replace(',', '').strip())
                                except:
                                    pass
                            else:
                                try:
                                    rate = float(val.replace('%', '').strip())
                                except:
                                    pass
                        elif "총 유권자" in text:
                            try:
                                total = int(val.replace('명', '').replace(',', '').strip())
                            except:
                                pass
                        elif "투표 성사" in text or "남은 투표" in text:
                            try:
                                remaining = int(val.replace('명', '').replace(',', '').strip())
                            except:
                                pass

                data_list.append({
                    "담당 선관위": commission_name,
                    "선거 단위": clean_name,
                    "투표율": rate,
                    "투표자 수": voted,
                    "총 유권자": total,
                    "투표 성사 잔여 인원": remaining
                })

                if clean_name == "외국인 학생회":
                    break

        df = pd.DataFrame(data_list)
        if not df.empty:
            df['orig_index'] = df.index

            ORDER_LIST = [
                "중앙선거관리위원회", "총동아리연합회", "문과대학", "상경·경영대학", "이과대학",
                "공과대학", "인공지능융합대학",
                "신과대학", "사회과학대학", "생명시스템대학", "음악대학",
                "생활과학대학", "교육과학대학", "체육계열", "의과대학", "치과대학",
                "간호대학", "약학대학", "언더우드국제대학", "글로벌인재대학"
            ]
            df['commission_order'] = pd.Categorical(df['담당 선관위'], categories=ORDER_LIST, ordered=True)
            df = df.sort_values(by=['commission_order', 'orig_index'])

            df = df.drop(columns=['orig_index', 'commission_order'])
            df.insert(0, '일련번호', range(1, len(df) + 1))

        return df

    except Exception as e:
        print(f"Crawling Error: {e}")
        return pd.DataFrame()
    finally:
        try:
            driver.quit()
        except:
            pass

def process_new_data(new_df):
    if 'data' in st.session_state and not st.session_state['data'].empty:
        old_df = st.session_state['data']
        if '선거 단위' in old_df.columns and '투표자 수' in old_df.columns:
            old_map = dict(zip(old_df['선거 단위'], old_df['투표자 수']))
            diffs = []
            for _, row in new_df.iterrows():
                unit = row['선거 단위']
                curr = row['투표자 수']
                if pd.notna(curr):
                    prev = old_map.get(unit)
                    diff = curr - prev if prev is not None and pd.notna(prev) else 0
                else:
                    diff = 0
                diffs.append(diff)
            new_df['증가'] = diffs
        else:
            new_df['증가'] = 0
    else:
        new_df['증가'] = 0
    return new_df


def create_html_table(df):
    html = '<table class="custom-table">'
    html += '<thead><tr>'
    cols = ['No.', '담당 선관위', '선거 단위', '투표율', '투표자 수', '증가', '총 유권자', '투표 성사 잔여 인원']
    for col in cols:
        html += f'<th>{col}</th>'
    html += '</tr></thead>'
    html += '<tbody>'
    for _, row in df.iterrows():
        unit_name = row['선거 단위']
        remaining = row['투표 성사 잔여 인원']
        voted = row['투표자 수']
        diff = row.get('증가', 0)

        row_class = "default-row"
        if not pd.isna(remaining):
            if remaining <= 0:
                row_class = "success-row"
            elif not pd.isna(voted) and voted > 0 and remaining <= (voted * 0.2):
                row_class = "warning-row"

        diff_html = "-"
        if diff > 0: diff_html = f'<span style="color: #e11d48; font-weight: bold;">▲ {int(diff):,}</span>'

        unit_display = unit_name
        if is_target_unit(unit_name):
            unit_display = f'<span class="target-highlight">{unit_name}</span>'

        html += f'<tr class="{row_class}">'
        html += f"<td>{row['일련번호']}</td>"
        html += f"<td>{row['담당 선관위']}</td>"
        html += f"<td>{unit_display}</td>"
        html += f"<td>{row['투표율']:.2f}%" if not pd.isna(row['투표율']) else "<td>-</td>"
        html += f"<td>{int(row['투표자 수']):,}</td>" if not pd.isna(row['투표자 수']) else "<td>-</td>"
        html += f"<td>{diff_html}</td>"
        html += f"<td>{int(row['총 유권자']):,}</td>" if not pd.isna(row['총 유권자']) else "<td>-</td>"
        html += f"<td>{int(remaining):,}</td>" if not pd.isna(remaining) else "<td>-</td>"
        html += '</tr>'
    html += '</tbody></table>'
    return html


if 'last_updated' not in st.session_state:
    st.session_state['last_updated'] = "-"
if 'data' not in st.session_state:
    st.session_state['data'] = pd.DataFrame()

# ==============================================================================
# 상단 컨트롤 패널
# ==============================================================================
col_toggle, col_btn, col_time = st.columns([1.5, 1.5, 3], vertical_alignment="bottom")

with col_toggle:
    st.write("")
    st.write("")
    auto_refresh = st.toggle("🔄 1분 자동 업데이트", value=False)

with col_btn:
    st.write("")
    manual_refresh = st.button("📥 수동 업데이트", type="primary", use_container_width=True)

with col_time:
    time_text = st.session_state['last_updated']
    st.markdown(f'''
        <div class="update-time-box">
            최근 업데이트: {time_text}
        </div>
    ''', unsafe_allow_html=True)

st.markdown("---")

# --- 데이터 갱신 ---
should_fetch = False
if manual_refresh:
    should_fetch = True
elif auto_refresh and st.session_state['data'].empty:
    should_fetch = True

if should_fetch:
    with st.spinner('데이터를 수집 중입니다...'):
        new_data = get_data_from_server()
        if not new_data.empty:
            new_data = process_new_data(new_data)
            st.session_state['data'] = new_data
            st.session_state['last_updated'] = datetime.now().strftime("%m월 %d일 %H시 %M분 %S초")
            st.rerun()

# --- 데이터 표시 ---
if not st.session_state['data'].empty:
    df = st.session_state['data']

    col_filter, col_sort = st.columns([3, 1])
    with col_filter:
        commission_list = sorted(df['담당 선관위'].unique().tolist())
        selected_commissions = st.multiselect("🔍 담당 선관위 필터 (비워두면 전체 보기)", options=commission_list, default=[])
    with col_sort:
        sort_option = st.selectbox("🔽 정렬 기준", ["기본순", "투표율 높은 순", "투표율 낮은 순", "투표자 많은 순", "잔여 인원 적은 순", "가나다 순"])

    if selected_commissions:
        df_filtered = df[df['담당 선관위'].isin(selected_commissions)]
    else:
        df_filtered = df

    df_valid = df_filtered[
        (df_filtered['총 유권자'].notna()) & (df_filtered['총 유권자'] > 0) & (df_filtered['투표 성사 잔여 인원'].notna())].copy()
    df_invalid = df_filtered[~((df_filtered['총 유권자'] > 0) & (df_filtered['투표 성사 잔여 인원'].notna()))].copy()

    if sort_option == "기본순":
        df_valid = df_valid.sort_values(by="일련번호", ascending=True)
    elif sort_option == "투표율 높은 순":
        df_valid = df_valid.sort_values(by="투표율", ascending=False)
    elif sort_option == "투표율 낮은 순":
        df_valid = df_valid.sort_values(by="투표율", ascending=True)
    elif sort_option == "투표자 많은 순":
        df_valid = df_valid.sort_values(by="투표자 수", ascending=False)
    elif sort_option == "잔여 인원 적은 순":
        df_valid = df_valid.sort_values(by="투표 성사 잔여 인원", ascending=True)
    elif sort_option == "가나다 순":
        df_valid = df_valid.sort_values(by="선거 단위", ascending=True)

    if not df_valid.empty:
        st.success(f"📊 현재 진행 중인 선거: {len(df_valid)}개")

        # 엑셀 저장 로직
        df_export = df_valid.copy()


        def restore_name_for_excel(name):
            skip_keywords = ["동아리연합회", "투표", "위원회", "연합회장"]
            if name.endswith("학생회") or any(k in name for k in skip_keywords):
                return name
            return f"{name} 학생회"


        df_export['선거 단위'] = df_export['선거 단위'].apply(restore_name_for_excel)
        df_export['투표율'] = df_export['투표율'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "-")
        df_export['비고'] = df_export['투표 성사 잔여 인원'].apply(lambda x: "(개표 가능)" if pd.notna(x) and x <= 0 else "")
        df_export = df_export.drop(columns=['투표자 수', '증가', '총 유권자', '투표 성사 잔여 인원'], errors='ignore')

        file_name = f"yonsei_vote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv = df_export.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="💾 엑셀 저장", data=csv, file_name=file_name, mime='text/csv')
        st.markdown(create_html_table(df_valid), unsafe_allow_html=True)

        with st.expander("📋 공지용 텍스트 복사 (클릭해서 열기)", expanded=False):
            clipboard_text = ""
            ORDERED_COMMISSIONS = [
                "중앙선거관리위원회", "총동아리연합회", "문과대학", "상경·경영대학", "이과대학",
                "공과대학", "인공지능융합대학",
                "신과대학", "사회과학대학", "생명시스템대학", "음악대학",
                "생활과학대학", "교육과학대학", "체육계열", "의과대학", "치과대학",
                "간호대학", "약학대학", "언더우드국제대학", "글로벌인재대학"
            ]
            found_commissions = df_valid['담당 선관위'].unique().tolist()
            sorted_commissions = [c for c in ORDERED_COMMISSIONS if c in found_commissions]
            extras = [c for c in found_commissions if c not in ORDERED_COMMISSIONS]
            sorted_commissions.extend(extras)

            for comm in sorted_commissions:
                group = df_valid[df_valid['담당 선관위'] == comm]
                if group.empty: continue

                for _, row in group.iterrows():
                    unit_name = row['선거 단위']
                    rate = row['투표율'] if pd.notna(row['투표율']) else 0.0

                    skip_keywords = ["학생회", "위원회", "투표", "동아리연합회", "연합회장"]
                    if any(k in unit_name for k in skip_keywords):
                        final_name = unit_name
                    else:
                        final_name = f"{unit_name} 학생회"

                    clipboard_text += f"{final_name} {rate:.2f}%\n"
                clipboard_text += "\n"

            st.info("우측 상단의 'Copy' 아이콘을 누르면 전체 내용이 복사됩니다.")
            st.code(clipboard_text, language="text")

    if not df_invalid.empty:
        st.markdown("---")
        st.subheader("📌 일부 정보 미표기 단위")
        st.info(f"아래 {len(df_invalid)}개 단위는 상세 정보가 확인되지 않습니다.")


        def safe_format_int(val):
            try:
                return f"{int(val):,}"
            except:
                return val


        def safe_format_float(val):
            try:
                return f"{float(val):.2f}%"
            except:
                return val


        df_show = df_invalid.fillna("-")
        df_show['투표자 수'] = df_show['투표자 수'].apply(lambda x: safe_format_int(x) if x != '-' else '-')
        df_show['총 유권자'] = df_show['총 유권자'].apply(lambda x: safe_format_int(x) if x != '-' else '-')
        df_show['투표 성사 잔여 인원'] = df_show['투표 성사 잔여 인원'].apply(lambda x: safe_format_int(x) if x != '-' else '-')
        df_show['투표율'] = df_show['투표율'].apply(lambda x: safe_format_float(x) if x != '-' else '-')

        styler_invalid = df_show.style.set_properties(**{'text-align': 'center'}).set_table_styles(
            [{'selector': 'th', 'props': [('text-align', 'center')]}]
        )
        st.dataframe(styler_invalid, use_container_width=True, hide_index=True)

elif st.session_state['last_updated'] != "-":
    st.warning("데이터를 찾지 못했습니다. 다시 시도해주세요.")

if auto_refresh:
    progress_text = "다음 업데이트 대기 중..."
    my_bar = st.progress(0, text=progress_text)
    for percent_complete in range(100):
        time.sleep(0.6)
        my_bar.progress(percent_complete + 1, text=f"{progress_text} ({60 - int(percent_complete * 0.6)}초)")

    with st.spinner('자동 업데이트 중...'):
        new_data = get_data_from_server()
        if not new_data.empty:
            new_data = process_new_data(new_data)
            st.session_state['data'] = new_data
            st.session_state['last_updated'] = datetime.now().strftime("%m월 %d일 %H시 %M분 %S초")
            st.rerun()