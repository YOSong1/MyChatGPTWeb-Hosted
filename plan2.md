# MyChatGPTWeb 설계서 (plan2) — 로컬 실행 파일 배포판

> plan1의 화면 설계와 기능 요구사항을 유지하면서, **Python + Streamlit으로 구현하고 OS별 단일 실행 파일로 배포**하는 방식의 설계서.
> 학생은 파일 하나를 받아 더블클릭하면 브라우저에 채팅 화면이 열린다. 소스 코드는 배포물에 노출되지 않는다.

작성일: 2026-09-10
버전: v1 (초안)
관련 문서: plan1.md (화면 흐름, 기능 범위, 데이터 구조는 plan1을 따른다)

---

## 1. 배포 요구사항 정리

| 요구 | 내용 |
|---|---|
| 실행 환경 | 학생 각자의 로컬 PC. Windows와 macOS 모두 지원 |
| 코드 노출 | 학생이 소스 코드를 쉽게 열어보거나 수정할 수 없어야 함 |
| 설치 부담 | 별도 런타임(Python, Node, Docker) 설치 없이 실행 가능해야 함 |
| 키 보관 | 학생 API Key는 학생 PC에만 저장. 관리자 서버로 전송하지 않음 |
| 서버 운영 | 관리자가 상시 운영하는 서버는 없음 |

---

## 2. 배포 방식 비교와 결정

### 2.1 후보 비교

| 방식 | 학생 설치 부담 | 코드 은닉 수준 | 빌드 난이도 | 결정 |
|---|---|---|---|---|
| A. PyInstaller 실행 파일 | 낮음. 더블클릭 | 중간. 바이트코드 추출은 가능하나 원본 복원은 어려움 | 중간. OS별 빌드 필요 | **주력** |
| B. Docker 이미지 | 높음. Docker Desktop 설치, Windows는 WSL2 필요 | 낮음. `docker cp`로 파일 추출 가능 | 낮음 | 보조 |
| C. Electron | 낮음 | 낮음. asar는 단순 아카이브 | 높음. Python까지 동봉해야 함 | 제외 |
| D. Nuitka 컴파일 | 낮음 | 높음. C로 컴파일됨 | 높음. 빌드 시간 길고 환경 까다로움 | 은닉 강화가 필요할 때 A에서 승격 |

### 2.2 결정 (확정)
- **A. PyInstaller**로 확정한다. 학생에게는 Windows용과 macOS용 실행 파일을 모두 제공한다.
- **D. Nuitka**는 코드 은닉 요구가 강해질 때의 전환 경로로만 남긴다. 소스 변경 없이 빌드 명령만 바뀐다.
- B. Docker와 C. Electron은 채택하지 않는다. Docker는 실행 파일이 정책상 차단된 환경이 실제로 확인될 때만 다시 검토한다.

### 2.3 코드 은닉에 대한 현실적 기준
- 관리자는 원본 소스를 보관한다. 여기서 말하는 "복원"은 **학생이 실행 파일을 뜯어 원본 `.py`를 되살리는 행위**를 뜻한다.
- 학생이 exe를 뜯을 때 벌어지는 단계
  1. 실행 파일에서 내부 파일을 꺼낸다. 공개 도구로 가능하며 막을 수 없다.
  2. 꺼낸 파일은 `.py`가 아니라 바이트코드 `.pyc`이다. 사람이 그대로 읽을 수 없다.
  3. `.pyc`를 `.py`로 되돌리는 디컴파일러는 Python 3.12 기준으로 신뢰할 만한 것이 없다. 따라서 **원본 소스 그 모습으로는 볼 수 없다.**
  4. 바이트코드를 명령어 목록으로 풀어보는 것은 가능하다. 함수 이름, 변수 이름, 문자열(시스템 프롬프트, URL)과 대략의 흐름은 알아낼 수 있다.
- PyInstaller 6부터 바이트코드 암호화 옵션(`--key`)이 제거되었으므로 이에 의존하지 않는다.
- 결론: "학생이 원본 소스를 그대로 볼 수 없게 한다"는 목표는 PyInstaller + Python 3.12로 달성된다. 문자열로 들어가는 값은 어떤 방식이든 찾아낼 수 있으므로, 학생에게 숨겨야 할 값은 코드에 직접 적지 않는다.
- Streamlit은 UI 로직이 전부 Python 쪽에 있어 브라우저 개발자 도구로는 우리 코드가 보이지 않는다. 이 점이 plan1의 순수 JS 방식 대비 가장 큰 장점이다.

