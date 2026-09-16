import datetime
import io
import pandas as pd
import streamlit as st
from streamlit_calendar import calendar
from supabase import create_client, Client

# ==========================================
# 1. Supabase 雲端資料庫連線設定
# ==========================================
DEFAULT_URL = "https://uxzxqwpfnuottwtzgopo.supabase.co"
DEFAULT_KEY = "sb_publishable_ki1K1MD3QxUVec1rqkeLYQ_xq5HUfvW"

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
except Exception:
    SUPABASE_URL = DEFAULT_URL

try:
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    SUPABASE_KEY = DEFAULT_KEY

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("⚠️ 雲端資料庫連線失敗，請檢查 SUPABASE_URL 與 SUPABASE_KEY 設定。")
    st.stop()

def get_settings():
    res = supabase.table("system_settings").select("*").execute()
    settings = {item["key"]: float(item["value"]) for item in res.data}
    return settings

# ==========================================
# 2. 國定假日與假日判斷邏輯
# ==========================================
# 台灣國定假日清單 (2025/2026/2027)
HOLIDAYS = {
    # 2026 年國定假日
    "2026-01-01",  # 元旦
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",  # 農曆春節
    "2026-02-28",  # 二二八紀念日
    "2026-04-03", "2026-04-04", "2026-04-05",  # 兒童節/清明節
    "2026-06-19",  # 端午節
    "2026-09-25",  # 中秋節
    "2026-10-10",  # 國慶日
    # 2027 年國定假日
    "2027-01-01",  # 元旦
    "2027-02-05", "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",  # 農曆春節
    "2027-02-28",  # 二二八紀念日
    "2027-04-04", "2027-04-05",  # 兒童節/清明節
    "2027-06-09",  # 端午節
    "2027-09-15",  # 中秋節
    "2027-10-10",  # 國慶日
}

def is_holiday_or_weekend(d: datetime.date) -> bool:
    """判斷某天是否為星期六、星期日或國定假日"""
    if d.weekday() in [5, 6]:
        return True
    if d.strftime("%Y-%m-%d") in HOLIDAYS:
        return True
    return False

