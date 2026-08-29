"""
통합 테스트용 가상 학생 데이터 생성기
- 실제 학생 데이터와 구분하기 위해 TEST-001 ~ TEST-005만 사용합니다.
- 실행 시 기존 TEST-001 ~ TEST-005 데이터만 삭제한 후 다시 생성합니다.
- 실제 학생 데이터는 삭제하지 않습니다.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def resolve_db_path():
    project_root = BASE_DIR.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "checkin_data.db"


DB_PATH = resolve_db_path()

TEST_IDS = [f"TEST-{i:03d}" for i in range(1, 6)]

def ensure_schema(conn):
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

    cur.execute("PRAGMA table_info(initial_screenings)")
    cols = {r[1] for r in cur.fetchall()}
    if "continuous_management" not in cols:
        cur.execute("ALTER TABLE initial_screenings ADD COLUMN continuous_management INTEGER DEFAULT 0")
    if "management_source" not in cols:
        cur.execute("ALTER TABLE initial_screenings ADD COLUMN management_source TEXT DEFAULT ''")

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

    conn.commit()

def clear_test_data(conn):
    cur = conn.cursor()
    marks = ",".join(["?"] * len(TEST_IDS))

    for table in [
        "checkins",
        "initial_screenings",
        "safety_plans",
        "management_contacts",
        "students",
    ]:
        cur.execute(
            f"DELETE FROM {table} WHERE student_id IN ({marks})",
            TEST_IDS
        )

    conn.commit()

def add_student(conn, sid, name):
    conn.execute("""
        INSERT INTO students(student_id, student_name, active)
        VALUES (?, ?, 1)
    """, (sid, name))

def add_screening(conn, sid, vals, prob, managed=0, source="", note=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cols = [
        "age_15_or_older","female","hunger","alcohol_use","loneliness",
        "anxiety","physically_attacked","close_friends","peer_support",
        "parental_supervision","parental_attachment","parental_bonding",
        "truancy","physical_activity","obesity"
    ]

    conn.execute(f"""
        INSERT INTO initial_screenings(
            timestamp, student_id,
            {",".join(cols)},
            predicted_probability,
            reviewer_checked,
            reviewer_note,
            continuous_management,
            management_source
        )
        VALUES (
            ?, ?,
            {",".join(["?"] * len(cols))},
            ?, ?, ?, ?, ?
        )
    """, (
        now, sid,
        *[int(vals[c]) for c in cols],
        float(prob),
        1 if note else 0,
        note,
        int(managed),
        source
    ))

def add_checkin(conn, sid, dt, mood, safety, plan, help_req,
                status, checked=0, note="", memo=""):
    conn.execute("""
        INSERT INTO checkins(
            timestamp, student_id, mood, safety, safety_plan,
            help_request, memo, monitoring_status,
            teacher_checked, teacher_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dt.strftime("%Y-%m-%d %H:%M:%S"),
        sid, mood, safety, plan, help_req, memo,
        status, int(checked), note
    ))

def add_safety_plan(conn, sid):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO safety_plans(
            student_id, warning_signs, coping_strategies,
            social_supports, professional_supports,
            safe_environment, updated_at, plan_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, '작성 완료')
    """, (
        sid,
        "잠을 잘 못 자고 혼자 있고 싶어질 때",
        "산책하기, 음악 듣기, 호흡 정리",
        "가까운 친구 또는 가족에게 연락하기",
        "담임교사·상담교사·보건교사에게 도움 요청하기",
        "혼자 있지 않고 신뢰할 수 있는 성인과 함께 있기",
        now
    ))

def add_contact(conn, sid, phone, checkin="20:00", reminder="20:30",
                consent=1, enabled=1, sent_today=False):
    today = datetime.now().strftime("%Y-%m-%d")
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if sent_today else ""

    conn.execute("""
        INSERT INTO management_contacts(
            student_id, phone, checkin_time, reminder_time,
            consent_confirmed, reminder_enabled,
            last_reminder_date, last_reminder_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sid, phone, checkin, reminder,
        int(consent), int(enabled),
        today if sent_today else "",
        sent_at
    ))