---

## 3. 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.12 | 디컴파일러 부재로 은닉에 유리. PyInstaller와 Streamlit 모두 안정 지원 |
| UI | Streamlit 1.63 | `st.chat_message`, `st.chat_input`, `st.write_stream`으로 스트리밍 채팅이 짧게 구현됨. UI 코드가 브라우저에 노출되지 않음 |
| OpenAI 호출 | `openai` 공식 SDK 3.x | 스트리밍, 오류 타입 처리가 정리되어 있음 |
| 설정·대화 저장 | 사용자 홈 폴더의 JSON 파일 | 서버 없이 영속화. 실행 파일과 분리되어 재설치해도 유지 |
| 패키징 | PyInstaller 6.x | 단일 파일(onefile)과 폴더(onedir) 두 형태 생성 |
| 빌드 머신 | GitHub Actions (windows-latest, macos-latest, macos-13) | PyInstaller는 교차 빌드가 안 되므로 macOS용은 Mac에서만 만들어짐. 관리자 PC나 Mac 없이 세 종류를 한 번에 생성 |
| 배포 경로 | Google Drive 공유 링크 | 서버 없이 파일만 전달 |

### 3.1 Streamlit의 한계와 대응
| 한계 | 대응 |
|---|---|
| 입력마다 스크립트 전체가 재실행됨 | 대화 목록·설정은 `st.session_state`와 JSON 파일에 두고, 재실행 시 복원 |
| 응답 중 "중지" 버튼 구현이 어색함 | v1에서는 중지 기능을 제외하거나, 스트리밍 루프 안에서 `st.session_state.stop` 플래그를 확인하는 방식으로 근사 구현 |
| 사이드바 대화 목록의 세밀한 상호작용 제한 | 대화 선택은 라디오/버튼, 삭제는 확인 버튼으로 단순화 |
| PyInstaller와 패키징 궁합이 까다로움 | 4.2절의 검증된 절차를 따른다. 막히면 NiceGUI로 UI만 교체 (7절 참조) |

---

## 4. 애플리케이션 구조

### 4.1 파일 구조
```
MyChatGPTWeb/
├── app/                   # 앱 본체. 빌드 시 바이트코드로 실행 파일 안에 들어간다(평문 .py 없음)
│   ├── main.py            # 화면 전환 (키 화면 / 채팅 화면)
│   ├── openai_client.py   # 키 검증, 모델 필터, 스트리밍 호출. base URL 상수 한 곳
│   ├── storage.py         # 홈 폴더 JSON 읽기·쓰기 (키, 설정, 대화)
│   ├── models.py          # Conversation, Message, Settings 데이터 클래스
│   └── ui/
│       ├── key_screen.py  # 키 입력 화면
│       ├── chat_screen.py # 채팅 화면 (사이드바, 메시지, 다시 생성)
│       └── settings.py    # 설정 패널, 내보내기/가져오기
├── streamlit_entry.py     # Streamlit이 파일로 읽는 2줄짜리 진입 스크립트. 빌드에 평문으로 들어가는 유일한 .py
├── launcher.py            # 실행 파일 진입점. 포트 탐색, 서버 기동, 브라우저 열기, --selftest
├── build/
│   ├── build.spec         # PyInstaller spec (onedir / onefile, macOS .app)
│   ├── hook-streamlit.py  # Streamlit 데이터·하위 모듈·메타데이터 수집 훅
│   ├── build_win.ps1      # Windows 빌드 스크립트
│   └── build_mac.sh       # macOS 빌드 스크립트
├── .github/workflows/
│   └── build.yml          # Windows·macOS(arm64, x64) 3종을 GitHub 러너에서 빌드 + 자체 점검
├── .streamlit/config.toml # 개발 실행용 설정 (포트, localhost 바인딩)
├── docs/
│   └── 학생안내.md         # 학생용 설치·사용 안내 (Drive에 PDF로 함께 배포)
├── requirements.txt
├── plan1.md
├── plan2.md
└── README.md              # 개발자용 실행·빌드 안내
```

코드 은닉 구조: Streamlit은 진입 스크립트를 "파일"로 읽어야 하므로 `streamlit_entry.py`만 평문으로 포함한다. 이 파일은 `from app.main import main; main()` 두 줄뿐이고, 실제 로직인 `app` 패키지는 PyInstaller의 PYZ 아카이브 안에 바이트코드로 들어간다. 빌드 결과 폴더에서 `.py`를 찾으면 `streamlit_entry.py` 하나만 나오는 것을 확인했다.

