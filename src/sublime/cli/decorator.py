"""CLI subcommand decorators.

Decorators used to add common functionality to subcommands.

"""
import os
import functools

import click
import structlog
from requests.exceptions import RequestException

from sublime.api import Sublime
from sublime.cli.formatter import FORMATTERS
from sublime.exceptions import RequestFailure
from sublime.util import load_config

LOGGER = structlog.get_logger()


def echo_result(function):
    """Decorator that prints subcommand results correctly formatted.

    :param function: Subcommand that returns a result from the API.
    :type function: callable
    :returns: Wrapped function that prints subcommand results
    :rtype: callable

    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        result = function(*args, **kwargs)
        context = click.get_current_context()
        params = context.params
        output_format = params["output_format"]
        formatter = FORMATTERS[output_format]
        if isinstance(formatter, dict):
            # For the text formatter, there's a separate formatter for each subcommand
            formatter = formatter[context.command.name]

        output = formatter(result, params.get("verbose", False)).strip("\n")
        click.echo(
            output, file=params.get("output_file", click.open_file("-", mode="w"))
        )

        # default behavior is to always save the MDM even if no output file is specified
        if context.command.name == "enrich" and not params.get("output_file"):
            input_file_relative_name = params.get('input_file').name
            input_file_relative_no_ext, _ = os.path.splitext(input_file_relative_name)
            input_file_name_no_ext = os.path.basename(input_file_relative_no_ext)
            output_file_name = f'{input_file_name_no_ext}.mdm'

            formatter = FORMATTERS["json"]
            output = formatter(result, params.get("verbose", False)).strip("\n")
            click.echo(
                output, file=click.open_file(output_file_name, mode="w")
            )

    return wrapper


def handle_exceptions(function):
    """Print error and exit on API client exception.

    :param function: Subcommand that returns a result from the API.
    :type function: callable
    :returns: Wrapped function that prints subcommand results
    :rtype: callable

    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RequestFailure as exception:
            body = exception.args[1]
            error_message = "API error: {}".format(body["detail"])
            LOGGER.error(error_message)
            # click.echo(error_message)
            click.get_current_context().exit(-1)
        except RequestException as exception:
            error_message = "API error: {}".format(exception)
            LOGGER.error(error_message)
            # click.echo(error_message)
            click.get_current_context().exit(-1)

    return wrapper


def pass_api_client(function):
    """Create API client form API key and pass it to subcommand.

    :param function: Subcommand that returns a result from the API.
    :type function: callable
    :returns: Wrapped function that prints subcommand results
    :rtype: callable

    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        context = click.get_current_context()
        api_key = context.params.get("api_key")
        config = load_config()

        if api_key is None:
            if not config["api_key"]:
                prog_name = context.parent.info_name
                click.echo(
                    "\nError: API key not found.\n\n"
                    "To fix this problem, please use any of the following methods "
                    "(in order of precedence):\n"
                    "- Pass it using the -k/--api-key option.\n"
                    "- Set it in the SUBLIME_API_KEY environment variable.\n"
                    "- Run {!r} to save it to the configuration file.\n".format(
                        "{} setup".format(prog_name)
                    )
                )
                context.exit(-1)
            api_key = config["api_key"]

        api_client = Sublime(api_key=api_key)
        return function(api_client, *args, **kwargs)

    return wrapper


def enrich_command(function):
    """Decorator that groups decorators common to enrich subcommand."""

    @click.command()
    @click.option("-k", "--api-key", help="Key to include in API requests")
    @click.option(
        "-i", "--input", "input_file", type=click.File(), 
        help="Input EML file", required=True
    )
    @click.option(
        "-o", "--output", "output_file", type=click.File(mode="w"), 
        help=(
            "Output file. Defaults to the input_file name in the current directory "
            "with a .mdm extension if none is specified"
        )
    )
    @click.option(
        "-f",
        "--format",
        "output_format",
        type=click.Choice(["json", "txt"]),
        default="txt",
        help="Output format",
    )
    @pass_api_client
    @click.pass_context
    @echo_result
    @handle_exceptions
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return function(*args, **kwargs)

    return wrapper


def analyze_command(function):
    """Decorator that groups decorators common to analyze subcommand."""

    @click.command()
    @click.option("-k", "--api-key", help="Key to include in API requests")
    @click.option(
        "-i", "--input", "input_file", type=click.File(), 
        help="Input EML or enriched MDM file", required=True
    )
    @click.option(
        "-d", "--detections", "detections_file", type=click.File(), 
        help="Detections file", required=True
    )
    @click.option(
        "-o", "--output", "output_file", type=click.File(mode="w"), 
        help=(
            "Output file. Defaults to the input_file name in the current directory "
            "with a .mdm extension if none is specified"
        )
    )
    @click.option(
        "-f",
        "--format",
        "output_format",
        type=click.Choice(["json", "txt"]),
        default="txt",
        help="Output format",
    )
    @pass_api_client
    @click.pass_context
    @echo_result
    @handle_exceptions
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return function(*args, **kwargs)

    return wrapper


class SubcommandNotImplemented(click.ClickException):
    """Exception used temporarily for subcommands that have not been implemented.

    :param subcommand_name: Name of the subcommand to display in the error message.
    :type subcommand_function: str

    """

    def __init__(self, subcommand_name):
        message = "{!r} subcommand is not implemented yet.".format(subcommand_name)
        super(SubcommandNotImplemented, self).__init__(message)


def not_implemented_command(function):
    """Decorator that sends requests for not implemented commands."""

    @click.command()
    @pass_api_client
    @functools.wraps(function)
    def wrapper(api_client, *args, **kwargs):
        command_name = function.__name__
        try:
            api_client.not_implemented(command_name)
        except RequestFailure:
            raise SubcommandNotImplemented(command_name)

    return wrapper