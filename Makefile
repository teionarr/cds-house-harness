.PHONY: setup lint type test eval validate run docker start package verify

setup:
	uv sync --all-extras --dev
	uv run pre-commit install

lint:
	uv run ruff format --check .
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest -q --cov=house_harness --cov-report=term-missing

eval:
	uv run python -m evals.harness --suite structural provenance uplift --subset 20

# Post-build acceptance gate (see VALIDATION.md): held-out functional + trust +
# red-team + ops suites -> evals/validation/report.json. Blocking gate exits non-zero on fail.
validate:
	uv run python -m evals.harness --suite validation --heldout evals/validation --report evals/validation/report.json --gate

run:
	uv run house-harness run $(CORPUS)

docker:
	docker build -t house-harness:dev .

# One command, fresh clone -> running stack (mirrors how they ship)
start:
	./install.sh

# Build the submission zip from committed files only (no venv/cache/secrets)
package:
	git archive --format=zip -o ../submission.zip HEAD
	@echo "Wrote ../submission.zip"

# The reviewer's real test: extract clean, bring it up, hit /health
verify: package
	rm -rf /tmp/sf-verify && mkdir -p /tmp/sf-verify
	cd /tmp/sf-verify && unzip -q $(CURDIR)/../submission.zip && cp .env.example .env && ./install.sh
