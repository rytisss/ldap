FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY seed ./seed
RUN pip install --no-cache-dir -e ".[dev]"

COPY users.yaml ./users.yaml
COPY tests ./tests

CMD ["sandbox-seed"]
