FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY pyproject.toml ./
COPY services ./services
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 jobos
USER jobos

CMD ["python", "-m", "services.api.run", "--container"]
