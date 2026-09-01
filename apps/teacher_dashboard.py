import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path

# =========================================================
# Shuvo(2025) 기반 상담지원 대시보드
# - 3개 RF 결과의 8개 상담지원 프로파일 Naming
# - Green / Yellow / Red 3단계 관리 수준
#   Green=안정군 / Yellow=관심군 / Red=고위험군
# - 전문가 확인 및 메모
# =========================================================

st.set_page_config(page_title="교사용 상담지원 Dashboard", page_icon="🧑‍🏫", layout="wide")
BASE_DIR = Path(__file__).resolve().parent

def resolve_db_path():
    candidates = [
        BASE_DIR / "checkin_data.db",
        BASE_DIR / "data" / "checkin_data.db",
        BASE_DIR / "notebook" / "checkin_data.db",
        BASE_DIR.parent / "checkin_data.db",
        BASE_DIR.parent / "data" / "checkin_data.db",
        BASE_DIR.parent / "notebook" / "checkin_data.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "checkin_data.db"

DB_PATH = resolve_db_path()

PROFILE_MAP = {
    (0, 0, 0): ('일반 관찰군', 'Green', '안정군', '정기 관찰'),
    (1, 0, 0): ('정서위축-사고형', 'Yellow', '관심군', '정서상태 확인'),
    (0, 1, 0): ('계획표출형', 'Yellow', '관심군', '계획 구체성 확인'),
    (1, 1, 0): ('사고-계획 진행형', 'Yellow', '관심군', '집중 상담 검토'),
    (0, 0, 1): ('돌봄 시도형', 'Red', '고위험군', '즉각 안전 확인'),
    (1, 0, 1): ('사고-행동 이행형', 'Red', '고위험군', '위기 개입·보호 체계'),
    (0, 1, 1): ('계획-시도형', 'Red', '고위험군', '전문기관 신속 연계'),
    (1, 1, 1): ('복합 고위험형', 'Red', '고위험군', '최우선 위기 개입'),
}

PROFILE_GUIDE = {
    profile: {"level": level, "group": group, "direction": direction}
    for _, (profile, level, group, direction) in PROFILE_MAP.items()
}
MANAGEMENT_ORDER = {"Red": 0, "Yellow": 1, "Green": 2}

def ensure_column(cur, table_name, column_name, definition):
    cur.execute(f"PRAGMA table_info({table_name})")
    existing = {row[1] for row in cur.fetchall()}
    if column_name not in existing:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

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
            reviewer_note TEXT DEFAULT ''
        )
    """)
    migrations = {
        "ideation_probability": "REAL",
        "plan_probability": "REAL",
        "attempt_probability": "REAL",
        "ideation_prediction": "INTEGER",
        "plan_prediction": "INTEGER",
        "attempt_prediction": "INTEGER",
        "counseling_profile": "TEXT DEFAULT ''",
        "priority_color": "TEXT DEFAULT ''",
        "management_group": "TEXT DEFAULT ''",
        "counseling_direction": "TEXT DEFAULT ''",
        "reviewer_checked": "INTEGER DEFAULT 0",
        "reviewer_note": "TEXT DEFAULT ''",
    }
    for name, definition in migrations.items():
        ensure_column(cur, "initial_screenings", name, definition)
    conn.commit()
    conn.close()

def sync_classification():
    """기존 DB의 과거 Gray/Green 분류도 현재 확정 기준으로 자동 재분류."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT id, ideation_prediction, plan_prediction, attempt_prediction
        FROM initial_screenings
    """).fetchall()
    for record_id, ideation, plan, attempt in rows:
        if ideation is None or plan is None or attempt is None:
            continue
        key = (int(ideation), int(plan), int(attempt))
        if key not in PROFILE_MAP:
            continue
        profile, level, group, direction = PROFILE_MAP[key]
        cur.execute("""
            UPDATE initial_screenings
            SET counseling_profile=?, priority_color=?,
                management_group=?, counseling_direction=?
            WHERE id=?
        """, (profile, level, group, direction, int(record_id)))
    conn.commit()
    conn.close()

def load_screenings():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT * FROM initial_screenings
        ORDER BY datetime(timestamp) DESC, id DESC
    """, conn)
    conn.close()
    return df

