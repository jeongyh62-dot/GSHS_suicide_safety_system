
import streamlit as st
import sqlite3
from datetime import datetime

DB_PATH = "checkin_data.db"

st.set_page_config(
    page_title="오늘의 30초 체크인",
    page_icon="🛡️",
    layout="centered"
)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()

def classify_signal(mood, safety, safety_plan, help_request):
    if safety == "네" or help_request == "선생님·보호자 등 성인의 도움이 필요해요":
        return "빠른 확인 필요"

    if (
        mood == "😟 많이 힘들어요"
        or safety == "조금 그래요"
        or safety_plan == "필요했지만 사용하지 않았어요"
    ):
        return "추가 확인 필요"

    if help_request == "친구에게 연락하고 싶어요":
        return "또래 연결 요청"

    return "기록 완료"

def save_record(student_id, mood, safety, safety_plan, help_request, memo):
    status = classify_signal(mood, safety, safety_plan, help_request)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 체크인을 제출한 학생은 등록 학생 명단에도 자동 포함
    cur.execute("""
        INSERT OR IGNORE INTO students (
            student_id, student_name, active
        )
        VALUES (?, '', 1)
    """, (student_id.strip(),))

    cur.execute("""
        INSERT INTO checkins (
            timestamp, student_id, mood, safety,
            safety_plan, help_request, memo,
            monitoring_status, teacher_checked, teacher_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '')
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        student_id.strip(),
        mood,
        safety,
        safety_plan,
        help_request,
        memo,
        status
    ))

    conn.commit()
    conn.close()

init_db()

st.markdown("""
<style>
.block-container {
    max-width: 760px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}
html, body, [class*="css"] {
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
}
h1 {
    color: #173B6C;
    font-weight: 800;
}
h3 {
    color: #20344D;
    font-size: 1.22rem !important;
    margin-top: 1.35rem !important;
}
.intro {
    background: #EEF5FB;
    border-left: 5px solid #2F75B5;
    border-radius: 10px;
    padding: 13px 16px;
    margin: 8px 0 18px 0;
    font-size: 15px;
    line-height: 1.65;
}
.small-note {
    color: #66788A;
    font-size: 13px;
    margin-top: -5px;
    margin-bottom: 8px;
}
.success-card {
    background: #EAF7EF;
    border: 1px solid #B8DFC6;
    border-radius: 12px;
    padding: 18px 20px;
    color: #23683A;
    font-size: 17px;
    line-height: 1.7;
    text-align: center;
}
div.stButton > button {
    font-weight: 700;
    min-height: 48px;
}
</style>
""", unsafe_allow_html=True)

st.title("🛡️ 오늘의 30초 체크인")

st.markdown("""
<div class="intro">
오늘의 상태를 짧게 알려주세요.<br>
이 체크인은 <b>위급상황을 자동으로 판단하는 검사가 아닙니다.</b>
평소와 다른 변화나 도움이 필요한 신호가 있을 때,
담당 선생님 등이 직접 확인할 수 있도록 돕기 위한 체크인입니다.
</div>
""", unsafe_allow_html=True)

student_id = st.text_input(
    "학생 ID",
    placeholder="예: STU-001"
)

st.markdown("### 1. 지금 기분은 어떤가요?")
mood = st.radio(
    "현재 기분",
    ["🙂 괜찮아요", "😐 조금 힘들어요", "😟 많이 힘들어요"],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("### 2. 지금 혼자 감당하기 어렵거나 안전하지 않다고 느끼나요?")
safety = st.radio(
    "현재 안전감",
    ["아니요", "조금 그래요", "네"],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("### 3. 오늘 Safety Plan이 필요했거나 사용했나요?")
safety_plan = st.radio(
    "Safety Plan",
    [
        "필요하지 않았어요",
        "필요했지만 사용하지 않았어요",
        "사용했어요"
    ],
    label_visibility="collapsed"
)

st.markdown("### 4. 지금 누군가의 도움이 필요한가요?")
help_request = st.radio(
    "도움 요청",
    [
        "지금은 필요하지 않아요",
        "친구에게 연락하고 싶어요",
        "선생님·보호자 등 성인의 도움이 필요해요"
    ],
    label_visibility="collapsed"
)

st.markdown(
    '<div class="small-note">'
    '친구는 위험을 판단하는 사람이 아니라, '
    '혼자 있지 않도록 연결을 돕는 지원자입니다.'
    '</div>',
    unsafe_allow_html=True
)

memo = st.text_area(
    "선택사항 · 오늘 있었던 일을 짧게 남겨도 됩니다.",
    placeholder="입력하지 않아도 됩니다.",
    height=75
)

if st.button(
    "체크인 제출",
    type="primary",
    use_container_width=True
):
    if not student_id.strip():
        st.error("학생 ID를 입력해 주세요.")
    else:
        save_record(
            student_id,
            mood,
            safety,
            safety_plan,
            help_request,
            memo
        )

        st.markdown("""
        <div class="success-card">
        <b>잘 전달되었습니다.</b><br>
        오늘의 상태를 알려주셔서 감사합니다.
        </div>
        """, unsafe_allow_html=True)

st.caption("※ 프로토타입 화면입니다.")
