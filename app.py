import io
import calendar
import requests
import pandas as pd
import streamlit as st

import urllib3

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)
# =========================================================
# 設定
# =========================================================

STATION_LIST_URL = "https://codis.cwa.gov.tw/api/station_list"
REPORT_URL = "https://codis.cwa.gov.tw/api/station?"

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://codis.cwa.gov.tw/StationData",
    "User-Agent": "Mozilla/5.0",
}

TIMEOUT = 30


# =========================================================
# API：取得測站清單
# =========================================================

@st.cache_data(ttl=3600)
def get_station_list():
    response = requests.get(
        STATION_LIST_URL,
        headers=HEADERS,
        timeout=TIMEOUT,
        verify=False
    )
    response.raise_for_status()
    return response.json()


def build_station_mapping(data):
    """
    將 station_list API 轉成：

    {
        "466881": {
            "stn_type": "cwb",
            "station_name": "板橋",
            ...
        }
    }
    """

    mapping = {}

    for group in data.get("data", []):
        stn_type = group.get("stationAttribute", "")

        for station in group.get("item", []):
            stn_id = str(station.get("stationID", "")).strip()

            if not stn_id:
                continue

            mapping[stn_id] = {
                "stn_type": stn_type,
                "station_name": station.get("stationName", ""),
                "latitude": station.get("latitude", ""),
                "longitude": station.get("longitude", ""),
                "altitude": station.get("altitude", ""),
                "address": station.get("address", ""),
                "area": station.get("area", ""),
            }

    return mapping


# =========================================================
# API：取得日／月／年報
# =========================================================

def get_report(stn_id, stn_type, report_type, date_str, start, end):
    payload = {
        "date": date_str,
        "type": report_type,
        "stn_ID": stn_id,
        "stn_type": stn_type,
        "more": "",
        "start": start,
        "end": end,
        "item": "",
    }

    response = requests.post(
        REPORT_URL,
        headers=HEADERS,
        data=payload,
        timeout=TIMEOUT,
        verify=False
    )

    response.raise_for_status()

    result = response.json()

    try:
        return result["data"][0]["dts"]
    except (KeyError, IndexError, TypeError):
        return []


def get_daily(stn_id, stn_type, date):
    date_str = date.strftime("%Y-%m-%d")

    return get_report(
        stn_id,
        stn_type,
        "report_date",
        date_str + "T00:00:00+08:00",
        date_str + "T00:00:00",
        date_str + "T23:59:59"
    )


def get_monthly(stn_id, stn_type, year, month):
    start_date = "{}-{:02d}-01".format(year, month)

    last_day = calendar.monthrange(year, month)[1]
    end_date = "{}-{:02d}-{:02d}".format(year, month, last_day)

    return get_report(
        stn_id,
        stn_type,
        "report_month",
        start_date + "T00:00:00+08:00",
        start_date + "T00:00:00",
        end_date + "T00:00:00"
    )


def get_yearly(stn_id, stn_type, year):
    start_date = "{}-01-01".format(year)
    end_date = "{}-12-31".format(year)

    return get_report(
        stn_id,
        stn_type,
        "report_year",
        start_date + "T00:00:00+08:00",
        start_date + "T00:00:00",
        end_date + "T00:00:00"
    )


def expand_dict_columns(df):
    new_columns = {}
    dict_columns = []

    for column in df.columns:

        has_dict = df[column].apply(
            lambda x: isinstance(x, dict)
        ).any()

        if not has_dict:
            continue

        dict_columns.append(column)

        for index, value in df[column].items():

            if not isinstance(value, dict):
                continue

            for key, item in value.items():

                new_column = "{}_{}".format(
                    column,
                    key
                )

                new_columns.setdefault(
                    new_column,
                    {}
                )

                new_columns[new_column][index] = item

    # 建立展開後欄位
    for column, values in new_columns.items():
        df[column] = pd.Series(values, index=df.index)

    # 移除原始 dict 欄位
    df = df.drop(columns=dict_columns)

    # 移除完全沒有值的欄位
    df = df.dropna(axis=1, how="all")

    # 移除全部為空字串的欄位
    for column in df.columns:
        if df[column].apply(
            lambda x: str(x).strip() == ""
        ).all():
            df = df.drop(columns=[column])

    return df

# =========================================================
# Streamlit
# =========================================================


st.set_page_config(
    page_title="CODIS 氣象資料下載",
    layout="wide"
)

st.title("CODIS 氣象資料下載")


# =========================================================
# 取得測站資料
# =========================================================

try:
    station_json = get_station_list()
    print(station_json)
    station_mapping = build_station_mapping(station_json)

except Exception as e:
    st.error("無法取得測站清單：{}".format(e))
    st.stop()


# =========================================================
# 查詢設定
# =========================================================

col1, col2 = st.columns([1, 2])

with col1:
    report_name = st.selectbox(
        "報表類型",
        ["日報", "月報", "年報"]
    )

with col2:
    stn_id = st.text_input(
        "測站 ID",
        value="467650"
    ).strip()


