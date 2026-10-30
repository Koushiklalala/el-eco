# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS build
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=bind,source=requirements.txt,target=requirements.txt \
    --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser
COPY --from=build --link --chown=1001:1001 /opt/venv /opt/venv
COPY --link --chown=1001:1001 el_eco ./el_eco
COPY --link --chown=1001:1001 static ./static
COPY --link --chown=1001:1001 --chmod=755 entrypoint.sh ./entrypoint.sh
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER appuser
EXPOSE 8000
LABEL org.opencontainers.image.title="El Eco" \
      org.opencontainers.image.description="An algorithmic ofrenda for abandoned projects" \
      org.opencontainers.image.licenses="MIT"
ENTRYPOINT ["./entrypoint.sh"]
