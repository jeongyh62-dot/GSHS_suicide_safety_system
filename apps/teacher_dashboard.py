import streamlit as st
import sqlite3
import pandas as pd
import math
from datetime import datetime, time
from pathlib import Path

st.set_page_config(
    page_title="교사용 학생 안전관리 Dashboard",
    page_icon="🧑‍🏫",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent

def resolve_db_path():
    project_root = BASE_DIR.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "checkin_data.db"


DB_PATH = resolve_db_path()
CHECKIN_CUTOFF_HOUR = 20

# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            student_id TEXT NOT NULL,
            mood TEXT NOT NULL,
            safety TEXT NOT NULL,
            safety_plan TEXT NOT NULL,
            help_request TEXT NOT NULL,
            memo TEXT,
            monitoring_status TEXT NOT NULL,
            teacher_checked INTEGER DEFAULT 0,
            teacher_note TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS initial_screenings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            student_id TEXT NOT NULL,
            age_15_or_older INTEGER NOT NULL,
            female INTEGER NOT NULL,
            hunger INTEGER NOT NULL,
            alcohol_use INTEGER NOT NULL,
            loneliness INTEGER NOT NULL,
            anxiety INTEGER NOT NULL,
            physically_attacked INTEGER NOT NULL,
            close_friends INTEGER NOT NULL,
            peer_support INTEGER NOT NULL,
            parental_supervision INTEGER NOT NULL,
            parental_attachment INTEGER NOT NULL,
            parental_bonding INTEGER NOT NULL,
            truancy INTEGER NOT NULL,
            physical_activity INTEGER NOT NULL,
            obesity INTEGER NOT NULL,
            predicted_probability REAL NOT NULL,
            reviewer_checked INTEGER DEFAULT 0,
            reviewer_note TEXT DEFAULT '',
            continuous_management INTEGER DEFAULT 0,
            management_source TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS safety_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            warning_signs TEXT DEFAULT '',
            coping_strategies TEXT DEFAULT '',
            social_supports TEXT DEFAULT '',
            professional_supports TEXT DEFAULT '',
            safe_environment TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            plan_status TEXT DEFAULT '미작성'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS management_contacts (
            student_id TEXT PRIMARY KEY,
            phone TEXT DEFAULT '',
            checkin_time TEXT DEFAULT '20:00',
            reminder_time TEXT DEFAULT '20:30',
            consent_confirmed INTEGER DEFAULT 0,
            reminder_enabled INTEGER DEFAULT 1,
            last_reminder_date TEXT DEFAULT '',
            last_reminder_at TEXT DEFAULT ''
        )
    """)

    cur.execute("PRAGMA table_info(initial_screenings)")
    cols = {r[1] for r in cur.fetchall()}
    if "continuous_management" not in cols:
        cur.execute("ALTER TABLE initial_screenings ADD COLUMN continuous_management INTEGER DEFAULT 0")
    if "management_source" not in cols:
        cur.execute("ALTER TABLE initial_screenings ADD COLUMN management_source TEXT DEFAULT ''")

    # 기존 체크인/선별 학생 자동 등록
    cur.execute("""
        INSERT OR IGNORE INTO students(student_id, student_name, active)
        SELECT DISTINCT student_id, '', 1 FROM checkins
        WHERE TRIM(student_id) != ''
    """)
    cur.execute("""
        INSERT OR IGNORE INTO students(student_id, student_name, active)
        SELECT DISTINCT student_id, '', 1 FROM initial_screenings
        WHERE TRIM(student_id) != ''
    """)

    conn.commit()
    conn.close()

def load_table(query):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def mark_screening_reviewed(record_id, note):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE initial_screenings
        SET reviewer_checked=1, reviewer_note=?
        WHERE id=?
    """, (note, int(record_id)))
    conn.commit()
    conn.close()

def set_management(record_id, selected, source="전문가 추가"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE initial_screenings
        SET continuous_management=?, management_source=?
        WHERE id=?
    """, (1 if selected else 0, source if selected else "", int(record_id)))
    conn.commit()
    conn.close()

def apply_rf_recommendations(record_ids):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 기존 RF 추천은 재설정하되 전문가 직접 추가 대상은 유지
    cur.execute("""
        UPDATE initial_screenings
        SET continuous_management=0, management_source=''
        WHERE management_source='RF 추천'
    """)

    for rid in record_ids:
        cur.execute("""
            UPDATE initial_screenings
            SET continuous_management=1, management_source='RF 추천'
            WHERE id=? AND COALESCE(management_source,'')!='전문가 추가'
        """, (int(rid),))

    conn.commit()
    conn.close()

def load_management_contacts():
    return load_table("""
        SELECT * FROM management_contacts
        ORDER BY student_id
    """)

def save_management_contact(student_id, phone, checkin_time, reminder_time,
                            consent_confirmed, reminder_enabled):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO management_contacts (
            student_id, phone, checkin_time, reminder_time,
            consent_confirmed, reminder_enabled
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            phone=excluded.phone,
            checkin_time=excluded.checkin_time,
            reminder_time=excluded.reminder_time,
            consent_confirmed=excluded.consent_confirmed,
            reminder_enabled=excluded.reminder_enabled
    """, (
        student_id,
        phone.strip(),
        checkin_time,
        reminder_time,
        1 if consent_confirmed else 0,
        1 if reminder_enabled else 0
    ))
    conn.commit()
    conn.close()

