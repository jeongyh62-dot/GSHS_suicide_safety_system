# =========================================================
# Shuvo(2025) balanced-data 재현 기반 발표용 버전
# - 자살사고 / 자살계획 / 자살시도 3개 RF
# - 8개 상담지원 프로파일 Naming
# - Green / Yellow / Red 3단계 관리 수준
#   Green=안정군 / Yellow=관심군 / Red=고위험군
# - 학생 화면에는 결과 비노출
# =========================================================

import streamlit as st
import sqlite3
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title='학생 초기 선별 설문', page_icon='📝', layout='centered')
BASE_DIR = Path(__file__).resolve().parent

def resolve_model_dir():
    candidates = [BASE_DIR / 'models', BASE_DIR.parent / 'models']
    for p in candidates:
        if any((p / n).exists() for n in [
            'suicide_ideation_rf_tuned.joblib',
            'suicide_plan_rf_tuned.joblib',
            'suicide_attempt_rf_tuned.joblib',
        ]):
            return p
    return candidates[0]

def resolve_db_path():
    candidates = [
        BASE_DIR / 'checkin_data.db',
        BASE_DIR.parent / 'checkin_data.db',
        BASE_DIR.parent / 'data' / 'checkin_data.db',
        BASE_DIR / 'notebook' / 'checkin_data.db',
        BASE_DIR.parent / 'notebook' / 'checkin_data.db',
    ]
    for p in candidates:
        if p.exists():
            return p
    data_dir = BASE_DIR.parent / 'data'
    if data_dir.exists():
        return data_dir / 'checkin_data.db'
    return BASE_DIR / 'checkin_data.db'

MODEL_DIR = resolve_model_dir()
DB_PATH = resolve_db_path()

MODEL_SPECS = {
    'ideation': ('자살사고', 'suicide_ideation_rf_tuned.joblib', 'suicide_ideation_features.joblib'),
    'plan': ('자살계획', 'suicide_plan_rf_tuned.joblib', 'suicide_plan_features.joblib'),
    'attempt': ('자살시도', 'suicide_attempt_rf_tuned.joblib', 'suicide_attempt_features.joblib'),
}

@st.cache_resource
def load_models():
    loaded = {}
    for key, (_, model_name, feature_name) in MODEL_SPECS.items():
        loaded[key] = {
            'model': joblib.load(MODEL_DIR / model_name),
            'features': list(joblib.load(MODEL_DIR / feature_name)),
        }
    return loaded

missing = []
for _, model_name, feature_name in MODEL_SPECS.values():
    for name in [model_name, feature_name]:
        if not (MODEL_DIR / name).exists():
            missing.append(name)

if missing:
    st.error('자살사고·자살계획·자살시도 3개 RF 추론에 필요한 모델 파일이 모두 준비되지 않았습니다.')
    st.markdown('**확인이 필요한 파일**')
    for name in missing:
        st.code(name)
    st.caption('부족한 모델 파일을 models/ 폴더에 추가한 뒤 다시 실행해 주세요.')
    st.stop()

try:
    MODELS = load_models()
except Exception as e:
    st.error(f'RF 모델을 불러오는 중 오류가 발생했습니다: {e}')
    st.stop()

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

def classify_profile(ideation, plan, attempt):
    return PROFILE_MAP[(int(ideation), int(plan), int(attempt))]

SCREENING_COLUMNS = [
    'age_15_or_older', 'female', 'hunger', 'alcohol_use', 'loneliness',
    'anxiety', 'physically_attacked', 'close_friends', 'peer_support',
    'parental_supervision', 'parental_attachment', 'parental_bonding',
    'truancy', 'physical_activity', 'obesity',
]