def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    clear_test_data(conn)

    # 15개 입력값 템플릿
    base = {
        "age_15_or_older": 1,
        "female": 0,
        "hunger": 0,
        "alcohol_use": 0,
        "loneliness": 0,
        "anxiety": 0,
        "physically_attacked": 0,
        "close_friends": 1,
        "peer_support": 1,
        "parental_supervision": 1,
        "parental_attachment": 1,
        "parental_bonding": 1,
        "truancy": 0,
        "physical_activity": 1,
        "obesity": 0,
    }

    profiles = [
        ("TEST-001", "가상학생1", 0.82, 1, "RF 추천"),
        ("TEST-002", "가상학생2", 0.66, 1, "RF 추천"),
        ("TEST-003", "가상학생3", 0.51, 1, "전문가 추가"),
        ("TEST-004", "가상학생4", 0.31, 0, ""),
        ("TEST-005", "가상학생5", 0.14, 0, ""),
    ]

    for i, (sid, name, prob, managed, source) in enumerate(profiles):
        add_student(conn, sid, name)

        vals = base.copy()

        if sid == "TEST-001":
            vals.update({
                "loneliness": 1,
                "anxiety": 1,
                "physically_attacked": 1,
                "peer_support": 0,
                "parental_attachment": 0,
            })
        elif sid == "TEST-002":
            vals.update({
                "loneliness": 1,
                "alcohol_use": 1,
                "truancy": 1,
            })
        elif sid == "TEST-003":
            vals.update({
                "anxiety": 1,
                "peer_support": 0,
                "parental_bonding": 0,
            })
        elif sid == "TEST-004":
            vals.update({"loneliness": 1})
        elif sid == "TEST-005":
            vals.update({})

        add_screening(
            conn, sid, vals, prob,
            managed=managed,
            source=source,
            note="통합 테스트용 가상 데이터"
        )

    now = datetime.now()

    # TEST-001: Safety Plan 있음, 오늘 체크인 있음, 최근 악화
    add_safety_plan(conn, "TEST-001")
    add_contact(conn, "TEST-001", "010-0000-0001", "20:00", "20:30", 1, 1)
    add_checkin(
        conn, "TEST-001", now - timedelta(days=1),
        "🙂 괜찮아요", "아니요",
        "필요하지 않았어요",
        "지금은 필요하지 않아요",
        "기록 완료", 1, "전날 확인 완료"
    )
    add_checkin(
        conn, "TEST-001", now,
        "😟 많이 힘들어요", "네",
        "필요했지만 사용하지 않았어요",
        "선생님·보호자 등 성인의 도움이 필요해요",
        "빠른 확인 필요", 0, ""
    )

    # TEST-002: Safety Plan 있음, 오늘 미응답, 리마인드 설정 있음
    add_safety_plan(conn, "TEST-002")
    add_contact(conn, "TEST-002", "010-0000-0002", "18:00", "18:30", 1, 1)
    add_checkin(
        conn, "TEST-002", now - timedelta(days=1),
        "😐 조금 힘들어요", "조금 그래요",
        "사용했어요",
        "친구에게 연락하고 싶어요",
        "추가 확인 필요", 1, "전날 상담 완료"
    )

    # TEST-003: 전문가 추가 대상, 연락처 미등록, Safety Plan 미작성
    add_checkin(
        conn, "TEST-003", now,
        "😐 조금 힘들어요", "아니요",
        "필요하지 않았어요",
        "지금은 필요하지 않아요",
        "기록 완료", 0, ""
    )

    conn.commit()
    conn.close()

    print("통합 테스트용 가상 학생 5명 생성 완료")
    print(f"DB 경로: {DB_PATH}")
    print("")
    print("확인 시나리오")
    print("TEST-001: RF 추천 + Safety Plan + 오늘 체크인 + 최근 악화 + 빠른 확인 필요")
    print("TEST-002: RF 추천 + Safety Plan + 오늘 미응답 + 리마인드 설정")
    print("TEST-003: 전문가 추가 + Safety Plan/연락처 미등록")
    print("TEST-004: 지속관리 미포함")
    print("TEST-005: 지속관리 미포함")

if __name__ == "__main__":
    main()