def record_reminder_sent(student_id):
    now = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE management_contacts
        SET last_reminder_date=?,
            last_reminder_at=?
        WHERE student_id=?
    """, (
        now.strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d %H:%M:%S"),
        student_id
    ))
    conn.commit()
    conn.close()

def mask_phone(phone):
    phone = str(phone or "").strip()
    if not phone:
        return "미등록"
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) >= 10:
        return f"{digits[:3]}-****-{digits[-4:]}"
    if len(digits) >= 7:
        return f"{digits[:3]}-***-{digits[-4:]}"
    return "등록됨"

def parse_hhmm(value, default_h=20, default_m=0):
    try:
        h, m = str(value).split(":")
        return time(int(h), int(m))
    except Exception:
        return time(default_h, default_m)

def load_safety_plans():
    return load_table("""
        SELECT * FROM safety_plans
        ORDER BY datetime(updated_at) DESC, id DESC
    """)

def save_safety_plan(student_id, warning_signs, coping_strategies,
                     social_supports, professional_supports, safe_environment):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO safety_plans (
            student_id, warning_signs, coping_strategies,
            social_supports, professional_supports, safe_environment,
            updated_at, plan_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, '작성 완료')
        ON CONFLICT(student_id) DO UPDATE SET
            warning_signs=excluded.warning_signs,
            coping_strategies=excluded.coping_strategies,
            social_supports=excluded.social_supports,
            professional_supports=excluded.professional_supports,
            safe_environment=excluded.safe_environment,
            updated_at=excluded.updated_at,
            plan_status='작성 완료'
    """, (
        student_id, warning_signs, coping_strategies,
        social_supports, professional_supports, safe_environment, now
    ))
    conn.commit()
    conn.close()

def mark_checkin_checked(record_id, note):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE checkins
        SET teacher_checked=1, teacher_note=?
        WHERE id=?
    """, (note, int(record_id)))
    conn.commit()
    conn.close()

init_db()

screenings = load_table("""
    SELECT * FROM initial_screenings
    ORDER BY datetime(timestamp) DESC, id DESC
""")
checkins = load_table("""
    SELECT * FROM checkins
    ORDER BY datetime(timestamp) DESC, id DESC
""")
students = load_table("""
    SELECT student_id, student_name, active FROM students
    WHERE active=1 ORDER BY student_id
