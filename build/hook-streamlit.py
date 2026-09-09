"""PyInstaller용 Streamlit 훅.

- static/ 프런트엔드 파일과 기타 데이터 포함
- 동적으로 import되는 하위 모듈 전부 포함
- importlib.metadata로 버전을 확인하는 패키지들의 메타데이터 포함
"""

from importlib.metadata import PackageNotFoundError, requires
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = collect_data_files("streamlit")
hiddenimports = collect_submodules("streamlit")

# streamlit 자신과 그 의존 패키지의 메타데이터. 없으면 실행 직후 "Package not found"로 죽는다.
_pkgs = {"streamlit"}
for req in requires("streamlit") or []:
    name = req.split(";")[0].split(" ")[0].split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
    if name:
        _pkgs.add(name)
for _p in sorted(_pkgs):
    try:
        datas += copy_metadata(_p)
    except PackageNotFoundError:
        pass
