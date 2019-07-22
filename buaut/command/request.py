# Typehinting
from typing import List, Tuple

import click
import validators
from bunq.sdk.model.generated import endpoint
from bunq.sdk.model.generated.object_ import Pointer, Amount

from buaut import helpers


@click.command()
@click.pass_context
@click.option(
    '--get',
    help='Email and amount (xx.xx) to request',
    required=True,
    multiple=True,
    type=(str, float)
)
@click.option(
    '--description',
    help='Description for the request',
    required=True,
    type=click.STRING
)
@click.option(
    '--currency',
    help='Currency for the requests in an ISO 4217 formatted currency code.',
    type=click.STRING,
    default='EUR',
    show_default=True
)
def request(ctx, get: List[Tuple[str, float]], description: str, currency: str):
    """Request on or more user for one or more amount

    Args:
        ctx ([type]): Click object containing the arguments from global
        get ([tuple]): List of users to request from
        description (str): Description for the request
        currency (str): Currency in an ISO 4217 formatted currency code
    """
    monetary_account_id: int = ctx.obj.get('monetary_account_id')

    helpers.create_request_batch(
      monetary_account_id=monetary_account_id,
      requests=get,
      description=description,
      currency=currency
    )
