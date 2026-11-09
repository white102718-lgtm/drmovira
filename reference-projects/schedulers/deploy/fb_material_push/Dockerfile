FROM python:3.11-slim

WORKDIR /schedulers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "tasks.fb_material_push.fb_material_push_consumer"]
