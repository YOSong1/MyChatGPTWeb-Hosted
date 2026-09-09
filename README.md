# MyChatGPTWeb

OpenAI API Key만 입력하면 ChatGPT처럼 대화할 수 있는 로컬 실행 웹 앱.
설계 문서: `plan1.md`(화면·기능), `plan2.md`(배포·빌드).

## 개발 환경에서 실행 (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app\main.py
```

브라우저에서 `http://localhost:8765` 접속.
환경변수 `OPENAI_API_KEY`에 키가 있으면 키 입력 화면을 건너뛴다.

## 실행 파일 빌드 (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File build\build_win.ps1 -Version 1.0.0            # 폴더 형태
powershell -ExecutionPolicy Bypass -File build\build_win.ps1 -Version 1.0.0 -OneFile   # 단일 exe
```

산출물은 `dist\` 아래 zip. 빌드 검증은 `dist\MyChatGPTWeb\MyChatGPTWeb.exe --selftest`.
macOS 빌드는 GitHub Actions의 "Build executables" 워크플로를 수동 실행해서 받는다(`.github/workflows/build.yml`).

## 데이터 저장 위치

| OS | 경로 |
|---|---|
| Windows | `%APPDATA%\MyChatGPTWeb\` |
| macOS | `~/Library/Application Support/MyChatGPTWeb/` |

- `config.json`: API Key(기억하기 선택 시), 모델, 시스템 프롬프트
- `conversations.json`: 대화 기록

## 진행 상태

- [x] 1단계 앱 뼈대: 키 입력 화면, 저장소, 채팅 화면 레이아웃
- [x] 2단계 채팅 기능: 키 서버 검증, OpenAI 스트리밍 응답, 모델 선택, 오류 시 다시 시도
- [x] 3단계 대화 관리·설정: 시스템 프롬프트, temperature, 기록 개수, 제목 수정, 다시 생성, 내보내기/가져오기
- [x] 4단계 런처: `python launcher.py` 로 서버 기동과 브라우저 자동 열기, 중복 실행 감지
- [x] 5단계 Windows 빌드: PyInstaller spec, 훅, 빌드 스크립트, `--selftest` 자체 점검
- [ ] 6단계 GitHub Actions 빌드 (macOS 포함): 워크플로 작성 완료. 비공개 저장소에 올린 뒤 수동 실행 필요
- [ ] 7단계 배포·안내문: `docs/학생안내.md` 초안 작성. 시험 배포 후 보완
