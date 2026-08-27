
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, time

DB_PATH = "checkin_data.db"
CHECKIN_CUTOFF_HOUR = 20
CHECKIN_CUTOFF_MINUTE = 0

st.set_page_config(
    page_title="교사용 학생 안전관리 Dashboard",
    page_icon="🧑‍🏫",
    layout="wide"
)

# -------------------------------------------------
# DB
# -------------------------------------------------
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

    conn.commit()
    conn.close()

def load_checkins():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            id,
            timestamp,
            student_id,
            mood,
            safety,
            safety_plan,
            help_request,
            memo,
            monitoring_status,
            teacher_checked,
            teacher_note
        FROM checkins
        ORDER BY datetime(timestamp) DESC, id DESC
    """, conn)
    conn.close()
    return df

def load_students():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT student_id, student_name, active
        FROM students
        WHERE active = 1
        ORDER BY student_id
    """, conn)
    conn.close()
    return df

def sync_students_from_checkins():
    """
    체크인 기록에 학생 ID가 있으면 학생 명단에도 자동 등록한다.
    따라서 '최근 학생 상태에는 보이는데 등록 학생 수에는 빠지는' 불일치를 방지한다.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO students (student_id, student_name, active)
        SELECT DISTINCT student_id, '', 1
        FROM checkins
        WHERE student_id IS NOT NULL
          AND TRIM(student_id) != ''
    """)
    conn.commit()
    conn.close()

def add_student(student_id, student_name=""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO students (student_id, student_name, active)
        VALUES (
            ?,
            CASE
                WHEN ? != '' THEN ?
                ELSE COALESCE(
                    (SELECT student_name FROM students WHERE student_id = ?),
                    ''
                )
            END,
            1
        )
    """, (
        student_id.strip(),
        student_name.strip(),
        student_name.strip(),
        student_id.strip()
    ))
    conn.commit()
    conn.close()

def mark_checked(record_id, note):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE checkins
        SET teacher_checked = 1,
            teacher_note = ?
        WHERE id = ?
    """, (note, record_id))
    conn.commit()
    conn.close()

init_db()
sync_students_from_checkins()

# -------------------------------------------------
# 내부 상태 / 변화 비교
# -------------------------------------------------
def status_priority(status):
    return {
        "빠른 확인 필요": 1,
        "추가 확인 필요": 2,
        "또래 연결 요청": 3,
        "기록 완료": 4
    }.get(status, 99)

def mood_score(v):
    return {
        "🙂 괜찮아요": 0,
        "😐 조금 힘들어요": 1,
        "😟 많이 힘들어요": 2
    }.get(v, 0)

def safety_score(v):
    return {
        "아니요": 0,
        "조금 그래요": 1,
        "네": 2
    }.get(v, 0)

def help_score(v):
    return {
        "지금은 필요하지 않아요": 0,
        "친구에게 연락하고 싶어요": 1,
        "선생님·보호자 등 성인의 도움이 필요해요": 2
    }.get(v, 0)

def compare_change(current, previous):
    if previous is None:
        return "비교 기록 없음"

    changes = []

    if mood_score(current["mood"]) > mood_score(previous["mood"]):
        changes.append("기분 악화")

    if safety_score(current["safety"]) > safety_score(previous["safety"]):
        changes.append("안전감 악화")

    if (
        current["safety_plan"] == "필요했지만 사용하지 않았어요"
        and previous["safety_plan"] != "필요했지만 사용하지 않았어요"
    ):
        changes.append("Safety Plan 미사용 새로 발생")

    if help_score(current["help_request"]) > help_score(previous["help_request"]):
        changes.append("도움 요청 수준 증가")

    return " · ".join(changes) if changes else "뚜렷한 악화 변화 없음"

