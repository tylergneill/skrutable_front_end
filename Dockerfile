FROM python:3.11-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
ENV PORT=5000
CMD gunicorn --bind 0.0.0.0:$PORT flask_app:app
EXPOSE 5000