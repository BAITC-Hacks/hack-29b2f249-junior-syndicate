FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    MONEY_GRAPH_DATA=/data \
    MONEY_GRAPH_OUTPUT=/state/output \
    MONEY_GRAPH_ACCOUNTS=/state/users.sqlite3

COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY app/ ./app/
COPY src/ ./src/
COPY config/ ./config/
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY run.py ./

RUN useradd --create-home --uid 10001 analyst && mkdir /state && chown analyst:analyst /state
USER analyst

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['STREAMLIT_SERVER_PORT'] + '/_stcore/health', timeout=4)"

CMD ["sh", "-c", "python run.py --data \"$MONEY_GRAPH_DATA\" --out \"$MONEY_GRAPH_OUTPUT\" && exec python -m streamlit run app/app.py"]
