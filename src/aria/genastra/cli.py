"""GenAstra CLI — Typer-based command-line interface."""

from __future__ import annotations

import typer

app = typer.Typer(name="genastra", help="Genome & Astrobiology Analysis Platform")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address"),  # nosec B104 (CLI default; operator overrides for production)
    port: int = typer.Option(8500, help="Port"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes"),
) -> None:
    """Start the API server."""
    import uvicorn
    uvicorn.run(
        "genastra.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def worker(
    worker_type: str = typer.Argument(help="Worker type: gpu, expression, spectra"),
    device: str = typer.Option("cuda", help="GPU device (gpu worker only)"),
    redis_url: str = typer.Option("redis://localhost:6379/0", help="Redis URL"),
) -> None:
    """Start a background worker."""
    import asyncio

    if worker_type == "gpu":
        from aria.genastra.workers.gpu_worker import GPUWorker
        w = GPUWorker(device=device)
        asyncio.run(w.run(redis_url=redis_url))
    else:
        typer.echo(f"Unknown worker type: {worker_type}. Available: gpu, expression, spectra")
        raise typer.Exit(1)


@app.command()
def migrate(
    revision: str = typer.Option("head", help="Target revision"),
) -> None:
    """Run database migrations."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, revision)
    typer.echo(f"Migrated to: {revision}")


@app.command()
def version() -> None:
    """Print version."""
    from aria.genastra import __version__
    typer.echo(f"GenAstra v{__version__}")


if __name__ == "__main__":
    app()
