FROM python:3.13-slim

# Add UV to the image
COPY --from=ghcr.io/astral-sh/uv:0.7.14 /uv /uvx /bin/

# Copy the project into the image
ADD . /app

# Sync the project into a new environment, asserting the lockfile is up to date
WORKDIR /app
RUN uv sync --locked

# Create directory for logs
RUN mkdir -p /app/logs

# Run the bot
CMD ["uv", "run", "dndmplusbot.py"]