def build_latest_summary(df):
    if df.empty:
        return pd.DataFrame()

    rows = []

    for student_id, group in df.groupby("student_id"):
        g = group.sort_values("timestamp", ascending=False).reset_index(drop=True)
        current = g.iloc[0]
        previous = g.iloc[1] if len(g) >= 2 else None

        rows.append({
            "id": current["id"],
            "student_id": student_id,
            "timestamp": current["timestamp"],
            "monitoring_status": current["monitoring_status"],
            "teacher_checked": current["teacher_checked"],
            "change_signal": compare_change(current, previous),
            "priority": status_priority(current["monitoring_status"])
        })

    latest = pd.DataFrame(rows)
    return latest.sort_values(
        ["priority", "timestamp"],
        ascending=[True, False]
    )

def build_response_status(students_df, checkins_df):
    """
    학생별 오늘 체크인 횟수를 집계한다.
    체크인 횟수는 위험 증가를 의미하지 않으며 단순한 이용/모니터링 정보로 사용한다.
    """
    if students_df.empty:
        return pd.DataFrame()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    cutoff = datetime.combine(
        now.date(),
        time(CHECKIN_CUTOFF_HOUR, CHECKIN_CUTOFF_MINUTE)
    )

    if checkins_df.empty:
        today_counts = {}
    else:
        tmp = checkins_df.copy()
        tmp["date"] = tmp["timestamp"].astype(str).str[:10]
        today_tmp = tmp[tmp["date"] == today_str]

        today_counts = (
            today_tmp.groupby("student_id")
            .size()
            .to_dict()
        )

    rows = []
    for _, row in students_df.iterrows():
        sid = str(row["student_id"])
        count = int(today_counts.get(sid, 0))

        if count > 0:
            state = f"오늘 체크인 {count}회 완료"
        else:
            state = "미응답 확인 필요" if now >= cutoff else "체크인 대기"

        rows.append({
            "학생 ID": sid,
            "이름": row["student_name"],
            "오늘 체크인 횟수": count,
            "오늘 응답 상태": state
        })

    return pd.DataFrame(rows)

