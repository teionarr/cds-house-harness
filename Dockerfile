FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
# Install dependencies first (cached layer) WITHOUT the project, so a code change
# doesn't re-resolve the whole dependency tree.
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Now the package itself.
COPY src ./src
RUN uv sync --no-dev

# The vendored corpus — ingested on boot (changed files only) so the live service
# answers from the resolved ontology, not a runtime fetch.
COPY data ./data

ENTRYPOINT ["uv", "run", "house-harness"]
CMD ["--help"]
