FROM python:3.11-slim

ARG APP_UID=1001
ARG APP_GID=1001

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY deploy/requirements.production.txt ./requirements.txt
RUN pip install --index-url https://pypi.org/simple -r requirements.txt && \
    groupadd --gid "$APP_GID" outlook && \
    useradd --uid "$APP_UID" --gid "$APP_GID" --no-create-home --home-dir /app outlook

COPY --chown=${APP_UID}:${APP_GID} web_outlook_app.py ./
COPY --chown=${APP_UID}:${APP_GID} outlook_web/ ./outlook_web/
COPY --chown=${APP_UID}:${APP_GID} templates/ ./templates/
COPY --chown=${APP_UID}:${APP_GID} static/ ./static/
COPY --chown=${APP_UID}:${APP_GID} img/ico.png ./img/ico.png

RUN mkdir -p /app/data /app/.runtime && chown "$APP_UID:$APP_GID" /app/data /app/.runtime

USER ${APP_UID}:${APP_GID}
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=4).read()"]

CMD ["gunicorn", "--workers", "1", "--threads", "8", "--bind", "0.0.0.0:5000", "--timeout", "120", "--no-control-socket", "--forwarded-allow-ips", "", "--access-logfile", "-", "--access-logformat", "%(h)s %(t)s \"%(m)s %(U)s %(H)s\" %(s)s %(b)s", "web_outlook_app:app"]
