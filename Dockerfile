FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRANSFERLENS_RUNTIME=local \
    AWS_REGION=us-east-1 \
    AWS_DEFAULT_REGION=us-east-1

WORKDIR /app

RUN useradd --create-home --uid 10001 transferlens

COPY pyproject.toml README.md ./
COPY transferlens ./transferlens
COPY policy ./policy
COPY fixtures/demo ./fixtures/demo
COPY fixtures/replay ./fixtures/replay
COPY .streamlit ./.streamlit

RUN pip install --no-cache-dir .

USER transferlens
EXPOSE 8501

CMD ["streamlit", "run", "transferlens/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
