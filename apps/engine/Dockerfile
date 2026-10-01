FROM python:3.14.5-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-api.lock requirements-build.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-api.lock -r requirements-build.lock
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-build-isolation --no-deps -w /wheels . && pip install --no-cache-dir --no-deps /wheels/*.whl
COPY app.py ./
FROM base AS test
COPY requirements-test.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-test.lock
COPY tests ./tests
CMD ["python", "-I", "-m", "pytest", "-q", "--import-mode=importlib", "tests"]
FROM base AS runtime
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
