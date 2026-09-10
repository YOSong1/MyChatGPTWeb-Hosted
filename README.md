# MyChatGPTWeb (호스팅판)

관리자가 서버에 한 번 올려 두고, 학생은 URL로 접속해 **자기 OpenAI API Key**를 입력해 ChatGPT처럼 대화하는 웹 앱.
로컬 실행판(`MyChatGPTWeb`)의 복사본이며, 여러 접속자가 한 서버를 같이 쓰도록 저장 방식을 바꿨다.
설계 문서: `plan3.md`(호스팅판), `plan1.md`(화면·기능), `plan2.md`(로컬 실행판).

## 핵심 원칙
- 키·설정·대화는 접속자의 **세션 메모리**에만 둔다. 서버 디스크에 쓰지 않는다.
- 서버의 환경변수 키는 사용하지 않는다.
- 탭을 닫거나 새로고침하면 키와 대화가 사라진다. 보관은 "⚙️ 설정 → 📤 대화 내보내기"로.
- 답변이 만든 파일은 서버 임시 폴더에 세션별로 두고 6시간 뒤 지운다.

## 로컬에서 실행해 보기
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app\main.py
```

## 배포
- **Streamlit Community Cloud**: https://share.streamlit.io 에서 이 저장소를 연결. 메인 파일 `app/main.py`, Python 3.12. 절차는 `plan3.md` 3.1절.
- **VPS / Docker**:
  ```
  docker build -t mychatgptweb-hosted .
  docker run -d --restart unless-stopped -p 8501:8501 mychatgptweb-hosted
  ```
  앞단에 Caddy 등으로 HTTPS를 붙인다.

## 기능
- 스트리밍 대화, 여러 대화 관리, 제목 수정, 다시 생성
- 모델 선택 (최신 모델 포함, 채팅용만 필터)
- 🌐 웹 검색 (출처 표시), 📎 파일 생성 (pptx, docx, xlsx, pdf, py 등 다운로드), 코드 블록 저장
- 설정: 시스템 프롬프트, temperature, 기록 개수, 대화 내보내기/가져오기