# ==========================================
# 3. 登入與 Session 管理
# ==========================================
st.set_page_config(page_title="家園預約休假系統", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏥 家園預約休假系統 - 登入")
    col1, _ = st.columns([1, 2])
    with col1:
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        if st.button("登入", type="primary", use_container_width=True):
            res = (
                supabase.table("users")
                .select("*")
                .eq("username", username)
                .eq("password", password)
                .execute()
            )
            rows = res.data

            if rows:
                user_data = rows[0]
                st.session_state.user = {
                    "id": user_data["id"],
                    "name": user_data["name"],
                    "username": user_data["username"],
                    "role": user_data["role"],
                    "job_title": user_data["job_title"],
                }
                st.rerun()
            else:
                st.error("帳號或密碼錯誤！")
    st.stop()

user = st.session_state.user
st.sidebar.title(f"👤 {user['name']} ({user['role']})")
st.sidebar.caption(f"職稱：{user['job_title']}")
if st.sidebar.button("登出"):
    st.session_state.user = None
    st.rerun()

st.title("🏥 家園預約休假系統")

# ==========================================
# 4. 讀取資料
# ==========================================
leaves_res = (
    supabase.table("leaves")
    .select("id, user_id, leave_date, shift_type, leave_category, status, users(name, job_title)")
    .execute()
)

df_raw = pd.DataFrame(leaves_res.data)

if not df_raw.empty and "users" in df_raw.columns:
    df_raw["name"] = df_raw["users"].apply(
        lambda x: x.get("name") if isinstance(x, dict) else ""
    )
    df_raw["job_title"] = df_raw["users"].apply(
        lambda x: x.get("job_title") if isinstance(x, dict) else ""
    )
    if "leave_category" not in df_raw.columns:
        df_raw["leave_category"] = "月休"
    else:
        df_raw["leave_category"] = df_raw["leave_category"].fillna("月休")
    df_leaves = df_raw
else:
    df_leaves = pd.DataFrame(
        columns=["id", "user_id", "leave_date", "shift_type", "leave_category", "status", "name", "job_title"]
    )

notes_res = supabase.table("daily_notes").select("*").execute()
df_notes = pd.DataFrame(notes_res.data)

settings = get_settings()

tab1, tab2, tab3 = st.tabs(["📅 月曆班表與預約", "📝 我的休假紀錄", "👑 主管管理專區"])

# ==========================================
# Tab 1: 視覺化月曆與預約
# ==========================================
with tab1:
    st.subheader("1. 申請預約休假")

    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    with c1:
        leave_date = st.date_input("選擇休假日期", min_value=datetime.date.today())
    with c2:
        leave_category = st.selectbox("休假類別", ["月休", "特休", "上午休", "下午休"], index=0)
    with c3:
        shift_type = st.selectbox("選擇班別", ["白班", "小夜班", "大夜班"])
    with c4:
        st.write("")
        st.write("")
        submit_btn = st.button("提交預約", type="primary")

    if submit_btn:
        date_str = leave_date.strftime("%Y-%m-%d")
        is_hol = is_holiday_or_weekend(leave_date)

        user_same_day = (
            df_leaves[
                (df_leaves["user_id"] == user["id"])
                & (df_leaves["leave_date"] == date_str)
            ]
            if not df_leaves.empty
            else pd.DataFrame()
        )

        if not user_same_day.empty:
            st.error("⚠️ 您當天已經有預約或主管已為您排休！")
        else:
            month_str = leave_date.strftime("%Y-%m")
            user_month_leaves = (
                df_leaves[
                    (df_leaves["user_id"] == user["id"])
                    & (df_leaves["leave_date"].str.startswith(month_str))
                ]
                if not df_leaves.empty
                else pd.DataFrame()
            )

            personal_warnings = []

            # 1. 檢查個人本月總天數
            max_m_limit = int(settings.get("max_monthly_leaves", 8))
            if len(user_month_leaves) >= max_m_limit:
                personal_warnings.append(f"本月預約天數已超過總額度 ({max_m_limit}天)")

            # 2. 檢查個人假日天數 (含國定假日)
            if is_hol:
                weekend_count = 0
                for l_date_str in user_month_leaves.get("leave_date", []):
                    if is_holiday_or_weekend(datetime.date.fromisoformat(l_date_str)):
                        weekend_count += 1
                
                if user["job_title"] == "護理師":
                    shift_key_map = {"白班": "max_weekend_nurse_day", "小夜班": "max_weekend_nurse_night1", "大夜班": "max_weekend_nurse_night2"}
                    weekend_limit = int(settings.get(shift_key_map.get(shift_type, ""), 2))
                else:
                    weekend_limit = int(settings.get("max_weekend_leaves", 2))

                if weekend_count >= weekend_limit:
                    personal_warnings.append(f"本月假日(含國定假日)排休已超過上限 ({weekend_limit}天)")

            # 3. 檢查當天同職稱同班別的人數限制 (劃分平日與假日)
            if user["job_title"] == "護理師":
                if is_hol:
                    shift_limit_map = {"白班": "limit_nurse_day_hol", "小夜班": "limit_nurse_night1_hol", "大夜班": "limit_nurse_night2_hol"}
                else:
                    shift_limit_map = {"白班": "limit_nurse_day_wd", "小夜班": "limit_nurse_night1_wd", "大夜班": "limit_nurse_night2_wd"}
                daily_limit = int(settings.get(shift_limit_map.get(shift_type, ""), 2))
            else:
                if is_hol:
                    job_key_map = {"照服員": "limit_caregiver_hol", "行政": "limit_staff_hol"}
                else:
                    job_key_map = {"照服員": "limit_caregiver_wd", "行政": "limit_staff_wd"}
                daily_limit = int(settings.get(job_key_map.get(user["job_title"], ""), 99))

            same_job_shift_leaves = (
                df_leaves[
                    (df_leaves["leave_date"] == date_str)
                    & (df_leaves["job_title"] == user["job_title"])
                    & (df_leaves["shift_type"] == shift_type)
                ]
                if not df_leaves.empty
                else pd.DataFrame()
            )

            current_count = len(same_job_shift_leaves)
            # 加上本次的新預約後是否超過限制
            is_conflict = (current_count + 1) > daily_limit
            new_status = "待協調/抽籤" if is_conflict else "已預約"

            # 新增本次預約
            supabase.table("leaves").insert({
                "user_id": user["id"],
                "leave_date": date_str,
                "leave_category": leave_category,
                "shift_type": shift_type,
                "status": new_status,
            }).execute()

            # 如果發生人數衝突，將當天「同一職稱、同一班別」的所有舊預約全部更新為「待協調/抽籤」
            if is_conflict and not same_job_shift_leaves.empty:
                existing_ids = same_job_shift_leaves["id"].tolist()
                for e_id in existing_ids:
                    curr_st = same_job_shift_leaves[same_job_shift_leaves["id"] == e_id]["status"].values[0]
                    if curr_st != "👑 主管預排":
                        supabase.table("leaves").update({"status": "待協調/抽籤"}).eq("id", int(e_id)).execute()

            # 顯示提示訊息
            day_type_label = "假日/國定假日" if is_hol else "平日"
            if is_conflict:
                st.warning(f"⚠️ 當天({day_type_label})【{user['job_title']}-{shift_type}】休假人數超過上限 ({daily_limit}人)，當天該班別所有申請人均已轉為「待協調/抽籤」狀態。")
            else:
                st.success(f"✅ 成功預約 {date_str} ({leave_category}-{shift_type}) 休假！")

            if personal_warnings:
                st.info("⚠️ 提醒：超過預約天數，請注意排休公平性！（" + "；".join(personal_warnings) + "）")

            st.rerun()

    st.markdown("---")
    st.subheader("2. 本月視覺化互動月曆")

    calendar_events = []

    if not df_notes.empty:
        for _, row in df_notes.iterrows():
            calendar_events.append(
                {
                    "id": f"note_{row['id']}",
                    "title": f"📌 備註: {row['note']}",
                    "start": row["date"],
                    "allDay": True,
                    "backgroundColor": "#EF4444",
                    "borderColor": "#EF4444",
                    "order": 0,
                    "extendedProps": {
                        "type": "note",
                        "full_text": f"📌 重要備註事項：\n{row['note']}",
                    },
                }
            )

    SHIFT_COLORS = {"白班": "#3B82F6", "小夜班": "#F59E0B", "大夜班": "#8B5CF6"}
    if not df_leaves.empty:
        for _, row in df_leaves.iterrows():
            cat = row.get("leave_category", "月休")
            
            if cat == "月休":
                cat_label = row['shift_type']
            else:
                cat_label = f"{cat}-{row['shift_type']}"

            if row["status"] == "👑 主管預排":
                color = "#EC4899"
                title_text = f"👑 {row['name']} ({cat_label})"
            elif "待協調" in row["status"]:
                color = "#9CA3AF"
                title_text = f"⚠️ {row['name']} ({cat_label})"
            else:
                color = SHIFT_COLORS.get(row["shift_type"], "#10B981")
                title_text = f"{row['name']} ({cat_label})"

            calendar_events.append(
                {
                    "id": f"leave_{row['id']}",
                    "title": title_text,
                    "start": row["leave_date"],
                    "backgroundColor": color,
                    "borderColor": color,
                    "order": 1,
                    "extendedProps": {
                        "type": "leave",
                        "full_text": f"👤 人員：{row['name']}\n💼 職稱：{row['job_title']}\n🏖️ 休假類別：{cat}\n⏰ 預約班別：{row['shift_type']}\n📌 狀態：{row['status']}",
                    },
                }
            )

    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek",
        },
        "initialView": "dayGridMonth",
        "locale": "zh-tw",
        "buttonText": {"today": "今天", "month": "月", "week": "週"},
        "dayMaxEvents": 3,
        "eventOrder": "order",
    }

    cal_result = calendar(events=calendar_events, options=calendar_options, key="leave_calendar")

    if cal_result and "eventClick" in cal_result and cal_result["eventClick"]:
        event_info = cal_result["eventClick"]["event"]
        props = event_info.get("extendedProps", {})
        full_text = props.get("full_text", event_info.get("title", ""))

        @st.dialog("🔍 排休與備註完整詳情")
        def show_details(text):
            st.text(text)
            if st.button("關閉視窗", type="primary"):
                st.rerun()

        show_details(full_text)

