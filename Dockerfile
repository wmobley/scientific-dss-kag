FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY ontology ./ontology
COPY domains ./domains
COPY experiments/benchmarks ./experiments/benchmarks
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home researcher
USER researcher
EXPOSE 8000
CMD ["uvicorn", "scientific_dss_kag.api:app", "--host", "0.0.0.0", "--port", "8000"]
