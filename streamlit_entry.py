# Streamlit이 실행할 진입 스크립트. 실제 코드는 app 패키지 안에 있다.
# 빌드 시 이 파일만 평문으로 포함되고 app 패키지는 실행 파일 내부에 컴파일되어 들어간다.
from app.main import main

main()
