# 학생 안전관리 지원 시스템

## 1. 구성
- `apps/screening_app.py` : 전교생 초기 선별 설문 및 RF 예측값 저장
- `apps/student_checkin_app.py` : 지속관리 학생의 30초 체크인
- `apps/teacher_dashboard.py` : RF 상대순위, 전문가 추가 선정, Safety Plan, 체크인 모니터링, 후속조치
- `tests/integration_test_seed.py` : TEST-001 ~ TEST-005 통합 시연 데이터 생성
- `data/checkin_data.db` : 최초 실행 또는 테스트 시 생성되는 로컬 공용 SQLite DB이며 GitHub에는 포함하지 않음
- `models/` : RF 모델 파일 위치  — 실제 .joblib 파일은 저장소에 포함하지 않음 

## 2. 필수 모델 파일
다음 두 파일을 `models/`에 넣어야 초기 선별 앱의 RF 추론이 동작합니다.
- `suicide_attempt_rf_tuned.joblib`
- `suicide_attempt_features.joblib`

## 3. 설치
```bash
pip install -r requirements.txt
```

## 4. 통합 테스트 데이터 생성
프로젝트 최상위 폴더에서:
```bash
python tests/integration_test_seed.py
```

## 5. 실행
각각 별도 터미널에서:
```bash
streamlit run apps/screening_app.py
streamlit run apps/student_checkin_app.py
streamlit run apps/teacher_dashboard.py
```

## 6. 통합 테스트 시나리오
- TEST-001: RF 추천 + Safety Plan + 오늘 체크인 + 최근 악화 + 빠른 확인 필요
- TEST-002: RF 추천 + Safety Plan + 오늘 미응답 + 리마인드 설정
- TEST-003: 전문가 추가 + Safety Plan/연락처 미등록
- TEST-004: 지속관리 미포함
- TEST-005: 지속관리 미포함

## 7. 주의
- 본 시스템은 프로토타입이며 자동 임상판정 도구가 아닙니다.
- RF 결과는 전교생 내 상대적 검토 우선순위 지원에 사용됩니다.
- 실제 SMS API는 연결하지 않았으며, 현재는 리마인드 필요 여부 및 발송 기록 관리까지 구현되어 있습니다.