# -------------------------------------------------
# STYLE
# -------------------------------------------------
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
}
h1, h2, h3 { color: #173B6C; }

.rule-box {
    background: #EEF5FB;
    border-left: 5px solid #2F75B5;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 10px 0 18px 0;
    line-height: 1.6;
}

.change-box {
    background: #FFF7E8;
    border-left: 5px solid #ED7D31;
    border-radius: 10px;
    padding: 11px 14px;
    margin: 8px 0 14px 0;
    line-height: 1.6;
}

.missing-box {
    background: #FFF2F2;
    border-left: 5px solid #D9534F;
    border-radius: 10px;
    padding: 11px 14px;
    margin: 8px 0 14px 0;
    line-height: 1.6;
}

.selected-student {
    background: #F6F9FC;
    border: 1px solid #D9E3ED;
    border-radius: 12px;
    padding: 12px 16px;
    margin: 8px 0 14px 0;
    font-size: 16px;
}

.compact-note {
    color: #687789;
    font-size: 13px;
    margin-top: 2px;
}
</style>
""", unsafe_allow_html=True)

st.title("🧑‍🏫 교사용 학생 안전관리 Dashboard")

st.markdown("""
<div class="rule-box">
이 Dashboard는 학생의 자기보고만으로 위험을 확정하지 않습니다.<br>
최근 응답, 직전 대비 변화, 미응답 여부를 함께 보고
<b>사람이 우선 확인해야 할 학생을 놓치지 않도록 돕는 운영 도구</b>입니다.
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------
# 사이드바: 학생 명단 관리
# -------------------------------------------------
with st.sidebar:
    st.header("학생 명단 관리")

    sid = st.text_input("학생 ID 등록", placeholder="예: STU-001")
    sname = st.text_input("학생 이름(선택)", placeholder="예: 홍길동")

    if st.button("학생 등록", use_container_width=True):
        if sid.strip():
            add_student(sid, sname)
            st.success("학생 명단에 등록했습니다.")
            st.rerun()
        else:
            st.warning("학생 ID를 입력해 주세요.")

    st.divider()
    st.caption(
        "체크인을 제출한 학생은 자동으로 등록 학생 명단에 포함됩니다."
    )
    st.caption(
        f"프로토타입 기본 체크인 마감 시각: "
        f"{CHECKIN_CUTOFF_HOUR:02d}:{CHECKIN_CUTOFF_MINUTE:02d}"
    )

# -------------------------------------------------
# 데이터
# -------------------------------------------------
df = load_checkins()
students = load_students()
latest = build_latest_summary(df)
response_status = build_response_status(students, df)

today_unique_count = (
    (response_status["오늘 체크인 횟수"] > 0).sum()
    if not response_status.empty else 0
)

missing_count = (
    (response_status["오늘 응답 상태"] == "미응답 확인 필요").sum()
    if not response_status.empty else 0
)

# 상단의 '확인 필요' 지표는 현재 남아 있는 미확인 업무만 집계한다.
# 담당자가 '학생 상태 확인 완료'를 누르면 teacher_checked=1이 되어
# 해당 학생은 빠른 확인/상태 변화 확인 필요 건수에서 제외된다.
fast_count = (
    (
        (latest["monitoring_status"] == "빠른 확인 필요")
        & (latest["teacher_checked"] == 0)
    ).sum()
    if not latest.empty else 0
)

change_count = (
    (
        latest["change_signal"].str.contains("악화|미사용|증가", regex=True)
        & (latest["teacher_checked"] == 0)
    ).sum()
    if not latest.empty else 0
)

# -------------------------------------------------
# KPI: 의미가 직접 연결되는 값만 표시
# -------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("등록 학생", f"{len(students):,}명")
c2.metric("오늘 체크인 완료", f"{today_unique_count:,}명")
c3.metric("빠른 확인 필요", f"{fast_count:,}명", help="담당자 확인이 아직 완료되지 않은 학생만 집계합니다.")
c4.metric("상태 변화 확인 필요", f"{change_count:,}명", help="직전 대비 악화 신호가 있고 담당자 확인이 아직 완료되지 않은 학생만 집계합니다.")
c5.metric("오늘 미응답 확인 필요", f"{missing_count:,}명")

st.caption(
    f"누적 체크인 기록: {len(df):,}건 · "
    "누적 기록은 아래 학생 상세 화면의 '최근 체크인 흐름'에서 학생별로 확인합니다."
)

# -------------------------------------------------
# 1. 오늘의 응답 상태
# -------------------------------------------------
st.subheader("오늘의 체크인 응답 상태")

if students.empty:
    st.info("등록된 학생이 없습니다.")
else:
    if missing_count > 0:
        st.markdown(
            f"""
            <div class="missing-box">
            오늘 마감 시각 이후에도 응답하지 않은 학생이
            <b>{missing_count}명</b> 있습니다.<br>
            미응답은 위험 판정이 아니라
            <b>현재 상태를 확인할 수 없음</b>을 의미합니다.
            </div>
            """,
            unsafe_allow_html=True
        )

    # 체크인 횟수는 내부 집계에는 유지하되,
    # 화면에서는 '오늘 응답 상태' 문구에 이미 포함되므로 중복 열은 표시하지 않는다.
    response_display = response_status[
        ["학생 ID", "이름", "오늘 응답 상태"]
    ].copy()

    st.dataframe(
        response_display,
        use_container_width=True,
        hide_index=True
    )

st.divider()

# -------------------------------------------------
# 2. 오늘/최근 확인 목록
# -------------------------------------------------
st.subheader("학생 확인 목록")

if latest.empty:
    st.info("아직 저장된 체크인 기록이 없습니다.")
    st.stop()

summary = latest[
    [
        "student_id",
        "timestamp",
        "change_signal",
        "monitoring_status",
        "teacher_checked"
    ]
].copy()

summary.columns = [
    "학생 ID",
    "최근 체크인",
    "직전 대비 변화",
    "내부 확인 상태",
    "학생 상태 확인"
]

summary["학생 상태 확인"] = summary["학생 상태 확인"].map(
    {0: "미확인", 1: "확인 완료"}
)

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True
)

st.caption(
    "이 표는 학생별 '가장 최근 체크인 1건'만 보여줍니다. "
    "과거 기록은 아래 학생 상세 화면에서 확인합니다."
)

st.divider()

# -------------------------------------------------
# 3. 학생 상세
# -------------------------------------------------
st.subheader("학생 상세 확인")

