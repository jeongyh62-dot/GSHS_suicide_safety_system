import streamlit as st
import sqlite3
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="학생 초기 선별 설문",
    page_icon="📝",
    layout="centered"
)

BASE_DIR = Path(__file__).resolve().parent


def resolve_model_dir():
    candidates = [
        BASE_DIR / "models",
        BASE_DIR.parent / "models",
    ]
    for p in candidates:
        if (p / "suicide_attempt_rf_tuned.joblib").exists():
            return p
    return candidates[0]


def resolve_db_path():
    project_root = BASE_DIR.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "checkin_data.db"


MODEL_DIR = resolve_model_dir()
MODEL_PATH = MODEL_DIR / "suicide_attempt_rf_tuned.joblib"
FEATURE_PATH = MODEL_DIR / "suicide_attempt_features.joblib"
DB_PATH = resolve_db_path()


# ---------------------------------------------------------
# 모델 로드
# ---------------------------------------------------------
@st.cache_resource
def load_model():
    model = joblib.load(MODEL_PATH)
    features = joblib.load(FEATURE_PATH)
    return model, features


try:
    model, feature_order = load_model()
except FileNotFoundError:
    st.error(
        "모델 파일을 찾지 못했습니다. "
        "`models/suicide_attempt_rf_tuned.joblib`과 "
        "`models/suicide_attempt_features.joblib` 위치를 확인해 주세요."
    )
    st.stop()


# ---------------------------------------------------------
# DB
# ---------------------------------------------------------
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

    conn.commit()
    conn.close()


