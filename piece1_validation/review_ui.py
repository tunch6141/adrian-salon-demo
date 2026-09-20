import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st


def business_zone(intake):
    return ZoneInfo(intake.tables["businesses"][0]["timezone"])


def display_value(value, zone):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    if isinstance(value, str) and re.match(
        r"^\d{4}-\d{2}-\d{2}T", value
    ):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                return stamp.astimezone(zone).strftime(
                    "%d %b %Y %H:%M:%S %Z (%z)"
                )
            return value + " (timezone unspecified)"
        except ValueError:
            pass
    return str(value)


def show_rows(rows, zone):
    if not rows:
        st.caption("No records yet.")
        return
    columns=list(dict.fromkeys(k for row in rows for k in row))
    if 'appointment_start' in columns and 'appointment_end' in columns:
        columns.remove('appointment_end')
        columns.insert(columns.index('appointment_start')+1,'appointment_end')
    st.dataframe(
        [
            {
                k.replace("_", " ").title(): display_value(row.get(k), zone)
                for k in columns
            }
            for row in rows
        ],
        hide_index=True,
    )


def selected_records(intake, question):
    if not question:
        return

    kind, record = question["kind"], question["record_id"]
    table, key = {
        "staff": ("bookings", "booking_id"),
        "cost": ("inventory_items", "item_id"),
        "identity": ("customer_import_batch", "source_customer_id"),
    }[kind]

    st.caption("Records for this question · " + question["label"])
    show_rows(
        [r for r in intake.tables[table] if r[key] == record],
        business_zone(intake),
    )
    st.caption(
        "Original value requiring clarification: "
        + str(question["raw_value"])
    )

    if kind == "identity":
        ids = {o["value"] for o in question["options"]} - {"new_identity"}
        st.caption("Possible existing customers")
        show_rows(
            [
                r for r in intake.tables["customers"]
                if r["customer_id"] in ids
            ],
            business_zone(intake),
        )


def explain_question(question, text):
    if not question or not re.search(
        r"explain|what do you mean|understand|confus|simpler|clearer|why.*ask|(?:other|more|any).*details|what.*(?:know|details|information)",
        text,
        re.I,
    ):
        return None

    return {
        "staff": (
            "The booking uses a name we cannot match confidently. "
            "The available booking details are shown above, including the customer ID, appointment start and end, and booking source. "
            "The original staff value is “" + str(question['raw_value']) + "”; it does not establish which staff member this is. "
            "Tell me the staff name or ID it belongs to. "
            "This fixes attribution; it does not add a sale."
        ),
        "cost": (
            "For " + question.get("item_name", question["record_id"])
            + ", I need what the business paid for ONE unit, excluding "
            "GST—not its selling price or a box total. If you only know "
            "the box price, leave this unresolved until the unit cost "
            "is confirmed."
        ),
        "identity": (
            "The incoming customer’s phone points to one existing "
            "customer, but the email points to another. Compare the "
            "records above, then give the correct customer name/ID "
            "or say “keep separate”. Existing customers will not "
            "be merged."
        ),
    }[question["kind"]]


def review_tables(checkpoint, zone):
    st.caption(
        "Times shown in " + zone.key
        + ". Approval times remain stored in UTC."
    )
    for key, title in [
        ("decisions", "Approved corrections"),
        ("context", "Business context"),
        ("sales", "Approved manual sales"),
    ]:
        st.markdown("**" + title + "**")
        show_rows(checkpoint.get(key, []), zone)