# ==========================================
# Tab 2: 我的休假紀錄
# ==========================================
with tab2:
    st.subheader("我的預約與主管預排列表")
    my_leaves = (
        df_leaves[df_leaves["user_id"] == user["id"]]
        if not df_leaves.empty
        else pd.DataFrame()
    )

    if my_leaves.empty:
        st.info("您目前沒有任何休假預約或預排紀錄。")
    else:
        for idx, row in my_leaves.iterrows():
            cat = row.get("leave_category", "月休")
            col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
            col_a.write(f"📅 **{row['leave_date']}**")
            col_b.write(f"類別：{cat}（{row['shift_type']}）")

            if row["status"] == "👑 主管預排":
                col_c.write("狀態：`:pink[👑 主管指定預排]`")
            elif "待協調" in row["status"]:
                col_c.write(f"狀態：`:orange[{row['status']}]`")
            else:
                col_c.write(f"狀態：`:green[{row['status']}]`")

            with col_d:
                if st.button("取消 / 刪除", key=f"del_{row['id']}"):
                    del_id = row['id']
                    del_date_str = row['leave_date']
                    del_date = datetime.date.fromisoformat(del_date_str)
                    del_shift = row['shift_type']
                    del_job = row['job_title']
                    is_hol = is_holiday_or_weekend(del_date)

                    # 刪除目標筆數
                    supabase.table("leaves").delete().eq("id", del_id).execute()

                    # 刪除後自動重新計算當天同班別是否解除了人數衝突
                    remaining = df_leaves[
                        (df_leaves["leave_date"] == del_date_str)
                        & (df_leaves["job_title"] == del_job)
                        & (df_leaves["shift_type"] == del_shift)
                        & (df_leaves["id"] != del_id)
                    ]

                    if del_job == "護理師":
                        if is_hol:
                            shift_limit_map = {"白班": "limit_nurse_day_hol", "小夜班": "limit_nurse_night1_hol", "大夜班": "limit_nurse_night2_hol"}
                        else:
                            shift_limit_map = {"白班": "limit_nurse_day_wd", "小夜班": "limit_nurse_night1_wd", "大夜班": "limit_nurse_night2_wd"}
                        daily_limit = int(settings.get(shift_limit_map.get(del_shift, ""), 2))
                    else:
                        if is_hol:
                            job_key_map = {"照服員": "limit_caregiver_hol", "行政": "limit_staff_hol"}
                        else:
                            job_key_map = {"照服員": "limit_caregiver_wd", "行政": "limit_staff_wd"}
                        daily_limit = int(settings.get(job_key_map.get(del_job, ""), 99))

                    # 若剩餘人數降回或低於上限，自動將剩餘的人恢復為「已預約」
                    if len(remaining) <= daily_limit:
                        for rem_id in remaining["id"].tolist():
                            rem_st = remaining[remaining["id"] == rem_id]["status"].values[0]
                            if rem_st != "👑 主管預排":
                                supabase.table("leaves").update({"status": "已預約"}).eq("id", int(rem_id)).execute()

                    st.success("已取消該筆休假紀錄！")
                    st.rerun()

