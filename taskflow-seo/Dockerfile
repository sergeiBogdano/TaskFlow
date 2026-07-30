FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data logs

EXPOSE 8000

CMD ["uvicorn", "app.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