### 4.2 실행 파일 진입점 (`launcher.py`) 동작
1. 이미 실행 중인지 확인한다. 고정 포트(기본 8765)가 열려 있으면 브라우저만 다시 연다.
2. 빈 포트를 찾는다. 기본 포트가 사용 중이면 다음 포트를 쓴다.
3. `streamlit.web.bootstrap.run()`으로 서버를 같은 프로세스 안에서 띄운다. 서브프로세스로 `streamlit run`을 부르지 않는다. 실행 파일 내부에는 `streamlit` 명령이 없기 때문이다.
4. 서버 준비 후 `webbrowser.open("http://localhost:<port>")`로 기본 브라우저를 연다.
5. 콘솔 창에는 "브라우저가 열리지 않으면 이 주소로 접속하세요"와 "종료하려면 이 창을 닫으세요"만 출력한다.
6. Streamlit 텔레메트리, 파일 감시, 자동 재실행은 모두 끈다.

### 4.3 데이터 저장 위치
| OS | 경로 |
|---|---|
| Windows | `%APPDATA%\MyChatGPTWeb\` |
| macOS | `~/Library/Application Support/MyChatGPTWeb/` |

파일 구성:
- `config.json`: `{ api_key, model, system_prompt, temperature, remember_key }`
- `conversations.json`: plan1 5.2절의 `Conversation[]` 구조
- `remember_key`가 false이면 `api_key`를 파일에 쓰지 않고 세션 메모리에만 둔다. 프로그램을 끄면 사라진다.

### 4.4 화면 흐름
plan1 4절과 동일하다. 차이점만 적는다.
- 키 결정 순서: **1) 환경변수 `OPENAI_API_KEY` → 2) `config.json`에 저장된 키 → 3) 키 입력 화면.** 환경변수 키는 파일에 저장하지 않는다.
- 키 입력 화면에는 환경변수로 등록하면 이 화면을 건너뛴다는 안내와 OS별 등록 방법을 함께 보여준다. 단, macOS에서 Finder로 실행한 앱은 셸 환경변수를 읽지 못하므로 안내에 명시한다.
- 환경변수 키를 쓰는 중에는 설정 패널의 버튼이 "다른 키 입력"으로 바뀌고, 누르면 이번 실행에 한해 환경변수를 무시하고 키 화면을 보여준다. 환경변수 키가 무효(401)이면 키 화면으로 넘어가며 경고를 표시한다.
- 키 검증은 `openai.OpenAI(api_key=key).models.list()` 호출로 한다. `AuthenticationError`, `RateLimitError`, `APIConnectionError`를 각각 다른 문구로 보여준다.
- 채팅 화면의 사이드바에 "새 대화", 대화 목록, "설정", "키 삭제"를 배치한다.
- 응답은 `st.write_stream()`에 SDK의 스트림 제너레이터를 넘겨 표시하고, 완료된 텍스트를 대화에 저장한다.

---

## 5. 빌드 파이프라인

### 5.1 로컬 빌드 (개발 중 확인용)
Windows:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller build\build.spec
```
macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pyinstaller
pyinstaller build/build.spec
```
- Windows용은 Windows에서, macOS용은 macOS에서만 빌드된다. 교차 빌드는 불가능하다.

### 5.2 PyInstaller spec 핵심 설정
- `hiddenimports`: `streamlit.runtime.scriptrunner.magic_funcs`, `openai`, `tiktoken_ext.openai_public` 등 동적 임포트 모듈
- `datas`: Streamlit의 `static/` 폴더와 `runtime/` 리소스, 앱의 `app/` 폴더 전체
- `copy_metadata`: `streamlit`, `openai`, `altair`, `pandas` 등 `importlib.metadata`를 읽는 패키지의 메타데이터. 누락되면 "Package not found" 오류로 실행 직후 종료된다.
- `hook-streamlit.py`: `collect_data_files("streamlit")`와 `collect_submodules("streamlit")`를 호출
- `console=True`: v1에서는 콘솔 창을 남긴다. 오류 확인과 종료 방법이 명확해진다. 안정화 후 `False`로 바꾼다.
- 두 가지 형태를 모두 만든다.
  - `onefile`: 배포가 간편. 첫 실행이 느리고 백신 오탐이 잦음
  - `onedir`: 폴더를 zip으로 배포. 실행이 빠르고 오탐이 적음

### 5.3 빌드는 GitHub Actions에서 (확정)
학생에게는 두 OS용을 모두 제공하되, **관리자는 Mac 없이 빌드한다.** PyInstaller는 교차 빌드가 안 되므로 macOS용은 GitHub가 제공하는 macOS 러너에서 만든다.

- 저장소는 비공개로 둔다. 비공개 저장소도 월 2,000분까지 무료이다. macOS 러너는 10배 가중이라 실질 약 200분이고, 빌드 1회에 10~15분이 든다. 한 달에 10회 안팎 빌드가 가능하며 v1 개발에는 충분하다.
- 트리거는 수동 실행(`workflow_dispatch`)으로 둔다. GitHub 웹 화면에서 "Run workflow" 버튼을 누르면 된다.
- 매트릭스: `windows-latest`, `macos-latest`(Apple Silicon), `macos-13`(Intel). Windows도 러너에서 빌드해 관리자 PC 상태와 무관하게 재현 가능한 결과를 얻는다.
- 산출물은 Actions 실행 페이지의 Artifacts에서 zip 3개를 내려받아 Google Drive에 올린다.
- 개발 중 빠른 확인용으로는 관리자 Windows PC에서 `build_win.ps1`을 직접 돌린다. 5.1절의 로컬 빌드는 이 용도이다.

집에 있는 Mac의 역할:
- 빌드에는 쓰지 않는다.
- 6단계에서 Actions가 만든 macOS zip을 한 번 내려받아 실행되는지, Gatekeeper 안내 절차가 맞는지 확인하는 용도로만 잠시 쓴다. Mac을 가진 학생이 대신 확인해 줄 수 있으면 그것으로 충분하다.

산출물 이름 규칙 (어느 방법이든 동일):
- `MyChatGPTWeb-1.0.0-windows-x64.zip`
- `MyChatGPTWeb-1.0.0-macos-arm64.zip`
- `MyChatGPTWeb-1.0.0-macos-x64.zip`

### 5.4 macOS 아키텍처
- Apple Silicon 빌드는 Intel Mac에서 실행되지 않는다.
- Intel 빌드는 Apple Silicon에서 Rosetta로 실행된다. 빌드를 하나로 줄이고 싶다면 Intel 빌드만 배포해도 된다. 다만 Rosetta 설치를 요구하는 팝업이 한 번 뜬다.
- v1에서는 두 가지를 모두 제공하고, 안내문에 "Apple 메뉴 > 이 Mac에 관하여"로 칩 종류를 확인하는 방법을 넣는다.

### 5.5 Google Drive 배포
1. 빌드 산출물 3개(Windows, macOS arm64, macOS x64)를 Drive의 배포 폴더에 올린다.
2. 폴더 공유를 "링크가 있는 모든 사용자 - 뷰어"로 설정하고 폴더 링크만 학생에게 전달한다.
3. 버전이 바뀌면 파일 이름에 새 버전을 붙여 올리고, 이전 버전은 `old/` 하위 폴더로 옮긴다. 링크는 바뀌지 않는다.
4. 학생용 안내문(README를 PDF로 변환)도 같은 폴더에 둔다.

주의점:
- 100MB가 넘는 파일은 Drive가 "바이러스 검사를 할 수 없습니다" 경고를 띄운다. "그래도 다운로드"로 받을 수 있으며 안내문에 한 줄 적는다.
- Chrome이 exe가 든 zip을 받을 때 "일반적으로 다운로드되지 않는 파일" 경고를 낼 수 있다. "계속" 절차를 안내문에 넣는다.
- macOS용 `.app`은 반드시 zip으로 묶어 올린다. 폴더째 올리면 실행 권한이 깨진다.
- 폴더 하나에 여러 명이 동시에 받으면 Drive가 일시적으로 다운로드를 제한할 수 있다. 수업 직전 일괄 배포보다는 하루 전에 링크를 공유한다.

---

## 6. 학생 설치 경험과 걸림돌

### 6.1 학생이 하는 일
1. zip을 받아 압축을 푼다.
2. Windows: `MyChatGPTWeb.exe` 더블클릭. macOS: `MyChatGPTWeb.app` 실행.
3. 브라우저가 자동으로 열린다. 첫 화면에서 API Key를 입력한다.
4. 종료할 때는 검은 콘솔 창을 닫는다.

### 6.2 반드시 안내문에 넣어야 할 경고 대응
| 상황 | 학생이 할 일 |
|---|---|
| Windows SmartScreen "알 수 없는 게시자" | "추가 정보" 클릭 후 "실행" |
| macOS "확인되지 않은 개발자" (macOS 14 이하) | 앱을 우클릭 후 "열기" |
| macOS 15 이상 | 한 번 실행 시도 후 "시스템 설정 > 개인정보 보호 및 보안"에서 "그래도 열기" |
| macOS "손상되었기 때문에 열 수 없습니다" | 터미널에서 `xattr -cr MyChatGPTWeb.app` 실행 |
| 백신이 파일을 격리함 | onedir 버전을 대신 사용. 그래도 막히면 관리자에게 예외 등록 요청 |
| 브라우저가 열리지 않음 | 콘솔 창에 표시된 `http://localhost:8765` 를 직접 입력 |

