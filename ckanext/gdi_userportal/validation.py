# SPDX-FileCopyrightText: His Majesty the King in Right of Canada, represented by the President of the Treasury Board
# SPDX-FileContributor: Stichting Health-RI
#
# SPDX-License-Identifier: MIT

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from ckanext.scheming.validation import register_validator, scheming_validator
from ckantoolkit import Invalid, _, get_validator
from dateutil.parser import isoparse

not_empty = get_validator("not_empty")


def enforce_utc_time(dt: datetime) -> datetime:
    """This function ensures a datetime object is always in UTC time with second accuracy.

    If no timezone is specified, it is presumed to be UTC time.

    Parameters
    ----------
    dt : datetime
        Datetime object to be set to UTC time

    Returns
    -------
    datetime
        Datetime object in UTC time

    """
    # Cut off microseconds, we don't need that much accuracy
    dt = dt.replace(microsecond=0)

    # If datetime is naive, assume UTC
    if dt.tzinfo is None:
        out_date = dt.replace(tzinfo=timezone.utc)
    else:
        out_date = dt.astimezone(timezone.utc)

    return out_date


def validate_datetime_flex_inputs(
    field, key, data, extras, errors, context
) -> datetime:
    """This function validates datetime inputs with a timezone accordng to ISO 8601.
    Note: this is about input from the form on the CKAN entry page.
    """
    date_error = _("Date format incorrect")
    time_error = _("Time format incorrect")

    date = None

    def get_input(suffix):
        inpt = key[0] + "_" + suffix
        new_key = (inpt,) + tuple(x for x in key if x != key[0])
        key_value = extras.get(inpt)
        data[new_key] = key_value
        errors[new_key] = []

        if key_value:
            del extras[inpt]

        if field.get("required"):
            not_empty(new_key, data, errors, context)

        return new_key, key_value

    date_key, date_value = get_input("date")

    if date_value:
        try:
            date = isoparse(date_value)
        except (TypeError, ValueError):
            errors[date_key].append(date_error)

    time_key, time_value = get_input("time")
    if time_value:
        if not date_value:
            errors[date_key].append(_("Date is required when a time is provided"))
        else:
            try:
                value_full = f"{date_value}T{time_value}"
                date = isoparse(value_full)
            except (TypeError, ValueError):
                errors[time_key].append(time_error)
    else:
        if isinstance(date, datetime):
            date.replace(hour=12)

    tz_key, tz_value = get_input("tz")
    if tz_value:
        try:
            tz = ZoneInfo(tz_value)
        except ZoneInfoNotFoundError:
            errors[tz_key].append(f"Invalid timezone: {tz_value}")
        else:
            if isinstance(date, datetime):
                # If date is naive, treat it as local time in the provided zone
                if date.tzinfo is None:
                    date = date.replace(tzinfo=tz)
                else:
                    date = date.astimezone(tz)

    return date


@register_validator
@scheming_validator
def scheming_isodatetime_flex(field, schema):
    """This scheming validator is very similar to the upstream one, but uses the parser from
    dateutil, which is a bit more robust and can also handle missing timestamps from inputs.
    """

    def validator(key, data, errors, context):
        value = data[key]
        date = None

        # If we get a value for the key, check if it's a datetime else make it one
        if value:
            if isinstance(value, datetime):
                date = value
            else:
                try:
                    date = isoparse(value)
                except (ValueError, TypeError):
                    raise Invalid(_("Datetime format incorrect"))
        else:
            # Else try to combine existing fields (extras date and time) into a datetime object
            extras = data.get(("__extras",))
            if not extras or (
                f"{key[0]}_date" not in extras and f"{key[0]}_time" not in extras
            ):
                if field.get("required"):
                    not_empty(key, data, errors, context)
            else:
                date = validate_datetime_flex_inputs(
                    field, key, data, extras, errors, context
                )
        if date:
            date = enforce_utc_time(date)

        data[key] = date

    return validator
