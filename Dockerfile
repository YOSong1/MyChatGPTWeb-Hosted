# VPS나 자체 서버에 올릴 때 사용. Streamlit Community Cloud에서는 필요 없다.
#   docker build -t mychatgptweb-hosted .
#   docker run -d --restart unless-stopped -p 8501:8501 mychatgptweb-hosted
# 앞단에 Caddy/Nginx 등으로 HTTPS를 붙인다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .streamlit ./.streamlit

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
