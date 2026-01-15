import click

from gitmore.add_partial import add_partial


@click.group()
def cli():
    """Git utilities for AI agents and humans."""
    pass


cli.add_command(add_partial)
# Test comment
