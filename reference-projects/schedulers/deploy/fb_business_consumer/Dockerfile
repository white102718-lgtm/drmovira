FROM python:3.11-slim

WORKDIR /schedulers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "tasks.fb_business_sync.fb_business_consumer"]