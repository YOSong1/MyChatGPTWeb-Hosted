# MyChatGPTWeb 설계서 (plan3) — 호스팅판

> 관리자가 한 번 배포해 두고 학생은 **URL로 접속해 자기 API Key를 입력**해 쓰는 버전.
> 로컬 실행판(`C:\WorkAI\MyChatGPTWeb`, plan2)은 그대로 유지하고, 이 폴더(`MyChatGPTWeb-Hosted`)는 그 복사본에서 출발했다.

작성일: 2026-09-10
관련 문서: plan1.md(화면·기능), plan2.md(로컬 실행판 배포)

---

## 1. 로컬 실행판과의 차이

| 항목 | 로컬 실행판 (plan2) | 호스팅판 (이 문서) |
|---|---|---|
| 실행 위치 | 학생 PC의 exe/app | 관리자가 올린 서버 하나 |
| 학생 설치 | zip 받아 실행 | 없음. URL 접속 |
| 키 보관 | 학생 PC 파일 또는 환경변수 | 접속자 세션 메모리에만. 서버 디스크에 쓰지 않음 |
| 대화 보관 | 학생 PC 파일. 재시작 후 유지 | 세션 메모리. **탭을 닫거나 새로고침하면 사라짐** |
| 생성 파일 | 학생 PC 데이터 폴더 | 서버 임시 폴더(세션별). 6시간 뒤 자동 삭제 |
| 코드 노출 | 실행 파일 안에 바이트코드 | 서버에만 있음. 학생에게 아무것도 내려가지 않음 |
| 키 경로 | 학생 PC → OpenAI | 학생 브라우저 → 관리자 서버 → OpenAI (HTTPS 필수) |
| 서버 환경변수 키 | 있으면 사용 | **절대 사용하지 않음** (관리자 키 노출 방지) |

## 2. 코드 변경 요약

- `app/storage.py`: 파일 대신 `st.session_state`에 설정·대화를 둔다. `env_api_key()`는 항상 빈 문자열. 생성 파일은 `<시스템 temp>/mychatgptweb-hosted/<세션 id>/<대화 id>/`에 두고, 세션마다 한 번 6시간 넘은 폴더를 지운다.
- `app/ui/key_screen.py`: "기억하기" 체크박스와 환경변수 안내 제거. 키가 저장되지 않는다는 안내와 "대화 내보내기" 권장 문구 추가.
- `app/ui/settings.py`: 저장 위치·키 출처 표시 제거.
- `app/main.py`: 환경변수·파일 키 조회 제거. 세션에 키가 있을 때만 채팅 화면.
- `launcher.py`, `build/`, `.github/workflows/build.yml`, `streamlit_entry.py` 삭제. 호스팅에는 필요 없다.
- `Dockerfile` 추가 (VPS 배포용).
- `app/openai_client.py`, `app/models.py`, `app/ui/chat_screen.py`는 로컬판과 동일. 두 프로젝트에 같은 수정을 적용할 때 이 세 파일은 그대로 복사하면 된다.

## 3. 배포 대상

### 3.1 Streamlit Community Cloud (1차 추천)
- 무료. GitHub 비공개 저장소를 연결하면 `https://<이름>.streamlit.app` 주소가 생긴다.
- 배포 절차 (관리자가 브라우저에서 진행)
  1. https://share.streamlit.io 에 GitHub 계정으로 로그인
  2. "Create app" → "Deploy a public app from GitHub" → 저장소 `YOSong1/MyChatGPTWeb-Hosted`, 브랜치 `main`, 메인 파일 `app/main.py`
  3. "Advanced settings"에서 Python 3.12 선택
  4. Deploy. 2~3분 뒤 주소가 나온다.
  5. 앱 설정(Settings → Sharing)에서 "Who can view this app"을 **Only specific people**로 바꾸고 학생 이메일을 등록하면 학생만 입장할 수 있다. 무료 계정은 비공개 앱 1개까지다.
- 잠자기: 며칠 접속이 없으면 잠든다. 누구든 접속해 "Yes, get this app back up!"을 누르면 30초~1분 뒤 깨어난다. 수업 전 관리자가 한 번 접속해 두면 학생은 대기 없이 들어온다.
- 잠들거나 재배포되면 메모리가 비워지므로 세션 대화는 사라진다. 이 설계에서는 원래 탭을 닫으면 사라지므로 추가 손실은 없다.
- 자원: 1GB 메모리. 학급 30명 동시 사용은 문제없다(호출은 대부분 OpenAI 대기 시간).

### 3.2 VPS + Docker (2차)
- 잠들지 않고 디스크가 영구적이라 나중에 로그인 기반 대화 보존을 붙이기 쉽다.
- `docker build -t mychatgptweb-hosted . && docker run -d --restart unless-stopped -p 8501:8501 mychatgptweb-hosted`
- 앞단에 Caddy를 두면 도메인만 적어도 HTTPS가 자동으로 붙는다.
- 월 5~10달러. Oracle Cloud 무료 티어나 집 PC + Cloudflare Tunnel로 0원도 가능.

## 4. 대화 보존 (다음 단계, 선택)

지금 설계는 "탭을 닫으면 대화가 사라진다". 보존이 필요해지면 두 가지를 더한다.
1. **Google 로그인**: Streamlit 내장 `st.login()`(OIDC). Google Cloud 콘솔에서 OAuth 클라이언트를 만들어 `secrets.toml`에 넣는다. 로그인 이메일이 접속자 id가 된다.
2. **외부 저장소**: Community Cloud는 디스크가 영구적이지 않으므로 Supabase(무료 티어) 같은 외부 DB에 이메일별로 대화를 저장한다. VPS라면 서버 디스크의 `<이메일>/` 폴더로 충분하다.

키는 로그인 후에도 저장하지 않는 것을 기본으로 한다. 저장하려면 서버 측 암호화가 필요하고, 그만큼 관리자 책임이 커진다.

## 5. 테스트 결과 (2026-09-10, AppTest)
- 서버 환경변수 `OPENAI_API_KEY`가 있어도 키 화면이 뜨고 그 키를 쓰지 않음
- 키 화면에 체크박스·환경변수 안내 없음
- 질문·답변, 파일 생성(📎 greeting.txt) 정상. 파일은 세션 임시 폴더에만 생성
- `%APPDATA%`에 아무 파일도 쓰지 않음
- 새 세션은 키 화면부터 시작
- 두 세션을 동시에 돌렸을 때 대화가 섞이지 않음

## 6. 열린 질문
1. Community Cloud로 시작할지, 처음부터 VPS로 갈지
2. 학생 이메일 허용 목록으로 입장을 제한할지 (Community Cloud 비공개 앱)
3. 대화 보존(Google 로그인 + 외부 DB)을 언제 붙일지
