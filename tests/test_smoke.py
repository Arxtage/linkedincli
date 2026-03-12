from click.testing import CliRunner

from linkedincli.cli import cli


def test_version_command() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "linkedincli 0.1.0" in result.output