def save_review(record_id, checked, note):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE initial_screenings
        SET reviewer_checked=?, reviewer_note=?
        WHERE id=?
    """, (1 if checked else 0, note.strip(), int(record_id)))
    conn.commit()
    conn.close()

def yes_no(v):
    try:
        return "1" if int(v) == 1 else "0"
    except Exception:
        return "-"

def pct(v):
    try:
        if pd.isna(v):
            return "-"
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return "-"

def management_badge(level):
    return {
        "Red": ("🔴", "#D64545"),
        "Yellow": ("🟡", "#D9A300"),
        "Green": ("🟢", "#2E9E6B"),
    }.get(str(level or ""), ("⚪", "#6B7280"))

init_db()
sync_classification()
screenings = load_screenings()

if screenings.empty:
    latest = pd.DataFrame()
else:
    latest = (
        screenings
        .sort_values(["student_id", "timestamp", "id"], ascending=[True, False, False])
        .groupby("student_id", as_index=False)
        .first()
    )

st.markdown("""
<style>
html, body, [class*="css"] {font-family: "Malgun Gothic", "맑은 고딕", sans-serif;}
.block-container {padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1500px;}
h1, h2, h3 {color: #173B6C;}
.note-box {background:#EEF5FB; border-left:5px solid #2F75B5; border-radius:10px; padding:13px 16px; line-height:1.65; margin:8px 0 16px 0;}
.profile-box {border:1px solid #D9E2F0; border-radius:12px; padding:14px 16px; background:white;}
</style>
""", unsafe_allow_html=True)

st.title("🧑‍🏫 교사용 상담지원 Dashboard")

st.markdown("""
<div class="note-box">
<b>Shuvo(2025) 기반 초기 선별 결과를 상담지원 정보로 재구성한 화면입니다.</b><br>
자살사고·자살계획·자살시도 3개 Random Forest 결과의 조합을
<b>8개 상담지원 프로파일</b>로 Naming하고,
Green·Yellow·Red는 각각 <b>안정군·관심군·고위험군의 관리 수준</b>을 나타냅니다.<br>
색상은 임상 진단이나 확정 위험등급이 아니며, 학생에게 결과를 노출하지 않고 최종 판단은 전문가가 수행합니다.
</div>
""", unsafe_allow_html=True)

if latest.empty:
    st.info("아직 학생용 초기 선별 설문에서 제출된 결과가 없습니다.")
    st.stop()

latest["priority_color"] = latest["priority_color"].fillna("Green")
latest["management_group"] = latest["management_group"].fillna("안정군")
latest["counseling_profile"] = latest["counseling_profile"].fillna("일반 관찰군")

n_total = len(latest)
n_red = int((latest["priority_color"] == "Red").sum())
n_yellow = int((latest["priority_color"] == "Yellow").sum())
n_green = int((latest["priority_color"] == "Green").sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("선별 완료", f"{n_total:,}명")
k2.metric("🔴 Red · 고위험군", f"{n_red:,}명")
k3.metric("🟡 Yellow · 관심군", f"{n_yellow:,}명")
k4.metric("🟢 Green · 안정군", f"{n_green:,}명")

st.markdown("### 1. 전체 학생 상담지원 현황")

display_df = latest.copy()
display_df["_management_order"] = display_df["priority_color"].map(MANAGEMENT_ORDER).fillna(9)
display_df = display_df.sort_values(
    ["_management_order", "attempt_probability", "plan_probability", "ideation_probability"],
    ascending=[True, False, False, False]
)

table = display_df[[
    "student_id", "ideation_prediction", "plan_prediction", "attempt_prediction",
    "counseling_profile", "management_group", "priority_color", "reviewer_checked"
]].copy()

for col in ["ideation_prediction", "plan_prediction", "attempt_prediction"]:
    table[col] = table[col].map(lambda x: "1" if x == 1 else "0")

table["priority_color"] = table["priority_color"].map({
    "Red": "🔴 Red", "Yellow": "🟡 Yellow", "Green": "🟢 Green"
}).fillna("-")
table["reviewer_checked"] = table["reviewer_checked"].map(
    {0: "미확인", 1: "확인 완료"}
).fillna("미확인")

table.columns = [
    "학생 ID", "사고", "계획", "시도", "상담유형 Naming",
    "상위 분류", "관리 수준", "전문가 확인"
]

st.dataframe(table, use_container_width=True, hide_index=True,
             height=min(430, 40 + 36 * max(len(table), 1)))

st.caption(
    "※ 사고·계획·시도의 0/1은 각 RF 모델의 예측 결과입니다. "
    "Green·Yellow·Red는 각각 안정군·관심군·고위험군의 관리 수준입니다."
)

st.markdown("### 2. 관리 수준 분포")
management_counts = (
    latest["management_group"]
    .value_counts()
    .reindex(["안정군", "관심군", "고위험군"], fill_value=0)
    .rename_axis("상위 분류")
    .reset_index(name="학생 수")
)
management_counts["관리 수준"] = management_counts["상위 분류"].map({
    "안정군": "🟢 Green", "관심군": "🟡 Yellow", "고위험군": "🔴 Red"
})
st.dataframe(management_counts, use_container_width=True, hide_index=True)

st.markdown("### 3. 학생별 결과 및 전문가 확인")
sid = st.selectbox("학생 선택", display_df["student_id"].astype(str).tolist())
sr = display_df[display_df["student_id"].astype(str) == str(sid)].iloc[0]

profile = str(sr["counseling_profile"])
level = str(sr["priority_color"])
group = str(sr["management_group"])
guide = PROFILE_GUIDE.get(profile, {"direction": "전문가 확인 후 상담 방향 결정"})
icon, color = management_badge(level)

c1, c2, c3, c4 = st.columns(4)
c1.metric("자살사고 RF", yes_no(sr["ideation_prediction"]))
c2.metric("자살계획 RF", yes_no(sr["plan_prediction"]))
c3.metric("자살시도 RF", yes_no(sr["attempt_prediction"]))
c4.metric("관리 수준", f"{icon} {level} · {group}")

st.markdown(
    f"""
    <div class="profile-box">
    <b style="font-size:20px;color:{color};">{profile}</b><br>
    <span style="font-size:15px;">상위 분류: {group}<br>상담 방향: {guide['direction']}</span>
    </div>
    """,
    unsafe_allow_html=True
)

p1, p2, p3 = st.columns(3)
p1.metric("사고 예측확률", pct(sr.get("ideation_probability")))
p2.metric("계획 예측확률", pct(sr.get("plan_probability")))
p3.metric("시도 예측확률", pct(sr.get("attempt_probability")))

st.caption("※ 예측확률은 설명을 위한 모델 출력값이며 단일 확률값만으로 위험도를 확정하지 않습니다.")

with st.expander("📋 초기 선별 15개 입력값 확인", expanded=False):
    labels = {
        "age_15_or_older": "연령", "female": "성별",
        "hunger": "식량 부족으로 심한 배고픔", "alcohol_use": "최근 음주",
        "loneliness": "지속적 외로움", "anxiety": "걱정으로 인한 수면 어려움",
        "physically_attacked": "신체적 공격 경험", "close_friends": "친한 친구 있음",
        "peer_support": "또래 지지", "parental_supervision": "부모 감독",
        "parental_attachment": "부모의 이해·관심", "parental_bonding": "부모와의 유대",
        "truancy": "무단결석", "physical_activity": "신체활동 기준 충족",
        "obesity": "비만 기준 해당",
    }
    rows = []
    for col, label in labels.items():
        value = sr[col]
        if col == "age_15_or_older":
            answer = "15세 이상" if int(value) == 1 else "14세 이하"
        elif col == "female":
            answer = "여성" if int(value) == 1 else "남성"
        else:
            answer = "예" if int(value) == 1 else "아니오"
        rows.append([label, answer])
    st.dataframe(pd.DataFrame(rows, columns=["항목", "응답"]),
                 use_container_width=True, hide_index=True, height=420)

st.markdown("### 4. 전문가 확인")
checked = st.checkbox(
    "이 학생의 초기 선별 결과와 상담지원 프로파일을 확인했습니다.",
    value=int(sr.get("reviewer_checked", 0)) == 1,
    key=f"checked_{int(sr['id'])}"
)
note = st.text_area(
    "전문가 확인 메모",
    value=str(sr.get("reviewer_note", "") or ""),
    placeholder="예: 상담 전 추가 확인이 필요한 상황, 교사 관찰, 보호자 연락 필요 여부 등을 기록",
    height=110,
    key=f"review_note_{int(sr['id'])}"
)
if st.button("전문가 확인 저장", type="primary", use_container_width=True,
             key=f"save_review_{int(sr['id'])}"):
    save_review(sr["id"], checked, note)
    st.success("전문가 확인 내용을 저장했습니다.")
    st.rerun()

with st.expander("ℹ️ 상담유형 Naming 및 관리 수준 기준", expanded=False):
    rule_rows = [
        [0,0,0,"안정군","일반 관찰군","🟢 Green","정기 관찰"],
        [1,0,0,"관심군","정서위축-사고형","🟡 Yellow","정서상태 확인"],
        [0,1,0,"관심군","계획표출형","🟡 Yellow","계획 구체성 확인"],
        [1,1,0,"관심군","사고-계획 진행형","🟡 Yellow","집중 상담 검토"],
        [0,0,1,"고위험군","돌봄 시도형","🔴 Red","즉각 안전 확인"],
        [1,0,1,"고위험군","사고-행동 이행형","🔴 Red","위기 개입·보호 체계"],
        [0,1,1,"고위험군","계획-시도형","🔴 Red","전문기관 신속 연계"],
        [1,1,1,"고위험군","복합 고위험형","🔴 Red","최우선 위기 개입"],
    ]
    st.dataframe(
        pd.DataFrame(rule_rows, columns=[
            "사고","계획","시도","상위 분류","상담유형 Naming","관리 수준","상담 방향"
        ]),
        use_container_width=True, hide_index=True
    )
    st.caption(
        "※ 본 분류는 자살행동 RF 예측 조합을 학교 상담에서 해석 가능한 형태로 "
        "재구성한 프로토타입 운영 기준이며 자동 진단 기준이 아닙니다."
    )

st.divider()
st.caption(f"DB: {DB_PATH} · 본 화면은 연구·발표용 프로토타입이며 자동 임상판정 도구가 아닙니다.")