def save_screening(student_id, input_values, probability):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    sid = student_id.strip()

    cur.execute("""
        INSERT OR IGNORE INTO students (
            student_id, student_name, active
        )
        VALUES (?, '', 1)
    """, (sid,))

    columns = [
        "age_15_or_older",
        "female",
        "hunger",
        "alcohol_use",
        "loneliness",
        "anxiety",
        "physically_attacked",
        "close_friends",
        "peer_support",
        "parental_supervision",
        "parental_attachment",
        "parental_bonding",
        "truancy",
        "physical_activity",
        "obesity",
    ]

    values = [int(input_values[c]) for c in columns]

    cur.execute(f"""
        INSERT INTO initial_screenings (
            timestamp, student_id,
            {", ".join(columns)},
            predicted_probability,
            reviewer_checked,
            reviewer_note
        )
        VALUES (
            ?, ?,
            {", ".join(["?"] * len(columns))},
            ?, 0, ''
        )
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sid,
        *values,
        float(probability)
    ))

    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# 스타일
# ---------------------------------------------------------
st.markdown("""
<style>
.block-container {
    max-width: 820px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}
html, body, [class*="css"] {
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
}
h1, h2, h3 {
    color: #173B6C;
}
.intro {
    background: #EEF5FB;
    border-left: 5px solid #2F75B5;
    border-radius: 10px;
    padding: 14px 16px;
    margin: 8px 0 18px 0;
    line-height: 1.65;
}
.small-note {
    color: #66788A;
    font-size: 13px;
    line-height: 1.55;
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
    min-height: 48px;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 화면
# ---------------------------------------------------------
st.title("📝 학생 초기 선별 설문")

st.markdown("""
<div class="intro">
아래 문항은 학생의 현재 및 최근 생활·건강 상태를 확인하기 위한 초기 설문입니다.<br>
응답 결과는 담당자에게 전달되며, 학생 화면에는 모델의 예측확률이나 내부 분석 결과가 표시되지 않습니다.
</div>
""", unsafe_allow_html=True)

student_id = st.text_input(
    "학생 ID",
    placeholder="예: STU-001"
)

st.markdown("### 1. 기본 정보")

col1, col2 = st.columns(2)

with col1:
    age_15_or_older = st.radio(
        "연령",
        ["14세 이하", "15세 이상"],
        horizontal=True
    )

with col2:
    female = st.radio(
        "성별",
        ["남성", "여성"],
        horizontal=True
    )

st.markdown("### 2. 개인·정신건강 관련 항목")

hunger = st.radio(
    "최근 30일 동안 집에 먹을 음식이 충분하지 않아 대부분의 시간 또는 항상 배고팠습니까?",
    ["아니오", "예"],
    horizontal=True
)

alcohol_use = st.radio(
    "최근 30일 동안 하루 이상 술을 마신 적이 있습니까?",
    ["아니오", "예"],
    horizontal=True
)

loneliness = st.radio(
    "최근 12개월 동안 대부분의 시간 또는 항상 외로움을 느꼈습니까?",
    ["아니오", "예"],
    horizontal=True
)

anxiety = st.radio(
    "최근 12개월 동안 걱정이 너무 많아 대부분의 시간 또는 항상 밤에 잠들지 못한 적이 있습니까?",
    ["아니오", "예"],
    horizontal=True
)

physically_attacked = st.radio(
    "최근 12개월 동안 한 번 이상 신체적 공격을 받은 적이 있습니까?",
    ["아니오", "예"],
    horizontal=True
)

st.markdown("### 3. 또래·가족·학교 관련 항목")

close_friends = st.radio(
    "친한 친구가 한 명 이상 있습니까?",
    ["아니오", "예"],
    horizontal=True
)

peer_support = st.radio(
    "최근 30일 동안 학교 친구들이 대부분의 시간 또는 항상 친절하고 도움을 주었습니까?",
    ["아니오", "예"],
    horizontal=True
)

parental_supervision = st.radio(
    "최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 숙제를 확인했습니까?",
    ["아니오", "예"],
    horizontal=True
)

parental_attachment = st.radio(
    "최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 자신의 문제와 걱정을 이해해 주었습니까?",
    ["아니오", "예"],
    horizontal=True
)

parental_bonding = st.radio(
    "최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 자신의 여가시간 활동을 알고 있었습니까?",
    ["아니오", "예"],
    horizontal=True
)

truancy = st.radio(
    "최근 30일 동안 허락 없이 하루 이상 수업이나 학교에 빠진 적이 있습니까?",
    ["아니오", "예"],
    horizontal=True
)

st.markdown("### 4. 건강행동·신체상태")

physical_activity = st.radio(
    "최근 7일 동안 매일 하루 60분 이상 신체활동을 했습니까?",
    ["아니오", "예"],
    horizontal=True
)

obesity = st.radio(
    "WHO 연령·성별 BMI 기준에서 비만(중앙값 대비 +2 SD 초과)에 해당합니까?",
    ["아니오", "예"],
    horizontal=True
)

st.markdown(
    '<div class="small-note">'
    "※ 비만 여부는 WHO 연령·성별 BMI 기준에 따라 확인된 값을 입력하는 것을 전제로 합니다."
    "</div>",
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# 0/1 변환
# ---------------------------------------------------------
binary = {"아니오": 0, "예": 1}

input_values = {
    "age_15_or_older": 0 if age_15_or_older == "14세 이하" else 1,
    "female": 0 if female == "남성" else 1,
    "hunger": binary[hunger],
    "alcohol_use": binary[alcohol_use],
    "loneliness": binary[loneliness],
    "anxiety": binary[anxiety],
    "physically_attacked": binary[physically_attacked],
    "close_friends": binary[close_friends],
    "peer_support": binary[peer_support],
    "parental_supervision": binary[parental_supervision],
    "parental_attachment": binary[parental_attachment],
    "parental_bonding": binary[parental_bonding],
    "truancy": binary[truancy],
    "physical_activity": binary[physical_activity],
    "obesity": binary[obesity],
}


# ---------------------------------------------------------
# 모델 실행 + 내부 저장
# 학생에게는 확률/판정 결과를 표시하지 않는다.
# ---------------------------------------------------------
if st.button(
    "초기 선별 설문 제출",
    type="primary",
    use_container_width=True
):
    if not student_id.strip():
        st.error("학생 ID를 입력해 주세요.")
    else:
        X_input = pd.DataFrame(
            [[input_values[f] for f in feature_order]],
            columns=feature_order
        )

        probability = float(model.predict_proba(X_input)[0, 1])

        save_screening(
            student_id=student_id,
            input_values=input_values,
            probability=probability
        )

        st.markdown("""
<div class="success-card">
<b>응답이 정상적으로 제출되었습니다.</b><br>
참여해 주셔서 감사합니다.
</div>
""", unsafe_allow_html=True)