### 6.3 코드 서명 (선택)
- 서명이 없으면 위 경고는 사라지지 않는다.
- macOS: Apple Developer Program(연 99달러) 가입 후 서명과 공증. CI에 인증서를 등록하면 자동화된다.
- Windows: 코드 서명 인증서 구매(연 수십만 원대). EV 인증서가 아니면 SmartScreen 평판이 쌓일 때까지 경고가 남는다.
- v1에서는 서명하지 않고 안내문으로 대응한다. 학생 수가 많아지거나 문의가 잦으면 macOS 공증부터 도입한다.

### 6.4 예상 수치
| 항목 | 값 |
|---|---|
| 실행 파일 크기 | 200~300MB |
| 첫 실행 시간 (onefile) | 5~10초 |
| 첫 실행 시간 (onedir) | 2~4초 |
| 학생 PC 요구 | Windows 10 이상 64비트, macOS 12 이상 |

---

## 7. 대안 경로

### 7.1 실행 파일이 정책상 차단된 환경
- 학교 PC에서 exe 실행이 막혀 있는 경우가 확인되면 그때 Docker 이미지 또는 plan1의 웹 호스팅 방식을 검토한다.
- v1에서는 준비하지 않는다.

### 7.2 Streamlit 패키징이 막힐 때: NiceGUI
- NiceGUI는 PyInstaller 패키징을 공식 문서로 지원하고 `native=True` 옵션으로 브라우저 없이 자체 창을 띄울 수 있다.
- 웹소켓 기반이라 재실행 모델이 없어 "중지" 버튼과 스트리밍 제어가 자연스럽다.
- 채팅 UI 컴포넌트는 Streamlit보다 직접 만들 부분이 많다.
- `openai_client.py`, `storage.py`, `models.py`는 그대로 재사용하고 `ui/`만 교체한다.

