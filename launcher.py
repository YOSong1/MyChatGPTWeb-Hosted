"""실행 파일 진입점. plan2 4.2절.

1. 같은 앱이 이미 떠 있으면 브라우저만 다시 연다.
2. 빈 포트를 찾아 Streamlit 서버를 같은 프로세스 안에서 띄운다.
3. 서버가 준비되면 기본 브라우저를 연다.
4. 콘솔 창을 닫으면 서버가 종료된다.

개발 중: python launcher.py
빌드 후: MyChatGPTWeb.exe / MyChatGPTWeb.app
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "MyChatGPTWeb"
DEFAULT_PORT = 8765
PORT_SEARCH_RANGE = 20
HOST = "localhost"


def base_dir() -> Path:
    """소스 실행이면 프로젝트 루트, PyInstaller 실행이면 임시 해제 폴더."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def main_script() -> Path:
    """Streamlit이 파일로 읽어 실행하는 진입 스크립트. app 패키지 본체는 import로 불러온다."""
    return base_dir() / "streamlit_entry.py"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def _is_our_app(port: int) -> bool:
    """해당 포트에 떠 있는 것이 Streamlit 서버인지 health 엔드포인트로 확인한다."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/_stcore/health", timeout=1) as r:
            return r.status == 200 and r.read().strip() == b"ok"
    except Exception:  # noqa: BLE001
        return False


def find_port() -> tuple[int, bool]:
    """(포트, 이미_실행중) 을 돌려준다."""
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_SEARCH_RANGE):
        if not _port_in_use(port):
            return port, False
        if _is_our_app(port):
            return port, True
    raise RuntimeError(f"{DEFAULT_PORT}~{DEFAULT_PORT + PORT_SEARCH_RANGE - 1} 포트를 모두 사용 중입니다.")


def open_browser_when_ready(port: int, timeout: float = 30.0) -> None:
    url = f"http://{HOST}:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_our_app(port):
            print(f"\n  브라우저를 엽니다: {url}")
            print("  브라우저가 열리지 않으면 위 주소를 직접 입력하세요.")
            print("  종료하려면 이 창을 닫으세요.\n")
            webbrowser.open(url)
            return
        time.sleep(0.3)
    print(f"\n  서버 준비를 기다리다 시간이 초과되었습니다. 브라우저에서 {url} 을 직접 열어 보세요.\n")


def run_streamlit(port: int) -> None:
    from streamlit import config as st_config
    from streamlit.web import bootstrap

    flag_options = {
        "server.port": port,
        "server.address": HOST,
        "server.headless": True,
        "server.runOnSave": False,
        "server.fileWatcherType": "none",
        "server.enableXsrfProtection": True,
        "browser.gatherUsageStats": False,
        "browser.serverAddress": HOST,
        "browser.serverPort": port,
        "global.developmentMode": False,
        "theme.base": "light",
    }
    bootstrap.load_config_options(flag_options)
    # load_config_options는 값이 None인 항목을 건너뛰므로 위 항목은 모두 명시값이다.
    assert st_config.get_option("server.port") == port

    script = str(main_script())
    os.chdir(str(base_dir()))
    bootstrap.run(script, False, [], flag_options)


def selftest() -> int:
    """번들 내부에서 화면 스크립트를 실제로 실행해 본다. 빌드 검증과 CI 스모크 테스트용.

    사용: MyChatGPTWeb.exe --selftest
    """
    import tempfile

    os.environ["MCW_DATA_DIR"] = tempfile.mkdtemp(prefix="mcw_selftest_")
    os.environ.pop("OPENAI_API_KEY", None)  # 빌드 머신의 키와 무관하게 키 화면을 검사한다
    os.chdir(str(base_dir()))
    try:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(main_script()), default_timeout=60).run()
        if at.exception:
            print("SELFTEST FAIL: 스크립트 예외")
            for e in at.exception:
                print(e.value)
            return 1
        titles = [t.value for t in at.title]
        if not titles or "API Key" not in titles[0]:
            print(f"SELFTEST FAIL: 키 화면이 아님: {titles}")
            return 1
        # 형식이 틀린 키를 넣어 검증 오류 문구까지 나오는지 본다.
        at.text_input[0].input("bad-key").run()
        at.button[0].click().run()
        if at.exception or not at.error:
            print("SELFTEST FAIL: 키 오류 문구 없음")
            return 1
        print(f"SELFTEST OK: {titles[0]} / {at.error[0].value}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"SELFTEST FAIL: {type(e).__name__}: {e}")
        return 1


def main() -> int:
    # 콘솔 인코딩이 한글을 못 다루는 환경에서도 죽지 않고, 안내 문구가 즉시 보이게 한다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass
    if "--selftest" in sys.argv:
        return selftest()
    print(f"=== {APP_NAME} ===")
    try:
        port, already = find_port()
    except RuntimeError as e:
        print(f"오류: {e}")
        input("아무 키나 누르면 종료합니다...")
        return 1

    if already:
        print(f"이미 실행 중입니다. 브라우저를 다시 엽니다: http://{HOST}:{port}")
        webbrowser.open(f"http://{HOST}:{port}")
        time.sleep(1.5)
        return 0

    if not main_script().exists():
        print(f"오류: 앱 파일을 찾을 수 없습니다: {main_script()}")
        input("아무 키나 누르면 종료합니다...")
        return 1

    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()
    try:
        run_streamlit(port)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