student_options = latest["student_id"].tolist()
selected_student = st.selectbox(
    "확인할 학생 선택",
    student_options
)

student_df = (
    df[df["student_id"] == selected_student]
    .sort_values("timestamp", ascending=False)
    .reset_index(drop=True)
)

recent = student_df.iloc[0]
previous = student_df.iloc[1] if len(student_df) >= 2 else None
change_signal = compare_change(recent, previous)

student_name = ""
if not students.empty:
    match = students[students["student_id"] == selected_student]
    if not match.empty:
        student_name = str(match.iloc[0]["student_name"] or "").strip()

name_text = f" · {student_name}" if student_name else ""

st.markdown(
    f"""
    <div class="selected-student">
        <b>현재 확인 학생:</b> {selected_student}{name_text}
        &nbsp;&nbsp; | &nbsp;&nbsp;
        <b>최근 체크인:</b> {recent['timestamp']}
        &nbsp;&nbsp; | &nbsp;&nbsp;
        <b>내부 확인 상태:</b> {recent['monitoring_status']}
    </div>
    """,
    unsafe_allow_html=True
)

# -------------------------------------------------
# 3-1. 최근 체크인 흐름 먼저
# -------------------------------------------------
st.markdown("### 최근 체크인 흐름")
st.caption(
    f"{selected_student}{name_text} 학생의 누적 체크인 {len(student_df)}건입니다."
)

history = student_df[
    [
        "timestamp",
        "mood",
        "safety",
        "safety_plan",
        "help_request",
        "monitoring_status",
        "teacher_checked"
    ]
].copy()

history.columns = [
    "시간",
    "기분",
    "안전감",
    "Safety Plan",
    "도움 요청",
    "내부 상태",
    "학생 상태 확인"
]

history["학생 상태 확인"] = history["학생 상태 확인"].map(
    {0: "미확인", 1: "확인 완료"}
)

st.dataframe(
    history,
    use_container_width=True,
    hide_index=True
)

# -------------------------------------------------
# 3-2. 직전 대비 변화 - 필요 정보만
# -------------------------------------------------
st.markdown("### 직전 체크인과 비교")

st.markdown(
    f'<div class="change-box"><b>{change_signal}</b></div>',
    unsafe_allow_html=True
)

if previous is not None:
    comparison = pd.DataFrame({
        "항목": ["기분", "안전감", "Safety Plan", "도움 요청"],
        "직전 → 현재": [
            f"{previous['mood']}  →  {recent['mood']}",
            f"{previous['safety']}  →  {recent['safety']}",
            f"{previous['safety_plan']}  →  {recent['safety_plan']}",
            f"{previous['help_request']}  →  {recent['help_request']}"
        ]
    })

    st.dataframe(
        comparison,
        use_container_width=True,
        hide_index=True
    )
else:
    st.caption(
        "이 학생은 이전 체크인 기록이 없어 변화 비교를 할 수 없습니다."
    )

# -------------------------------------------------
# 3-3. 상태 확인 / 후속조치 메모는 맨 마지막에 간결하게
# -------------------------------------------------
st.markdown(f"### {selected_student}{name_text} 학생 상태 확인")

st.caption(
    "학생에게 실제로 연락하거나 상태를 확인한 뒤, "
    "필요한 후속 조치만 간단히 기록합니다."
)

note = st.text_area(
    "확인 내용 / 후속 조치 메모",
    value=recent["teacher_note"] if recent["teacher_note"] else "",
    height=85,
    placeholder="예: 학생과 통화함 / 담임교사에게 전달함 / 내일 상담 예정",
    key=f"note_{recent['id']}"
)

col_btn, col_space = st.columns([1, 2.2])

with col_btn:
    if st.button(
        "학생 상태 확인 완료",
        type="primary",
        use_container_width=True
    ):
        mark_checked(int(recent["id"]), note)
        st.success("학생 상태 확인 내용이 저장되었습니다.")
        st.rerun()

st.caption(
    "※ '학생 상태 확인 완료'는 학생이 안전하다는 판정이 아니라, "
    "담당자가 직접 확인했다는 업무 기록입니다."
)
