"""CLI entrypoint. `house-harness run <corpus>` executes the pipeline end to end;
`house-harness serve` starts the agent-facing endpoint.

Stub: wire the real pipeline (ingest -> ... -> centrality) here as milestones land.
Keep this thin — orchestration logic lives in pipeline/ and serve/, not in the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="House Harness Engine — compile org artifacts into a House Harness (<COMPANY>.md + ontology graph).")


@app.command()
def run(
    corpus: Path = typer.Argument(..., help="Path to a corpus of Artifact JSON."),
    out: Path = typer.Option(Path("out"), help="Where to write <COMPANY>.md files + graph.json."),
) -> None:
    """Run the full pipeline on a corpus directory."""
    # TODO(M1+): from house_harness.pipeline import run_pipeline; run_pipeline(corpus, out)
    typer.echo(f"[stub] would compile {corpus} -> {out}")


@app.command()
def serve(
    corpus: Optional[Path] = typer.Argument(None, help="Corpus dir to ingest on boot."),
    ingest_on_boot: bool = typer.Option(False, "--ingest-on-boot", help="Ingest the corpus before serving."),
    port: Optional[int] = typer.Option(None, help="Port (default APP_PORT or 8080)."),
) -> None:
    """Start the agent-facing endpoint. v1 skeleton serves GET /health (open) and
    POST /ask (token-gated -> serve.answer). This is the Phase-1 deploy contract;
    the production MCP server + HTTP layer supersede it."""
    from house_harness.serve import _httpd

    _httpd.run(ingest_on_boot=ingest_on_boot, corpus=corpus, port=port)


if __name__ == "__main__":
    app()
