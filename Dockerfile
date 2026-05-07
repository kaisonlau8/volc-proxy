FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py config.py converter.py .

RUN mkdir -p logs

EXPOSE 8000

ENV ARK_API_KEY=""
ENV ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/coding"
ENV ARK_REAL_MODEL="glm-5.1"
ENV ARK_PROXY_PORT="8000"
ENV ARK_THINKING_MODE="auto"

CMD ["python3", "main.py"]