### 7.3 은닉 강화: Nuitka
```
python -m nuitka --standalone --onefile --enable-plugin=... launcher.py
```
- 소스 변경 없이 빌드 명령만 바꾼다.
- 빌드 시간이 10~30분으로 길고 C 컴파일러(MSVC, Xcode)가 필요하다.
- Streamlit 데이터 파일 포함 설정은 PyInstaller와 별도로 다시 잡아야 한다.

---

## 8. 개발 단계 (진행 방향)

| 단계 | 산출물 | 완료 기준 |
|---|---|---|
| 1. 앱 뼈대 ✅ (2026-09-10 완료) | `app/main.py`, `storage.py`, `models.py`, 키 화면, 채팅 화면 레이아웃 | `streamlit run`으로 키 입력 후 빈 채팅 화면 진입 |
| 2. 채팅 기능 ✅ (2026-09-10 완료) | `openai_client.py`, 채팅 화면, 사이드바 모델 선택 | 질문하면 스트리밍으로 답이 나오고 대화가 파일에 저장됨 |
| 3. 대화 관리·설정 ✅ (2026-09-10 완료) | 사이드바, 설정 패널(`ui/settings.py`), 제목 수정, 다시 생성, 내보내기/가져오기 | 새 대화, 전환, 삭제, 모델 변경, 키 삭제 동작 |
| 4. 런처 ✅ (2026-09-10 완료) | `launcher.py` | `python launcher.py`로 서버 기동과 브라우저 자동 열기 |
| 5. Windows 빌드 ✅ (2026-09-10 빌드·자체 점검 완료, 타 PC 확인은 미완) | `build.spec`, `hook-streamlit.py`, `build_win.ps1`, `launcher.py --selftest` | 다른 Windows PC(Python 미설치)에서 exe 실행 성공 |
| 6. GitHub Actions 빌드 | `build.yml`, `build_mac.sh` | Actions 수동 실행으로 3종 zip 생성. Python 미설치 Apple Silicon Mac과 Intel Mac에서 app 실행 성공. Gatekeeper 우회 절차 확인 |
| 7. 배포·안내문 | `README.md`, Google Drive 배포 폴더 | 학생 2~3명(Windows, Mac 각 1명 이상)에게 시험 배포 후 안내문 보완 |

