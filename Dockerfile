FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home flowfix
COPY --chown=flowfix:flowfix . .
USER flowfix
EXPOSE 8000
CMD ["gunicorn", "saas.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--limit-request-line", "4094", "--limit-request-fields", "50", "--error-logfile", "-", "--no-control-socket"]
