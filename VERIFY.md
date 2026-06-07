# VERIFY.md

Exact commands that prove it works. Run the relevant block before checking off a `PLAN.md` item. `[now]` = wired today; `[impl]` = green once the stub it covers is implemented.

## Static — `[now]`
```bash
python -m compileall -q src                                          # expect 0
PYTHONPATH=src python -c "import house_harness.schema"                  # expect 0 (needs pydantic)
python -m json.tool evals/evals.json   >/dev/null                    # expect 0
python -m json.tool greptile.json      >/dev/null                    # expect 0
python -c "import yaml; yaml.safe_load(open('doppler.yaml'))"        # expect 0
python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"  # expect 0
```

## Lint — `[impl]`
```bash
ruff check src                          # expect 0
shellcheck install.sh                   # expect 0  (linter must be installed)
```

## Evals (the gate) — `[impl]`
```bash
make eval                               # expect 0; runs with/without-harness, asserts delta.pass_rate > 0
```

## Phase-1 deploy gate (BLOCKING) — `[now for /health, impl for /ask]`
```bash
# the deployable artifact must come up healthy BEFORE any Phase 2+ work:
docker build -t house-harness:ci .                                   # expect 0
docker run -d --name hh -e HOUSE_HARNESS_SERVE_MODE=mock -p 8080:8080 house-harness:ci serve
curl -fsS localhost:8080/health                                      # expect {"status":"ok","mode":"mock"}
docker rm -f hh
# then the real deploy — record the URL in PROGRESS.md + SOLUTION.md <DEPLOY_URL>:
curl -fsS https://<DEPLOY_URL>/health                                # expect {"status":"ok","mode":...}
```

## End-to-end — `[impl]`
```bash
./install.sh                            # expect 0; brings up app + SQLite store, ingests data/
curl -fsS localhost:8080/health         # expect 0 + {"status":"ok","mode":"live"}
# sample agent call returns a full trust envelope (mode=live, answer_path=ontology, claims w/ assertion_ids):
curl -fsS localhost:8080/ask -H "Authorization: Bearer $HOUSE_HARNESS_API_TOKEN" \
  -d '{"q":"what is Q1 revenue vs plan, and who approves discounts?"}'   # expect 0
```

## Package — `[now]`
```bash
make package                            # git archive -> tarball; expect 0
make verify                             # extract clean + run static block; expect 0
```
