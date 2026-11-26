FROM grafana/k6:2.4.0@sha256:d41bb79cd8de5a7ad619b53570e3712633e8bff0937010a5c6c57a4747e7a276 AS k6

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6
COPY *.py journeys.js ./

RUN useradd --uid 10001 --no-create-home mcp
USER 10001

ENV HOST=0.0.0.0 PORT=8081
EXPOSE 8081
CMD ["python", "server.py"]