def ensure_column(cur, table_name, column_name, definition):
    cur.execute(f'PRAGMA table_info({table_name})')
    existing = {row[1] for row in cur.fetchall()}
    if column_name not in existing:
        cur.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    ''')
    cur.execute('''
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
    ''')
    migrations = {
        'ideation_probability': 'REAL',
        'plan_probability': 'REAL',
        'attempt_probability': 'REAL',
        'ideation_prediction': 'INTEGER',
        'plan_prediction': 'INTEGER',
        'attempt_prediction': 'INTEGER',
        'counseling_profile': "TEXT DEFAULT ''",
        'priority_color': "TEXT DEFAULT ''",
        'management_group': "TEXT DEFAULT ''",
        'counseling_direction': "TEXT DEFAULT ''",
    }
    for name, definition in migrations.items():
        ensure_column(cur, 'initial_screenings', name, definition)
    conn.commit()
    conn.close()

def predict_outcome(input_values, outcome_key):
    model = MODELS[outcome_key]['model']
    feature_order = MODELS[outcome_key]['features']
    missing_features = [f for f in feature_order if f not in input_values]
    if missing_features:
        label = MODEL_SPECS[outcome_key][0]
        raise ValueError(f'{label} 모델에 필요한 입력변수가 설문에 없습니다: {missing_features}')
    X = pd.DataFrame([[input_values[f] for f in feature_order]], columns=feature_order)
    probability = float(model.predict_proba(X)[0, 1])
    prediction = int(model.predict(X)[0])
    return probability, prediction

def save_screening(student_id, input_values, results):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    sid = student_id.strip()
    cur.execute("INSERT OR IGNORE INTO students (student_id, student_name, active) VALUES (?, '', 1)", (sid,))
    values = [int(input_values[c]) for c in SCREENING_COLUMNS]
    ideation, plan, attempt = results['ideation'], results['plan'], results['attempt']
    profile, level, group, direction = classify_profile(
        ideation['prediction'], plan['prediction'], attempt['prediction']
    )
    cur.execute(f'''
        INSERT INTO initial_screenings (
            timestamp, student_id, {', '.join(SCREENING_COLUMNS)},
            predicted_probability,
            ideation_probability, plan_probability, attempt_probability,
            ideation_prediction, plan_prediction, attempt_prediction,
            counseling_profile, priority_color, management_group, counseling_direction,
            reviewer_checked, reviewer_note
        ) VALUES (
            ?, ?, {', '.join(['?'] * len(SCREENING_COLUMNS))},
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ''
        )
    ''', (
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sid, *values,
        float(attempt['probability']),
        float(ideation['probability']), float(plan['probability']), float(attempt['probability']),
        int(ideation['prediction']), int(plan['prediction']), int(attempt['prediction']),
        profile, level, group, direction,
    ))
    conn.commit()
    conn.close()

init_db()

st.markdown('''
<style>
.block-container {max-width: 820px; padding-top: 1.6rem; padding-bottom: 3rem;}
html, body, [class*="css"] {font-family: "Malgun Gothic", "맑은 고딕", sans-serif;}
h1, h2, h3 {color: #173B6C;}
.intro {background:#EEF5FB; border-left:5px solid #2F75B5; border-radius:10px; padding:14px 16px; margin:8px 0 18px; line-height:1.65;}
.small-note {color:#66788A; font-size:13px; line-height:1.55;}
.success-card {background:#EAF7EF; border:1px solid #B8DFC6; border-radius:12px; padding:18px 20px; color:#23683A; font-size:17px; line-height:1.7; text-align:center;}
div.stButton > button {min-height:48px; font-weight:700;}
</style>
''', unsafe_allow_html=True)

st.title('📝 학생 초기 선별 설문')
st.markdown('''
<div class="intro">
아래 문항은 학생의 최근 생활·건강 상태를 확인하기 위한 초기 설문입니다.<br>
응답 결과는 Shuvo(2025) 기반 Random Forest 모델의 재현 결과를 활용하여
담당자의 상담 검토를 지원하는 내부 정보로 저장됩니다.<br>
학생 화면에는 모델의 예측확률·상담유형·관리 수준이 표시되지 않습니다.
</div>
''', unsafe_allow_html=True)

student_id = st.text_input('학생 ID', placeholder='예: STU-001')

st.markdown('### 1. 기본 정보')
col1, col2 = st.columns(2)
with col1:
    age_15_or_older = st.radio('연령', ['14세 이하', '15세 이상'], horizontal=True)
with col2:
    female = st.radio('성별', ['남성', '여성'], horizontal=True)

st.markdown('### 2. 개인·정신건강 관련 항목')
hunger = st.radio('최근 30일 동안 집에 먹을 음식이 충분하지 않아 대부분의 시간 또는 항상 배고팠습니까?', ['아니오', '예'], horizontal=True)
alcohol_use = st.radio('최근 30일 동안 하루 이상 술을 마신 적이 있습니까?', ['아니오', '예'], horizontal=True)
loneliness = st.radio('최근 12개월 동안 대부분의 시간 또는 항상 외로움을 느꼈습니까?', ['아니오', '예'], horizontal=True)
anxiety = st.radio('최근 12개월 동안 걱정이 너무 많아 대부분의 시간 또는 항상 밤에 잠들지 못한 적이 있습니까?', ['아니오', '예'], horizontal=True)
physically_attacked = st.radio('최근 12개월 동안 한 번 이상 신체적 공격을 받은 적이 있습니까?', ['아니오', '예'], horizontal=True)

st.markdown('### 3. 또래·가족·학교 관련 항목')
close_friends = st.radio('친한 친구가 한 명 이상 있습니까?', ['아니오', '예'], horizontal=True)
peer_support = st.radio('최근 30일 동안 학교 친구들이 대부분의 시간 또는 항상 친절하고 도움을 주었습니까?', ['아니오', '예'], horizontal=True)
parental_supervision = st.radio('최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 숙제를 확인했습니까?', ['아니오', '예'], horizontal=True)
parental_attachment = st.radio('최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 자신의 문제와 걱정을 이해해 주었습니까?', ['아니오', '예'], horizontal=True)
parental_bonding = st.radio('최근 30일 동안 부모님 또는 보호자가 대부분의 시간 또는 항상 자신의 여가시간 활동을 알고 있었습니까?', ['아니오', '예'], horizontal=True)
truancy = st.radio('최근 30일 동안 허락 없이 하루 이상 수업이나 학교에 빠진 적이 있습니까?', ['아니오', '예'], horizontal=True)

st.markdown('### 4. 건강행동·신체상태')
physical_activity = st.radio('최근 7일 동안 매일 하루 60분 이상 신체활동을 했습니까?', ['아니오', '예'], horizontal=True)
obesity = st.radio('WHO 연령·성별 BMI 기준에서 비만(중앙값 대비 +2 SD 초과)에 해당합니까?', ['아니오', '예'], horizontal=True)
st.markdown('<div class="small-note">※ 비만 여부는 WHO 연령·성별 BMI 기준에 따라 확인된 값을 입력하는 것을 전제로 합니다.</div>', unsafe_allow_html=True)

binary = {'아니오': 0, '예': 1}
input_values = {
    'age_15_or_older': 0 if age_15_or_older == '14세 이하' else 1,
    'female': 0 if female == '남성' else 1,
    'hunger': binary[hunger], 'alcohol_use': binary[alcohol_use],
    'loneliness': binary[loneliness], 'anxiety': binary[anxiety],
    'physically_attacked': binary[physically_attacked],
    'close_friends': binary[close_friends], 'peer_support': binary[peer_support],
    'parental_supervision': binary[parental_supervision],
    'parental_attachment': binary[parental_attachment],
    'parental_bonding': binary[parental_bonding],
    'truancy': binary[truancy], 'physical_activity': binary[physical_activity],
    'obesity': binary[obesity],
}

if st.button('초기 선별 설문 제출', type='primary', use_container_width=True):
    if not student_id.strip():
        st.error('학생 ID를 입력해 주세요.')
    else:
        try:
            results = {}
            for outcome_key in ['ideation', 'plan', 'attempt']:
                probability, prediction = predict_outcome(input_values, outcome_key)
                results[outcome_key] = {'probability': probability, 'prediction': prediction}
            save_screening(student_id, input_values, results)
            st.markdown('''<div class="success-card"><b>응답이 정상적으로 제출되었습니다.</b><br>참여해 주셔서 감사합니다.</div>''', unsafe_allow_html=True)
        except Exception as e:
            st.error('응답 저장 또는 모델 추론 중 오류가 발생했습니다. 관리자에게 다음 내용을 전달해 주세요: ' + str(e))