""")
safety_plans = load_safety_plans()
management_contacts = load_management_contacts()

# 학생별 최신 초기 선별 1건
if screenings.empty:
    latest = pd.DataFrame()
else:
    latest = (
        screenings.sort_values(["student_id","timestamp","id"], ascending=[True,False,False])
        .groupby("student_id", as_index=False)
        .first()
    )

# ---------------- RF 상대 순위 ----------------
def add_rank_info(df):
    if df.empty:
        return df.copy()

    r = df.sort_values(
        ["predicted_probability","timestamp","id"],
        ascending=[False,False,False]
    ).reset_index(drop=True)

    n = len(r)
    r["rf_rank"] = range(1, n+1)
    r["top_percent"] = r["rf_rank"] / n * 100

    def guide(p):
        if p <= 1:
            return "3단계 · 최우선 검토"
        if p <= 5:
            return "2단계 · 우선 검토"
        if p <= 10:
            return "1단계 · 관심 검토"
        return "일반 범위"

    r["rf_guide"] = r["top_percent"].apply(guide)
    return r

ranked = add_rank_info(latest)
managed = ranked[ranked["continuous_management"] == 1].copy() if not ranked.empty else pd.DataFrame()

# ---------------- 체크인 변화 ----------------
def mood_score(v):
    return {"🙂 괜찮아요":0, "😐 조금 힘들어요":1, "😟 많이 힘들어요":2}.get(v,0)

def safety_score(v):
    return {"아니요":0, "조금 그래요":1, "네":2}.get(v,0)

def help_score(v):
    return {
        "지금은 필요하지 않아요":0,
        "친구에게 연락하고 싶어요":1,
        "선생님·보호자 등 성인의 도움이 필요해요":2
    }.get(v,0)

def compare_change(cur, prev):
    if prev is None:
        return "비교 기록 없음"
    changes=[]
    if mood_score(cur["mood"]) > mood_score(prev["mood"]):
        changes.append("기분 악화")
    if safety_score(cur["safety"]) > safety_score(prev["safety"]):
        changes.append("안전감 악화")
    if cur["safety_plan"]=="필요했지만 사용하지 않았어요" and prev["safety_plan"]!="필요했지만 사용하지 않았어요":
        changes.append("Safety Plan 미사용 새로 발생")
    if help_score(cur["help_request"]) > help_score(prev["help_request"]):
        changes.append("도움 요청 수준 증가")
    return " · ".join(changes) if changes else "뚜렷한 악화 변화 없음"

# ---------------- STYLE ----------------
st.markdown("""
<style>
html, body, [class*="css"] {font-family:"Malgun Gothic","맑은 고딕",sans-serif;}
h1,h2,h3 {color:#173B6C;}
.block-container {padding-top:1.2rem; padding-bottom:2rem;}
.note-box {
 background:#EEF5FB; border-left:5px solid #2F75B5; border-radius:10px;
 padding:12px 16px; margin:8px 0 16px 0; line-height:1.65;
}
.warn-box {
 background:#FFF7E8; border-left:5px solid #ED7D31; border-radius:10px;
 padding:12px 16px; margin:8px 0 16px 0; line-height:1.65;
}
</style>
""", unsafe_allow_html=True)

st.title("🧑‍🏫 교사용 학생 안전관리")

st.markdown("""
<div class="note-box">
<b>기본 원칙</b><br>
전교생의 초기 선별 응답을 확인한 뒤 RF가 상대적 검토 우선순위를 제안합니다.
학교는 실제 관리 가능한 범위를 선택하고, 전문가 그룹은 RF 추천 범위 밖의 학생도 직접 지속 관리 대상에 추가할 수 있습니다.
</div>
""", unsafe_allow_html=True)

rf_count = (managed["management_source"]=="RF 추천").sum() if not managed.empty else 0
expert_count = (managed["management_source"]=="전문가 추가").sum() if not managed.empty else 0

tab1, tab2 = st.tabs(["🔎 초기 선별 관리", "🛡️ 지속 안전관리"])

# ==========================================================
# TAB 1
# ==========================================================
with tab1:
    if ranked.empty:
        st.info("아직 초기 선별 설문이 제출되지 않았습니다.")
    else:
        st.markdown("### 지속 안전 관리 규모 선택")
        option = st.selectbox(
            "지속 안전관리 RF 추천 범위",
            ["상위 1%","상위 3%","상위 5%","상위 10%","직접 입력"]
        )

        if option == "직접 입력":
            pct = st.number_input(
                "상위 비율(%)", min_value=0.1, max_value=100.0,
                value=1.0, step=0.1
            )
        else:
            pct = float(option.replace("상위 ","").replace("%",""))

        n_total = len(ranked)
        n_rec = max(1, math.ceil(n_total*pct/100))
        ids = ranked.head(n_rec)["id"].tolist()

        st.info(
            f"현재 선별 완료 {n_total:,}명 기준 → 상위 {pct:g}% = 약 {n_rec:,}명. "
            "이 선택은 학교의 관리 역량에 따른 운영 범위이며, 나머지 학생이 안전하다는 의미는 아닙니다."
        )

        if st.button(
            f"상위 {pct:g}% ({n_rec:,}명)을 RF 추천 대상으로 반영",
            type="primary", use_container_width=True
        ):
            apply_rf_recommendations(ids)
            st.success(f"RF 추천 대상 {n_rec:,}명을 반영했습니다.")
            st.rerun()

        st.divider()
        st.markdown("### 전교생 선별 결과")

        table = ranked[[
            "student_id","predicted_probability","rf_rank",
            "top_percent","rf_guide","continuous_management","management_source"
        ]].copy()
        table["predicted_probability"]=(table["predicted_probability"]*100).round(1).astype(str)+"%"
        table["top_percent"]=table["top_percent"].round(1).astype(str)+"%"
        table["continuous_management"]=table["continuous_management"].map({0:"미포함",1:"포함"})
        table["management_source"]=table["management_source"].replace("","-")
        table.columns=[
            "학생 ID","RF 예측값","RF 순위","상위 비율",
            "3단계 안내","지속 관리","선정 경로"
        ]
        st.dataframe(table, use_container_width=True, hide_index=True, height=340)

        st.caption(
            "※ RF 3단계 안내: 3단계(최우선 검토)=상위 1% 이내 · "
            "2단계(우선 검토)=상위 1% 초과~5% 이내 · "
            "1단계(관심 검토)=상위 5% 초과~10% 이내. "
            "이는 임상적 위험등급이 아니라 전교생 내 RF 예측값의 상대적 순위에 따른 검토 우선순위 안내입니다."
        )

        st.divider()
        st.markdown("### 학생별 응답 확인 및 전문가 추가 선정")

        sid = st.selectbox("학생 선택", ranked["student_id"].tolist())
        sr = ranked[ranked["student_id"]==sid].iloc[0]

        # 사용자가 요청한 순서: 15개 응답값 -> RF 추천 -> 전문가 검토
        st.markdown("#### ① 초기 선별 15개 응답값")

        labels = {
            "age_15_or_older":"연령",
            "female":"성별",
            "hunger":"식량 부족으로 심한 배고픔",
            "alcohol_use":"최근 음주",
            "loneliness":"지속적 외로움",
            "anxiety":"걱정으로 인한 수면 어려움",
            "physically_attacked":"신체적 공격 경험",
            "close_friends":"친한 친구 있음",
            "peer_support":"또래 지지",
            "parental_supervision":"부모 감독",
            "parental_attachment":"부모의 이해·관심",
            "parental_bonding":"부모와의 유대",
            "truancy":"무단결석",
            "physical_activity":"신체활동 기준 충족",
            "obesity":"비만 기준 해당"
        }

        rows=[]
        for col,label in labels.items():
            if col=="age_15_or_older":
                ans="15세 이상" if int(sr[col])==1 else "14세 이하"
            elif col=="female":
                ans="여성" if int(sr[col])==1 else "남성"
            else:
                ans="예" if int(sr[col])==1 else "아니오"
            rows.append([label,ans])

        st.dataframe(
            pd.DataFrame(rows, columns=["항목","응답"]),
            use_container_width=True, hide_index=True, height=300
        )

        st.markdown("#### ② 전문가 추가 선정")

        current_source = str(sr["management_source"] or "").strip()
        is_managed = int(sr["continuous_management"]) == 1

        if current_source == "RF 추천":
            st.success(
                "이 학생은 학교가 선택한 RF 추천 범위에 포함되어 이미 지속 안전관리 대상입니다."
            )
            st.caption(
                "전문가 추가 선정 버튼은 RF 추천 범위 밖 학생을 별도로 지속 관리 대상에 포함할 때 사용합니다."
            )
        elif current_source == "전문가 추가":
            st.success("이 학생은 전문가 그룹의 판단으로 지속 안전관리 대상에 추가되어 있습니다.")

            expert_note = st.text_area(
                "전문가 추가 선정 사유 / 메모",
                value=sr["reviewer_note"] if sr["reviewer_note"] else "",
                height=80,
                key=f"expert_note_{int(sr['id'])}"
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "선정 메모 저장",
                    use_container_width=True,
                    key=f"save_expert_{int(sr['id'])}"
                ):
                    mark_screening_reviewed(sr["id"], expert_note)
                    st.success("전문가 추가 선정 메모를 저장했습니다.")
                    st.rerun()

            with c2:
                if st.button(
                    "전문가 추가 대상에서 해제",
                    use_container_width=True,
                    key=f"remove_expert_{int(sr['id'])}"
                ):
                    set_management(sr["id"], False)
                    st.success("전문가 추가 대상을 해제했습니다.")
                    st.rerun()
        else:
            st.info(
                "이 학생은 현재 학교가 선택한 RF 추천 범위에는 포함되지 않았습니다. "
                "보건교사·상담교사·담임교사 등 전문가 그룹의 직접 관찰과 판단에 따라 "
                "필요하면 지속 안전관리 대상에 추가할 수 있습니다."
            )

            expert_note = st.text_area(
                "전문가 추가 선정 사유 / 메모",
                value=sr["reviewer_note"] if sr["reviewer_note"] else "",
                height=80,
                placeholder="예: 담임교사 관찰, 상담 기록, 보건실 방문 내용 등",
                key=f"expert_note_{int(sr['id'])}"
            )

            if st.button(
                "지속 안전관리 대상에 추가",
                type="primary",
                use_container_width=True,
                key=f"add_expert_{int(sr['id'])}"
            ):
                mark_screening_reviewed(sr["id"], expert_note)
                set_management(sr["id"], True, "전문가 추가")
                st.success("전문가 판단으로 지속 안전관리 대상에 추가했습니다.")
                st.rerun()

        st.caption(
            "※ 전교생의 RF 예측값과 3단계 안내는 위 선별 결과표에서 계속 확인할 수 있으며, "
            "전문가 추가 선정은 RF 추천 여부와 별개로 적용됩니다."
        )

# ==========================================================
# TAB 2
# ==========================================================
with tab2:
    st.subheader("지속 안전관리 대상")
    st.caption(
        "학교가 선택한 RF 추천 대상과 전문가 그룹이 추가한 학생을 대상으로 "
        "Safety Plan, 30초 체크인, 상태 변화, 후속 조치를 연계합니다."
    )

    if managed.empty:
        st.info("아직 지속 안전관리 대상이 없습니다.")
    else:
        # --------------------------------------------------
        # KPI: 지속 안전관리 탭에서는 실제 운영 현황을 빠르게 확인
        # --------------------------------------------------
        managed_ids = set(managed["student_id"].astype(str))

        if checkins.empty:
            managed_checkins = pd.DataFrame()
        else:
            managed_checkins = checkins[
                checkins["student_id"].astype(str).isin(managed_ids)
            ].copy()

        today = datetime.now().strftime("%Y-%m-%d")
        if managed_checkins.empty:
            today_checkins = pd.DataFrame()
            today_done = 0
            quick_need = 0
            change_need = 0
        else:
            today_checkins = managed_checkins[
                managed_checkins["timestamp"].astype(str).str[:10] == today
            ].copy()
            today_done = today_checkins["student_id"].nunique()

            latest_checkin_rows = (
                managed_checkins
                .sort_values(["student_id", "timestamp", "id"],
                             ascending=[True, False, False])
                .groupby("student_id", as_index=False)
                .first()
            )

            quick_need = (
                (
                    (latest_checkin_rows["monitoring_status"] == "빠른 확인 필요")
                    & (latest_checkin_rows["teacher_checked"] == 0)
                ).sum()
            )

            # 학생별 최근 2회 기록을 비교하여 변화 신호 집계
            change_need = 0
            for sid in managed_ids:
                g = (
                    managed_checkins[
                        managed_checkins["student_id"].astype(str) == str(sid)
                    ]
                    .sort_values("timestamp", ascending=False)
                    .reset_index(drop=True)
                )
                if len(g) >= 2:
                    sig = compare_change(g.iloc[0], g.iloc[1])
                    if any(x in sig for x in ["악화", "미사용", "증가"]):
                        if int(g.iloc[0]["teacher_checked"]) == 0:
                            change_need += 1

        plan_done = 0
        if not safety_plans.empty:
            plan_done = safety_plans[
                safety_plans["student_id"].astype(str).isin(managed_ids)
                & (safety_plans["plan_status"] == "작성 완료")
            ]["student_id"].nunique()

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("지속 관리 대상", f"{len(managed):,}명")
        k2.metric("Safety Plan 작성", f"{plan_done:,}명")
        k3.metric("오늘 체크인 완료", f"{today_done:,}명")
        k4.metric("빠른 확인 필요", f"{quick_need:,}명")
        k5.metric("상태 변화 확인", f"{change_need:,}명")

        st.caption(
            f"대상 구성: RF 추천 {rf_count:,}명 + 전문가 추가 {expert_count:,}명"
        )

        # --------------------------------------------------
        # 지속 관리 대상자 목록 유지
        # --------------------------------------------------
        st.markdown("### 지속 관리 대상자")

        mt = managed[
            ["student_id", "predicted_probability", "rf_guide", "management_source"]
        ].copy()

        mt["predicted_probability"] = (
            mt["predicted_probability"] * 100
        ).round(1).astype(str) + "%"

        # 지속관리 연락처/리마인드 설정
        contact_map = {}
        if not management_contacts.empty:
            contact_map = {
                str(r["student_id"]): r
                for _, r in management_contacts.iterrows()
            }

        # Safety Plan 상태
        plan_map = {}
        if not safety_plans.empty:
            plan_map = dict(zip(
                safety_plans["student_id"].astype(str),
                safety_plans["plan_status"]
            ))

        # 오늘 체크인 상태
        today_count_map = {}
        if not today_checkins.empty:
            today_count_map = (
                today_checkins.groupby("student_id").size().to_dict()
            )

        mt["Safety Plan"] = mt["student_id"].astype(str).map(
            lambda x: plan_map.get(x, "미작성")
        )
        mt["오늘 체크인"] = mt["student_id"].astype(str).map(
            lambda x: (
                f"{int(today_count_map.get(x, 0))}회 완료"
                if int(today_count_map.get(x, 0)) > 0
                else "미응답"
            )
        )

        mt["연락처"] = mt["student_id"].astype(str).map(
            lambda x: mask_phone(
                contact_map.get(x, {}).get("phone", "")
                if isinstance(contact_map.get(x, {}), dict)
                else (contact_map[x]["phone"] if x in contact_map else "")
            )
        )

        def reminder_state_for_student(sid):
            sid = str(sid)
            if sid not in contact_map:
                return "설정 필요"

            row = contact_map[sid]
            enabled = int(row["reminder_enabled"]) == 1
            consent = int(row["consent_confirmed"]) == 1
            phone = str(row["phone"] or "").strip()

            if not enabled:
                return "미사용"
            if not phone or not consent:
                return "설정 필요"

            if int(today_count_map.get(sid, 0)) > 0:
                return "체크인 완료"

            now_dt = datetime.now()
            reminder_t = parse_hhmm(row["reminder_time"], 20, 30)
            reminder_dt = datetime.combine(now_dt.date(), reminder_t)

            if str(row["last_reminder_date"] or "") == now_dt.strftime("%Y-%m-%d"):
                return "리마인드 발송 완료"

            if now_dt >= reminder_dt:
                return "리마인드 발송 필요"

            return "대기"

        mt["리마인드"] = mt["student_id"].astype(str).map(reminder_state_for_student)

        mt.columns = [
            "학생 ID", "RF 예측값", "3단계 안내", "선정 경로",
            "Safety Plan", "오늘 체크인", "연락처", "리마인드"
        ]

        st.dataframe(
            mt,
            use_container_width=True,
            hide_index=True,
            height=min(300, 38 + 35 * max(len(mt), 1))
        )

        st.divider()

        # --------------------------------------------------
        # 학생 선택
        # --------------------------------------------------
        sid2 = st.selectbox(
            "관리 학생 선택",
            managed["student_id"].tolist(),
            key="managed_student"
        )

        selected_row = managed[
            managed["student_id"] == sid2
        ].iloc[0]

        st.caption(
            f"{sid2} · 선정 경로: {selected_row['management_source']} · "
            f"RF 3단계 안내: {selected_row['rf_guide']}"
        )

        # --------------------------------------------------
        # 지속관리 대상자 전용 연락/리마인드 설정
        # --------------------------------------------------
        with st.expander("📱 지속관리 연락 및 체크인 설정", expanded=False):
            existing_contact = management_contacts[
                management_contacts["student_id"].astype(str) == str(sid2)
            ]

            if existing_contact.empty:
                c_phone = ""
                c_checkin = "20:00"
                c_reminder = "20:30"
                c_consent = False
                c_enabled = True
                last_reminder_at = ""
            else:
                cr = existing_contact.iloc[0]
                c_phone = str(cr["phone"] or "")
                c_checkin = str(cr["checkin_time"] or "20:00")
                c_reminder = str(cr["reminder_time"] or "20:30")
                c_consent = int(cr["consent_confirmed"]) == 1
                c_enabled = int(cr["reminder_enabled"]) == 1
                last_reminder_at = str(cr["last_reminder_at"] or "")

            st.caption(
                "연락처는 전교생이 아니라 지속 안전관리 대상으로 선정된 학생에게만 등록합니다. "
                "체크인 안내 및 안전관리 연락 목적에 한해 사용하는 것을 전제로 합니다."
            )

            cc1, cc2, cc3 = st.columns([1.4, 1, 1])

            with cc1:
                phone = st.text_input(
                    "학생 연락처",
                    value=c_phone,
                    placeholder="예: 010-1234-5678",
                    key=f"phone_{sid2}"
                )

            with cc2:
                checkin_time_value = st.text_input(
                    "체크인 예정시간",
                    value=c_checkin,
                    placeholder="20:00",
                    key=f"checkin_time_{sid2}"
                )

            with cc3:
                reminder_time_value = st.text_input(
                    "미응답 리마인드 시간",
                    value=c_reminder,
                    placeholder="20:30",
                    key=f"reminder_time_{sid2}"
                )

            consent_confirmed = st.checkbox(
                "연락처 수집·체크인 안내 및 미응답 리마인드 사용에 대한 사전 안내/동의 확인",
                value=c_consent,
                key=f"consent_{sid2}"
            )

            reminder_enabled = st.checkbox(
                "미응답 리마인드 사용",
                value=c_enabled,
                key=f"reminder_enabled_{sid2}"
            )

            if st.button(
                "연락 및 체크인 설정 저장",
                use_container_width=True,
                key=f"save_contact_{sid2}"
            ):
                save_management_contact(
                    sid2,
                    phone,
                    checkin_time_value,
                    reminder_time_value,
                    consent_confirmed,
                    reminder_enabled
                )
                st.success("지속관리 연락 및 체크인 설정을 저장했습니다.")
                st.rerun()

            if last_reminder_at:
                st.caption(f"최근 리마인드 기록: {last_reminder_at}")

            st.caption(
                "※ 실제 SMS 발송 API는 아직 연결하지 않았습니다. "
                "현재 프로토타입에서는 발송 필요 대상을 식별하고 발송 기록을 남기는 기능까지만 구현합니다."
            )

        # --------------------------------------------------
        # 4개 하위 관리 탭
        # --------------------------------------------------
        sp_tab, check_tab, change_tab, follow_tab = st.tabs(
            ["📋 Safety Plan", "📝 오늘의 체크인", "📈 상태 변화", "🤝 후속조치"]
        )

        # ==================================================
        # 1. SAFETY PLAN
        # ==================================================
        with sp_tab:
            st.markdown("### 개인별 Safety Plan")

            existing = safety_plans[
                safety_plans["student_id"].astype(str) == str(sid2)
            ]

            if existing.empty:
                sp = None
                st.info(
                    "아직 작성된 Safety Plan이 없습니다. "
                    "학생과 담당자가 함께 계획을 작성해 주세요."
                )
            else:
                sp = existing.iloc[0]
                st.success(
                    f"Safety Plan 작성 완료 · 최근 수정 {sp['updated_at']}"
                )

            warning_signs = st.text_area(
                "1. 내가 알아차릴 수 있는 경고 신호",
                value="" if sp is None else str(sp["warning_signs"] or ""),
                height=85,
                placeholder="학생이 스스로 알아차릴 수 있는 생각, 감정, 상황 등을 기록",
                key=f"sp_warning_{sid2}"
            )

            coping_strategies = st.text_area(
                "2. 혼자서 해볼 수 있는 대처 방법",
                value="" if sp is None else str(sp["coping_strategies"] or ""),
                height=85,
                placeholder="학생에게 도움이 되는 개인적 대처 방법을 기록",
                key=f"sp_coping_{sid2}"
            )

            social_supports = st.text_area(
                "3. 연락하거나 함께 있을 수 있는 사람·사회적 지지",
                value="" if sp is None else str(sp["social_supports"] or ""),
                height=85,
                placeholder="친구, 가족 등 학생이 도움을 요청할 수 있는 사람",
                key=f"sp_social_{sid2}"
            )

            professional_supports = st.text_area(
                "4. 도움을 요청할 수 있는 전문가·기관",
                value="" if sp is None else str(sp["professional_supports"] or ""),
                height=85,
                placeholder="보건교사, 상담교사, 보호자, 전문기관 등",
                key=f"sp_prof_{sid2}"
            )

            safe_environment = st.text_area(
                "5. 더 안전한 환경을 만들기 위한 계획",
                value="" if sp is None else str(sp["safe_environment"] or ""),
                height=85,
                placeholder="학생의 안전을 높이기 위해 함께 정한 환경적 조치",
                key=f"sp_safe_{sid2}"
            )

            if st.button(
                "Safety Plan 저장 / 수정",
                type="primary",
                use_container_width=True,
                key=f"save_sp_{sid2}"
            ):
                save_safety_plan(
                    sid2,
                    warning_signs,
                    coping_strategies,
                    social_supports,
                    professional_supports,
                    safe_environment
                )
                st.success("Safety Plan을 저장했습니다.")
                st.rerun()

            st.caption(
                "※ Safety Plan은 학생과 담당자가 함께 검토·수정하는 지원 계획이며, "
                "자동 위험 판정 도구가 아닙니다."
            )

        # ==================================================
        # 2. 오늘의 체크인
        # ==================================================
        with check_tab:
            st.markdown("### 오늘의 30초 체크인")

            sdf = (
                checkins[checkins["student_id"].astype(str) == str(sid2)]
                .sort_values("timestamp", ascending=False)
                .reset_index(drop=True)
            )

            today_sdf = (
                sdf[sdf["timestamp"].astype(str).str[:10] == today]
                if not sdf.empty else pd.DataFrame()
            )

            if today_sdf.empty:
                st.warning("오늘 제출된 30초 체크인이 없습니다.")
                st.caption(
                    "미응답은 위험 판정이 아니라 현재 상태를 확인할 수 없음을 의미합니다."
                )

                contact_row = management_contacts[
                    management_contacts["student_id"].astype(str) == str(sid2)
                ]

                if contact_row.empty:
                    st.info(
                        "리마인드 기능을 사용하려면 위의 '지속관리 연락 및 체크인 설정'에서 "
                        "연락처와 시간을 먼저 등록해 주세요."
                    )
                else:
                    cr = contact_row.iloc[0]
                    phone = str(cr["phone"] or "").strip()
                    consent_ok = int(cr["consent_confirmed"]) == 1
                    enabled = int(cr["reminder_enabled"]) == 1
                    reminder_t = parse_hhmm(cr["reminder_time"], 20, 30)
                    now_dt = datetime.now()
                    reminder_dt = datetime.combine(now_dt.date(), reminder_t)
                    sent_today = (
                        str(cr["last_reminder_date"] or "")
                        == now_dt.strftime("%Y-%m-%d")
                    )

                    r1, r2, r3 = st.columns(3)
                    r1.metric("등록 연락처", mask_phone(phone))
                    r2.metric("체크인 예정", str(cr["checkin_time"] or "20:00"))
                    r3.metric("리마인드", str(cr["reminder_time"] or "20:30"))

                    if not enabled:
                        st.info("이 학생은 미응답 리마인드 기능을 사용하지 않도록 설정되어 있습니다.")
                    elif not phone:
                        st.warning("학생 연락처가 등록되지 않았습니다.")
                    elif not consent_ok:
                        st.warning("사전 안내/동의 확인이 완료되지 않아 리마인드를 사용할 수 없습니다.")
                    elif sent_today:
                        st.success(
                            f"오늘 리마인드 발송 기록이 있습니다: {cr['last_reminder_at']}"
                        )
                    elif now_dt < reminder_dt:
                        st.info(
                            f"리마인드 예정시간({cr['reminder_time']}) 전입니다. "
                            "예정시간 이후에도 미응답이면 발송 필요 상태로 전환됩니다."
                        )
                    else:
                        st.warning("리마인드 발송 필요")
                        st.markdown(
                            "> 오늘 체크인이 아직 확인되지 않았습니다. "
                            "괜찮을 때 오늘의 상태를 간단히 알려주세요."
                        )

                        if st.button(
                            "리마인드 발송 완료로 기록",
                            type="primary",
                            use_container_width=True,
                            key=f"reminder_sent_{sid2}"
                        ):
                            record_reminder_sent(sid2)
                            st.success("리마인드 발송 완료 시각을 기록했습니다.")
                            st.rerun()

            else:
                st.success(f"오늘 체크인 {len(today_sdf)}회 완료")

                today_view = today_sdf[
                    [
                        "timestamp", "mood", "safety",
                        "safety_plan", "help_request", "monitoring_status"
                    ]
                ].copy()

                today_view.columns = [
                    "시간", "기분", "안전감",
                    "Safety Plan 사용", "도움 요청", "내부 확인 상태"
                ]

                st.dataframe(
                    today_view,
                    use_container_width=True,
                    hide_index=True
                )

            if not sdf.empty:
                st.caption(f"누적 체크인 {len(sdf)}건")

        # ==================================================
        # 3. 상태 변화
        # ==================================================
        with change_tab:
            st.markdown("### 최근 상태 변화")

            sdf = (
                checkins[checkins["student_id"].astype(str) == str(sid2)]
                .sort_values("timestamp", ascending=False)
                .reset_index(drop=True)
            )

            if len(sdf) < 2:
                st.info("비교할 체크인 기록이 충분하지 않습니다.")
            else:
                cur = sdf.iloc[0]
                prev = sdf.iloc[1]
                signal = compare_change(cur, prev)

                if any(x in signal for x in ["악화", "미사용", "증가"]):
                    st.warning(f"직전 대비 변화: {signal}")
                else:
                    st.info(f"직전 대비 변화: {signal}")

                comparison = pd.DataFrame({
                    "항목": ["기분", "안전감", "Safety Plan", "도움 요청"],
                    "직전": [
                        prev["mood"], prev["safety"],
                        prev["safety_plan"], prev["help_request"]
                    ],
                    "현재": [
                        cur["mood"], cur["safety"],
                        cur["safety_plan"], cur["help_request"]
                    ]
                })

                st.dataframe(
                    comparison,
                    use_container_width=True,
                    hide_index=True
                )

                with st.expander("최근 체크인 이력 보기"):
                    hist = sdf[
                        [
                            "timestamp", "mood", "safety",
                            "safety_plan", "help_request",
                            "monitoring_status", "teacher_checked"
                        ]
                    ].copy()

                    hist.columns = [
                        "시간", "기분", "안전감", "Safety Plan",
                        "도움 요청", "내부 상태", "담당자 확인"
                    ]
                    hist["담당자 확인"] = hist["담당자 확인"].map(
                        {0: "미확인", 1: "확인 완료"}
                    )

                    st.dataframe(
                        hist,
                        use_container_width=True,
                        hide_index=True,
                        height=260
                    )

        # ==================================================
        # 4. 후속조치
        # ==================================================
        with follow_tab:
            st.markdown("### 전문가 확인 및 후속조치")

            sdf = (
                checkins[checkins["student_id"].astype(str) == str(sid2)]
                .sort_values("timestamp", ascending=False)
                .reset_index(drop=True)
            )

            if sdf.empty:
                st.info(
                    "아직 체크인 기록이 없어 후속조치를 연결할 수 없습니다."
                )
            else:
                cur = sdf.iloc[0]

                f1, f2 = st.columns(2)
                f1.metric("최근 체크인", str(cur["timestamp"])[5:16])
                f2.metric(
                    "담당자 확인",
                    "확인 완료"
                    if int(cur["teacher_checked"]) == 1
                    else "미확인"
                )

                st.write(
                    f"**최근 내부 확인 상태:** {cur['monitoring_status']}"
                )

                follow = st.text_area(
                    "확인 내용 / 후속 조치",
                    value=cur["teacher_note"] if cur["teacher_note"] else "",
                    height=110,
                    placeholder="예: 학생과 직접 확인 / 상담교사 연계 / 보호자 연락 / 재확인 예정",
                    key=f"follow_{int(cur['id'])}"
                )

                if st.button(
                    "학생 상태 확인 완료",
                    type="primary",
                    use_container_width=True,
                    key=f"checked_{int(cur['id'])}"
                ):
                    mark_checkin_checked(cur["id"], follow)
                    st.success("학생 상태 확인 내용을 저장했습니다.")
                    st.rerun()

                st.caption(
                    "※ '확인 완료'는 학생이 안전하다는 판정이 아니라 "
                    "담당자가 학생 상태를 직접 확인하고 후속조치를 기록했다는 의미입니다."
                )
