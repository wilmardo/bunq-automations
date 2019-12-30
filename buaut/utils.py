# Typehinting
from typing import List, Tuple, Optional

import re
import validators
import datetime

from bunq.sdk.client import Pagination
from bunq.sdk.model.generated import endpoint, object_
from bunq.sdk.exception import BunqException


def get_monetary_account_id(value_type: str, value: str) -> int:
    """Get account_id with api types

    Args:
        type (str): Possible values: IBAN, EMAIL, PHONE_NUMBER
        value (str): Value of defined type

    Returns:
        int: monetary account id

    Raises:
        ValueError: If match is not found
    """
    pagination = Pagination()
    pagination.count = 25  # maximum of accounts
    monetaryaccount_list = endpoint.MonetaryAccount.list(
        params=pagination.url_params_count_only).value

    for monetaryaccount in monetaryaccount_list:
        account = monetaryaccount.MonetaryAccountBank or \
                    monetaryaccount.MonetaryAccountJoint or \
                    monetaryaccount.MonetaryAccountLight or \
                    monetaryaccount.MonetaryAccountSavings
        for alias in account.alias:
            if alias.type_ == value_type and alias.value == value:
                return account.id_

    raise ValueError


def get_events(monetary_account_id: int, types: Optional[List[str]], includes: Optional[List[str]],
      excludes: Optional[List[str]], end_date: Optional[datetime.datetime]) -> List[endpoint.Event]:
    """Get events for a certain account

    Args:
        monetary_account_id (int): Monetary account id
        types (List[str]): API types to filter from events
        includes (List[str]): IBAN number to include
        excludes (List[str]): IBAN numbers to exclude
        end_date (datetime.datetime): Date to stop looking for events

    Returns:
        List[endpoint.Event]: List of events
    """

    events: List[endpoint.Event] = []
    result: List[endpoint.Event] = []

    try:
        # Loop until we raise or return
        while True:
            # Check if first iteration (unsplit_payments empty)
            if not events:
                # We will loop over the payments in batches of 200
                pagination = Pagination()
                pagination.count = 200
                params = pagination.url_params_count_only
            else:
                # TODO: Fix this, this does not seem to work
                # BunqException('Could not generate previous page URL params: there is no previous page.',)

                # When there is already a paged request, you can get the next page from it, no need to create it ourselfs:
                try:
                    params = pagination.url_params_previous_page
                except BunqException:
                    # Break the loop, there is no more to process
                    raise StopIteration

            # Add parameters to only list for current monetary_account_id
            params['monetary_account_id'] = monetary_account_id
            params['display_user_event'] = 'false'

            # Get events
            events = endpoint.Event.list(
                params=params,
            ).value

            # Filter out all non relevant events
            included_events: List[endpoint.Event] = _filter_excluded_events(
                events=events, includes=includes, excludes=excludes)

            for e in included_events:
                if datetime.datetime.strptime(e.created, '%Y-%m-%d %H:%M:%S.%f') < end_date:
                    # Break the outer loop since this is before the end_date
                    raise StopIteration

                for t in types:
                  a = getattr(e.object_, t.capitalize(), '')  # use capitilize since API objects are CamelCase
                  # Only insert if of desired type
                  # NOTE: uses insert no mitigate reversing the events
                  if a: result.insert(e)

    except StopIteration: return result


def get_payment_object(event: endpoint.Payment) -> endpoint.Payment:
    """Workaround for the issue https://github.com/bunq/sdk_python/issues/116

    Args:
        event (endpoint.Payment): Payment object of Event object so incomplete

    Returns:
        endpoint.Payment: Payment object but from the payment endpoint
    """
    payment = endpoint.Payment.get(
       payment_id=event.id_,
       monetary_account_id=event.monetary_account_id
    )
    return payment.value


def convert_to_valid_amount(amount) -> str:
    """Convert any datatype to a valid amount (xx.xx)

    Args:
        amount (any): Amount to convert

    Returns:
        str: Amount in valid currency string
    """
    # Source: https://stackoverflow.com/a/6539677
    return "{0:.2f}".format(amount)


def convert_comma_seperated_to_list(string: str) -> List[str]:
    """Convert comma seperated string to list

    Args:
        string (str): Comma seperated string to split

    Returns:
        List: List contain the items of the string
    """
    # Source: https://stackoverflow.com/a/12760144
    pattern = re.compile(r"^\s+|\s*,\s*|\s+$")
    return pattern.split(string)


def create_request_batch(monetary_account_id: int, requests: List[Tuple[str, float]], description: str, currency: str,
                          event_id: int=None,
                          reference_split_the_bill: object_.RequestReferenceSplitTheBillAnchorObject=None):
    """Create request batch from a list of requests

    Args:
        monetary_account_id (int): Account id where the requests are made from
        requests (List[tuple]): List of tuples containing email and amount
        description (str): Description for the requests
        currency (str): Currency for the requests in an ISO 4217 formatted currency code
        event_id (int): The ID of the associated event if the request batch was made using 'split the bill'.
    """
    request_inqueries: List[dict] = []
    total_amount_inquired: float = 0

    for email, amount in requests:
        # Check if valid email
        # TODO: Create some logging class and exit with message
        if not validators.email(email):
            exit(1)

        # Add amount to total
        total_amount_inquired += amount
        # Create request and append to request_inqueries list
        request = endpoint.RequestInquiry(
            amount_inquired=object_.Amount(convert_to_valid_amount(amount), currency),
            counterparty_alias=object_.Pointer(type_='EMAIL', value=email),
            description=description,
            allow_bunqme=True
        )

        # Add request to list
        request_inqueries.append(request)


    # Convert to valid Bunq currency string
    total_amount_inquired_string: str = convert_to_valid_amount(
        total_amount_inquired)

    # Send the requests to the API to create the requests batch
    endpoint.RequestInquiryBatch.create(
        request_inquiries=request_inqueries,
        total_amount_inquired=object_.Amount(total_amount_inquired_string, currency),
        monetary_account_id=monetary_account_id,
        event_id=event_id
    )


def _filter_excluded_events(events: List[endpoint.Event], includes: Optional[List[str]], excludes: Optional[List[str]]
    ) -> List[endpoint.Event]:
    """Filter all excluded payments

    Args:
        payments (Payment): Bunq payment object to validate

    Returns:
        List[endpoint.Payment]: List of included payments
    """
    if not includes and not excludes:
        # No need to check just return
        return events

    result: List[endpoint.Event] = []
    # Loop payments to filter
    for e in events:
        # TODO: make this more generic for non payment events
        payment = get_payment_object(e.object_.Payment)
        counterparty = payment.counterparty_alias.label_monetary_account

        # When payment not in excludes it should be included
        if counterparty.iban not in excludes:
            # When includes defined check if included, else just append
            if includes:
                if counterparty.iban in includes:
                    result.append(payment)
            else:
                result.append(payment)

    return result