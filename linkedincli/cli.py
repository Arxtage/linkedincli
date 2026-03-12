import click


@click.group()
def cli() -> None:
    """LinkedIn CLI."""


@cli.command()
def version() -> None:
    """Print the current version."""
    click.echo("linkedincli 0.1.0")
