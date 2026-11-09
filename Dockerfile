# Dependencies, installed by uv exactly as pinned in uv.lock
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS dependencies
RUN pip install --no-cache-dir --root-user-action=ignore uv==0.13.7
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# The bot: Python, the dependencies and the code, without uv
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# Print logs right away instead of buffering them
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN useradd --create-home --uid 1000 luna

COPY --from=dependencies /app/.venv /app/.venv
COPY . .
# data/ holds the Telegram session, docker-compose.yml mounts a volume there.
# Heroku runs containers as a random user, so the folder is writable by all.
RUN mkdir -p /app/data && chown luna:luna /app/data && chmod 1777 /app/data
USER luna

CMD ["python3", "-m", "luna"]