- 5단계가 이 계획의 최대 위험 구간이다. 1~3단계 완료 직후 5단계를 먼저 시도해 패키징 가능 여부를 조기에 확인한다.
- 5단계에서 이틀 이상 막히면 7.2절 NiceGUI로 전환한다.
- 6단계의 macOS 빌드는 GitHub Actions에서만 만든다. 실행 확인은 집의 Mac 또는 Mac을 가진 학생 한 명에게 zip을 보내 진행한다.
- 1~5단계는 관리자 Windows PC만으로 진행 가능하다. GitHub 저장소는 6단계 직전에 만들어도 된다.

---

## 9. 테스트 체크리스트

배포 관련 항목만 적는다. 기능 테스트는 plan1 10절을 따른다.

- [ ] Python이 설치되지 않은 Windows 10, 11 PC에서 exe 실행
- [ ] Python이 설치되지 않은 Apple Silicon Mac, Intel Mac에서 app 실행
- [ ] 두 번 더블클릭해도 서버가 하나만 뜨고 브라우저 탭만 추가됨
- [ ] 8765 포트가 사용 중일 때 다른 포트로 기동
- [ ] 콘솔 창을 닫으면 서버가 종료됨
- [ ] 재실행 후 대화와 설정이 유지됨
- [ ] "기억하기" 해제 상태에서 재실행 시 키 입력 화면이 다시 나옴
- [ ] 인터넷이 끊긴 상태에서 실행 시 앱은 뜨고 키 검증 단계에서만 오류 안내
- [ ] Windows Defender 기본 설정에서 onefile, onedir 모두 격리되지 않음
- [ ] macOS 15에서 안내문 절차대로 실행 성공
- [ ] Google Drive 링크에서 로그인 없는 계정으로 3종 zip 다운로드 성공
- [ ] Drive에서 받은 macOS zip을 풀었을 때 app이 정상 실행됨 (실행 권한 유지 확인)

---

## 10. plan1 대비 변경 요약

| 항목 | plan1 | plan2 |
|---|---|---|
| 구현 언어 | HTML/CSS/JS | Python + Streamlit |
| 실행 방식 | 정적 웹 호스팅 | 학생 PC 로컬 실행 파일 |
| 코드 노출 | 브라우저에서 전부 보임 | 실행 파일 내부. 브라우저에는 노출 안 됨 |
| 저장소 | 브라우저 localStorage | 사용자 홈 폴더 JSON |
| OpenAI 호출 | 브라우저에서 직접 | 로컬 Python 프로세스에서 |
| 배포 경로 | 웹 호스팅 URL | Google Drive 공유 폴더 |
| 관리자 서버 | 없음 | 없음 |
| 유지되는 것 | 화면 흐름, 기능 범위, 데이터 구조, 키 검증 방식 | |

---

## 11. 확정된 사항과 열린 질문

### 11.1 확정
- 배포 방식: A. PyInstaller 실행 파일
- 기술 스택: 3절 그대로 (Python 3.12 + Streamlit + openai SDK)
- Docker: 제외
- 배포 경로: Google Drive 공유 폴더
- 학생 제공 파일: Windows용 1종, macOS용 2종(Apple Silicon, Intel)
- 빌드 머신: GitHub Actions. 관리자는 Mac 없이 빌드한다. 집의 Mac은 실행 확인에만 잠시 사용
- 개발 시작점: 8절 1단계(앱 뼈대)부터 순서대로 진행

### 11.2 열린 질문 (사용자 확인 필요)
1. 학생 중 Intel Mac 사용자가 있는가? (없으면 arm64 빌드만 제공해 배포 파일을 2종으로 줄일 수 있음)
2. 학교 PC에 관리자 권한 없이 exe 실행이 허용되는가? (차단되면 7.1절 경로 검토)
3. macOS 공증 비용(연 99달러)을 감당할 의사가 있는가? (있으면 Mac 안내문이 크게 단순해짐)
4. "중지" 버튼이 v1에 꼭 필요한가? (Streamlit에서는 구현이 어색하므로 제외를 권장)
5. GitHub 계정이 있는가? (없으면 6단계 전에 무료 계정을 만들어야 함)
