import streamlit as st

# 발표용 통합 진입점
# 학생용/교사용을 하나의 Streamlit 앱으로 묶어 동일한 SQLite DB를 사용합니다.

pages = [
    st.Page(
        "apps/screening_app.py",
        title="학생용 초기 선별",
        icon="📝",
        default=True,
    ),
    st.Page(
        "apps/teacher_dashboard.py",
        title="교사용 Dashboard",
        icon="🧑‍🏫",
    ),
]

navigation = st.navigation(pages)
navigation.run()
