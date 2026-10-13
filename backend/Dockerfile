FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build DJANGO_DEBUG=1 python manage.py collectstatic --noinput
RUN useradd -m siteos && chown -R siteos /app
USER siteos
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed && gunicorn config.wsgi:application -b 0.0.0.0:8000 -w 3 --access-logfile -"]