# ==========================================
# Tab 3: 主管管理專區
# ==========================================
with tab3:
    if user["role"] != "主管":
        st.error("⛔ 您沒有存取主管專區的權限！")
    else:
        st.subheader("👑 主管維護與管控專區")

        # 1. 審核與變更排休狀態
        st.markdown("##### ✏️ 1. 審核與調整員工排休狀態")
        if df_leaves.empty:
            st.info("目前無任何排休申請。")
        else:
            df_leaves_edit = df_leaves[["id", "leave_date", "name", "job_title", "leave_category", "shift_type", "status"]].copy()
            df_leaves_edit.columns = ["紀錄ID", "日期", "姓名", "職稱", "休假類別", "班別", "審核狀態"]
            
            column_config_leaves = {
                "紀錄ID": st.column_config.NumberColumn("紀錄ID", disabled=True),
                "日期": st.column_config.TextColumn("日期", disabled=True),
                "姓名": st.column_config.TextColumn("姓名", disabled=True),
                "職稱": st.column_config.TextColumn("職稱", disabled=True),
                "休假類別": st.column_config.TextColumn("休假類別", disabled=True),
                "班別": st.column_config.TextColumn("班別", disabled=True),
                "審核狀態": st.column_config.SelectboxColumn("審核狀態", options=["已預約", "待協調/抽籤", "👑 主管預排"], required=True),
            }

            edited_leaves_df = st.data_editor(
                df_leaves_edit,
                column_config=column_config_leaves,
                use_container_width=True,
                hide_index=True,
                key="leave_editor",
            )

            if st.button("💾 儲存審核狀態變更", type="primary"):
                for _, r in edited_leaves_df.iterrows():
                    supabase.table("leaves").update({"status": r["審核狀態"]}).eq("id", int(r["紀錄ID"])).execute()
                st.success("✅ 所有排休審核狀態已成功更新！")
                st.rerun()

        st.markdown("---")

        # 2. 主管預排
        st.markdown("##### 📌 2. 主管預先指定員工休假")
        users_res = supabase.table("users").select("id, name, job_title").execute()
        df_users_list = pd.DataFrame(users_res.data)

        pc1, pc2, pc3, pc4, pc5 = st.columns([2, 2, 2, 2, 1])
        with pc1:
            user_options = {
                f"{r['name']} ({r['job_title']})": r["id"]
                for _, r in df_users_list.iterrows()
            }
            selected_user_label = st.selectbox("選擇指定員工", list(user_options.keys()))
            target_user_id = user_options[selected_user_label]
        with pc2:
            admin_target_date = st.date_input("指定休假日期", datetime.date.today(), key="admin_target_date")
        with pc3:
            admin_leave_cat = st.selectbox("休假類別", ["月休", "特休", "上午休", "下午休"], index=0, key="admin_cat")
        with pc4:
            admin_shift_type = st.selectbox("指定班別", ["白班", "小夜班", "大夜班"], key="admin_shift")
        with pc5:
            st.write("")
            st.write("")
            if st.button("送出預排", type="primary"):
                ad_date_str = admin_target_date.strftime("%Y-%m-%d")
                supabase.table("leaves").insert({
                    "user_id": target_user_id,
                    "leave_date": ad_date_str,
                    "leave_category": admin_leave_cat,
                    "shift_type": admin_shift_type,
                    "status": "👑 主管預排",
                }).execute()

                st.success(f"✅ 已成功為【{selected_user_label}】預先指定 {ad_date_str} ({admin_leave_cat}) 休假！")
                st.rerun()

        st.markdown("---")

        # 3. 人員帳號管理
        st.markdown("##### 👥 3. 人員帳號管理與重設密碼 (可直接在表格內點擊修改)")
        all_users_res = supabase.table("users").select("*").execute()
        df_all_users = pd.DataFrame(all_users_res.data)
        df_all_users = df_all_users[["id", "name", "username", "password", "role", "job_title"]]
        df_all_users.columns = ["人員ID", "姓名", "帳號", "密碼", "權限角色", "職稱"]

        column_config = {
            "人員ID": st.column_config.NumberColumn("人員ID", disabled=True),
            "權限角色": st.column_config.SelectboxColumn("權限角色", options=["員工", "主管"], required=True),
            "職稱": st.column_config.SelectboxColumn("職稱", options=["護理師", "照服員", "行政"], required=True),
        }

        edited_df = st.data_editor(
            df_all_users,
            column_config=column_config,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="user_editor",
        )

        if st.button("💾 儲存所有人員變更"):
            current_ids = [int(row["人員ID"]) for _, row in edited_df.iterrows() if pd.notna(row["人員ID"])]
            all_db_ids = [u["id"] for u in all_users_res.data]
            to_delete = set(all_db_ids) - set(current_ids)
            for del_id in to_delete:
                supabase.table("leaves").delete().eq("user_id", del_id).execute()
                supabase.table("users").delete().eq("id", del_id).execute()

            for _, row in edited_df.iterrows():
                user_data = {
                    "name": row["姓名"],
                    "username": row["帳號"],
                    "password": row["密碼"],
                    "role": row["權限角色"],
                    "job_title": row["職稱"],
                }
                if pd.isna(row["人員ID"]):
                    supabase.table("users").insert(user_data).execute()
                else:
                    supabase.table("users").update(user_data).eq("id", int(row["人員ID"])).execute()

            st.success("✅ 人員資料已成功儲存至雲端資料庫！")
            st.rerun()

        st.markdown("---")

        # 4. 規則動態設定
        st.markdown("##### ⚙️ 4. 排休規則限制設定")

        st.caption("全機構通用限制：")
        gc1, gc2 = st.columns(2)
        with gc1:
            set_month_max = st.number_input("每人每月預約總上限 (天)", value=int(settings.get("max_monthly_leaves", 8)))
        with gc2:
            set_weekend_max = st.number_input("非護理人員 每月假日(含國定假日)上限 (天)", value=int(settings.get("max_weekend_leaves", 2)))

        st.caption("🏥 護理師專屬規則設定 (區分班別與平假日)：")
        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            st.write("**每月假日上限 (天)**")
            set_nurse_wk_day = st.number_input("護理師-白班 假日上限", value=int(settings.get("max_weekend_nurse_day", 2)))
            set_nurse_wk_n1 = st.number_input("護理師-小夜 假日上限", value=int(settings.get("max_weekend_nurse_night1", 2)))
            set_nurse_wk_n2 = st.number_input("護理師-大夜 假日上限", value=int(settings.get("max_weekend_nurse_night2", 2)))

        with nc2:
            st.write("**【平日】每日休假上限 (人)**")
            set_nurse_day_wd = st.number_input("白班 (平日)", value=int(settings.get("limit_nurse_day_wd", settings.get("limit_nurse_day", 2))))
            set_nurse_n1_wd = st.number_input("小夜班 (平日)", value=int(settings.get("limit_nurse_night1_wd", settings.get("limit_nurse_night1", 1))))
            set_nurse_n2_wd = st.number_input("大夜班 (平日)", value=int(settings.get("limit_nurse_night2_wd", settings.get("limit_nurse_night2", 1))))

        with nc3:
            st.write("**【假日/國定假日】每日休假上限 (人)**")
            set_nurse_day_hol = st.number_input("白班 (假日)", value=int(settings.get("limit_nurse_day_hol", settings.get("limit_nurse_day", 2))))
            set_nurse_n1_hol = st.number_input("小夜班 (假日)", value=int(settings.get("limit_nurse_night1_hol", settings.get("limit_nurse_night1", 1))))
            set_nurse_n2_hol = st.number_input("大夜班 (假日)", value=int(settings.get("limit_nurse_night2_hol", settings.get("limit_nurse_night2", 1))))

        st.caption("其他職務每日休假上限 (區分平假日)：")
        oc1, oc2 = st.columns(2)
        with oc1:
            st.write("**照服員**")
            set_care_wd = st.number_input("照服員 (平日上限)", value=int(settings.get("limit_caregiver_wd", settings.get("limit_caregiver", 5))))
            set_care_hol = st.number_input("照服員 (假日/國定假日上限)", value=int(settings.get("limit_caregiver_hol", settings.get("limit_caregiver", 3))))
        with oc2:
            st.write("**行政人員**")
            set_staff_wd = st.number_input("行政 (平日上限)", value=int(settings.get("limit_staff_wd", settings.get("limit_staff", 1))))
            set_staff_hol = st.number_input("行政 (假日/國定假日上限)", value=int(settings.get("limit_staff_hol", settings.get("limit_staff", 1))))

        if st.button("💾 儲存規則設定", type="primary"):
            new_rules = [
                ("max_monthly_leaves", set_month_max),
                ("max_weekend_leaves", set_weekend_max),
                ("max_weekend_nurse_day", set_nurse_wk_day),
                ("max_weekend_nurse_night1", set_nurse_wk_n1),
                ("max_weekend_nurse_night2", set_nurse_wk_n2),
                ("limit_nurse_day_wd", set_nurse_day_wd),
                ("limit_nurse_night1_wd", set_nurse_n1_wd),
                ("limit_nurse_night2_wd", set_nurse_n2_wd),
                ("limit_nurse_day_hol", set_nurse_day_hol),
                ("limit_nurse_night1_hol", set_nurse_n1_hol),
                ("limit_nurse_night2_hol", set_nurse_n2_hol),
                ("limit_caregiver_wd", set_care_wd),
                ("limit_caregiver_hol", set_care_hol),
                ("limit_staff_wd", set_staff_wd),
                ("limit_staff_hol", set_staff_hol),
            ]
            for k, v in new_rules:
                supabase.table("system_settings").upsert({"key": k, "value": v}).execute()
            st.success("✅ 排休規則已更新至雲端資料庫！")
            st.rerun()

        st.markdown("---")

        # 5. 每日行程備註
        st.markdown("##### 📌 5. 每日行程備註")
        nb_col1, nb_col2, nb_col3 = st.columns([2, 3, 1])
        with nb_col1:
            note_date = st.date_input("選擇日期", datetime.date.today(), key="note_date")
        with nb_col2:
            note_content = st.text_input("行程備註 (例: 督導查核、教育訓練)")
        with nb_col3:
            st.write("")
            st.write("")
            if st.button("儲存備註"):
                nd_str = note_date.strftime("%Y-%m-%d")
                supabase.table("daily_notes").upsert({"date": nd_str, "note": note_content}).execute()
                st.success("備註已更新！")
                st.rerun()

        st.markdown("---")

        # 6. Excel 匯出
        st.markdown("##### 📊 6. 匯出 Excel 清單")
        if not df_leaves.empty:
            excel_cols = ["leave_date", "name", "job_title", "leave_category", "shift_type", "status"]
            excel_headers = ["休假日期", "人員姓名", "職稱", "休假類別", "預約班別", "審核狀態"]

            excel_data = df_leaves[excel_cols].copy()
            excel_data.columns = excel_headers

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                excel_data.to_excel(writer, index=False, sheet_name="排休清單")

            st.download_button(
                label="📥 下載排休清單 (Excel)",
                data=buffer.getvalue(),
                file_name=f"機構排休清單_{datetime.date.today().strftime('%Y%m')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
