"""CLI entrypoint. `house-harness run <corpus>` executes the pipeline end to end;
`house-harness serve` starts the agent-facing endpoint.

Stub: wire the real pipeline (ingest -> ... -> centrality) here as milestones land.
Keep this thin — orchestration logic lives in pipeline/ and serve/, not in the CLI.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    help="House Harness Engine — compile org artifacts into a House Harness "
    "(<COMPANY>.md + ontology graph)."
)


@app.command()
def run(
    corpus: Path = typer.Argument(..., help="Path to the corpus directory."),
    out: Path = typer.Option(Path("out"), help="Where to write <COMPANY>.md + graph.json."),
) -> None:
    """Run the full pipeline on a corpus directory: ingest -> extract -> persist ->
    emit <COMPANY>.md + graph.json. Needs ANTHROPIC_API_KEY (extraction)."""
    import json

    from house_harness.pipeline.run import run_pipeline

    summary = run_pipeline(str(corpus), str(out))
    typer.echo(json.dumps(summary, indent=2))


@app.command()
def serve(
    corpus: Path | None = typer.Argument(None, help="Corpus dir to ingest on boot."),
    ingest_on_boot: bool = typer.Option(
        False, "--ingest-on-boot", help="Ingest the corpus before serving."
    ),
    port: int | None = typer.Option(None, help="Port (default APP_PORT or 8080)."),
) -> None:
    """Start the agent-facing endpoint. v1 skeleton serves GET /health (open) and
    POST /ask (token-gated -> serve.answer). This is the Phase-1 deploy contract;
    the production MCP server + HTTP layer supersede it."""
    from house_harness.serve import _httpd

    _httpd.run(ingest_on_boot=ingest_on_boot, corpus=corpus, port=port)


@app.command()
def mcp(
    transport: str = typer.Option("stdio", help="MCP transport: stdio | sse | streamable-http."),
) -> None:
    """Start the MCP server — the primary agent-native surface (ask_company,
    get_harness, get_harness_health, get_entity). An agent spawns it over stdio."""
    from house_harness.serve.mcp import run as run_mcp

    run_mcp(transport=transport)


if __name__ == "__main__":
    app()
