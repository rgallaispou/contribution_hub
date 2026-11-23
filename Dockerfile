FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
RUN mkdir -p /app/imports /app/data
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"]
