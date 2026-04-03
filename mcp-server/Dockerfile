FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml server.py ./

RUN pip install --no-cache-dir "mcp[cli]>=1.0.0" "boto3>=1.35.0"

CMD ["python", "server.py"]