# =========================================================
# 測站資訊
# =========================================================

station_info = station_mapping.get(stn_id)

if station_info:
    st.caption(
        "測站：{}　｜　類型：{}　｜　緯度：{}　｜　經度：{}".format(
            station_info["station_name"],
            station_info["stn_type"],
            station_info["latitude"],
            station_info["longitude"]
        )
    )
else:
    st.warning("找不到測站 ID：{}".format(stn_id))


# =========================================================
# 日期設定
# =========================================================

if report_name == "日報":

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日期"
        )

    with col2:
        end_date = st.date_input(
            "結束日期"
        )


elif report_name == "月報":

    # 開始年月
    st.markdown("### 開始年月")

    col1, col2 = st.columns(2)

    with col1:
        start_year = st.number_input(
            "開始年份",
            min_value=1900,
            max_value=2100,
            value=2026,
            step=1,
            key="start_year"
        )

    with col2:
        start_month = st.selectbox(
            "開始月份",
            range(1, 13),
            format_func=lambda x: "{} 月".format(x),
            key="start_month"
        )

    # 結束年月
    st.markdown("### 結束年月")

    col1, col2 = st.columns(2)

    with col1:
        end_year = st.number_input(
            "結束年份",
            min_value=1900,
            max_value=2100,
            value=2026,
            step=1,
            key="end_year"
        )

    with col2:
        end_month = st.selectbox(
            "結束月份",
            range(1, 13),
            index=9,
            format_func=lambda x: "{} 月".format(x),
            key="end_month"
        )


else:

    col1, col2 = st.columns(2)

    with col1:
        start_year = st.number_input(
            "開始年份",
            min_value=1900,
            max_value=2100,
            value=2025,
            step=1
        )

    with col2:
        end_year = st.number_input(
            "結束年份",
            min_value=1900,
            max_value=2100,
            value=2026,
            step=1
        )


# =========================================================
# 查詢
# =========================================================

if st.button("開始下載"):

    if not station_info:
        st.error("請輸入正確的測站 ID。")
        st.stop()

    stn_type = station_info["stn_type"]
    results = []

    try:

        # -------------------------------------------------
        # 日報
        # -------------------------------------------------

        if report_name == "日報":

            if start_date > end_date:
                st.error("開始日期不能晚於結束日期。")
                st.stop()

            current = start_date
            total_days = (end_date - start_date).days + 1

            progress = st.progress(0)

            for i in range(total_days):

                data = get_daily(
                    stn_id,
                    stn_type,
                    current
                )

                results.extend(data)

                progress.progress(
                    int((i + 1) / total_days * 100)
                )

                current = current + pd.Timedelta(days=1)

            progress.empty()

        # -------------------------------------------------
        # 月報
        # -------------------------------------------------

        elif report_name == "月報":

            start_key = int(start_year) * 100 + int(start_month)
            end_key = int(end_year) * 100 + int(end_month)

            if start_key > end_key:
                st.error("開始月份不能晚於結束月份。")
                st.stop()

            year = int(start_year)
            month = int(start_month)

            months = []

            while year * 100 + month <= end_key:

                months.append((year, month))

                month += 1

                if month > 12:
                    month = 1
                    year += 1

            progress = st.progress(0)

            for i, item in enumerate(months):

                data = get_monthly(
                    stn_id,
                    stn_type,
                    item[0],
                    item[1]
                )

                results.extend(data)

                progress.progress(
                    int((i + 1) / len(months) * 100)
                )

            progress.empty()

        # -------------------------------------------------
        # 年報
        # -------------------------------------------------

        else:

            if start_year > end_year:
                st.error("開始年份不能晚於結束年份。")
                st.stop()

            years = range(
                int(start_year),
                int(end_year) + 1
            )

            years = list(years)

            progress = st.progress(0)

            for i, year in enumerate(years):

                data = get_yearly(
                    stn_id,
                    stn_type,
                    year
                )

                results.extend(data)

                progress.progress(
                    int((i + 1) / len(years) * 100)
                )

            progress.empty()

        # =================================================
        # 顯示結果
        # =================================================

        if not results:
            st.warning("API 沒有回傳資料。")
            st.stop()

        df = pd.DataFrame(results)
        df = expand_dict_columns(df)
        st.success(
            "下載完成，共 {} 筆資料。".format(len(df))
        )

        st.dataframe(
            df,
            use_container_width=True
        )

        # =================================================
        # CSV
        # =================================================

        csv_buffer = io.StringIO()

        df.to_csv(
            csv_buffer,
            index=False
        )

        filename = "{}_{}_{}.csv".format(
            stn_id,
            report_name,
            len(df)
        )

        st.download_button(
            label="下載 CSV",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=filename,
            mime="text/csv"
        )

    except requests.RequestException as e:

        st.error(
            "CODIS API 連線失敗：{}".format(e)
        )

    except Exception as e:

        st.error(
            "處理資料時發生錯誤：{}".format(e)
        )
