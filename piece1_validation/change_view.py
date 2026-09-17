"""Compare actual canonical records before and after owner decisions."""

import json

import streamlit as st

from .adapter import KEYS
from .review_ui import business_zone, display_value, show_rows


def changes(before, after):
    results = []

    tables = [
        "bookings",
        "inventory_items",
        "customers",
        "transactions",
        "transaction_items",
        "items",
    ]

    for table in tables:
        key = KEYS[table]
        old = {r[key]: r for r in before.tables.get(table, [])}
        new = {r[key]: r for r in after.tables.get(table, [])}

        for identifier in sorted(set(old) | set(new)):
            original = old.get(identifier, {})
            current = new.get(identifier, {})

            if identifier not in old:
                change_type = "Added record"
            elif identifier not in new:
                change_type = "Removed record"
            else:
                change_type = "Updated field"

            for field in sorted(set(original) | set(current)):
                if original.get(field) != current.get(field):
                    results.append(
                        {
                            "Table": table,
                            "Record": identifier,
                            "Field": field,
                            "Before": original.get(field),
                            "After": current.get(field),
                            "Change": change_type,
                        }
                    )

    old_links = {
        row["source_customer_id"]: row
        for row in before.identity
    }

    for row in after.identity:
        original = old_links.get(row["source_customer_id"], {})

        for field in ["status", "customer_id"]:
            if original.get(field) != row.get(field):
                results.append(
                    {
                        "Table": "customer_identity_links",
                        "Record": row["source_customer_id"],
                        "Field": field,
                        "Before": original.get(field),
                        "After": row.get(field),
                        "Change": "Updated identity link",
                    }
                )

    return results


def render_changes(before, after, notes):
    rows = changes(before, after)
    zone = business_zone(after)

    st.subheader("Verify changes in the tables")
    st.caption(
        "Before = cleaned data before owner decisions. "
        "After = current session records. "
        "Original CSVs remain unchanged. "
        "Customer matching changes a link. "
        "It does not merge two existing customer records."
    )

    if rows:
        display_rows = [
            {
                key: (
                    "Unavailable"
                    if value is None
                    else display_value(value, zone)
                )
                for key, value in row.items()
            }
            for row in rows
        ]
        st.dataframe(display_rows, hide_index=True)
    else:
        st.info("No confirmed record changes yet.")

    with st.expander("Inspect the current table records"):
        table = st.selectbox(
            "Table",
            [
                "inventory_items",
                "bookings",
                "customer_identity_links",
                "customers",
                "transactions",
                "transaction_items",
                "business_context",
            ],
            key="p1_inspect_table",
        )

        if table == "customer_identity_links":
            data = after.identity
        elif table == "business_context":
            data = after.tables.get("business_context", []) + notes
        else:
            data = after.tables.get(table, [])

        search = st.text_input(
            "Filter by record ID, name or reference",
            key="p1_inspect_filter",
        ).strip()

        filtered = [
            row
            for row in data
            if (
                not search
                or search.casefold()
                in json.dumps(row, default=str).casefold()
            )
        ]

        st.caption(
            f"{len(filtered)} matching records. "
            f"Displaying up to 200. Times shown in {zone.key}."
        )
        show_rows(filtered[:200], zone)

    # Approval details remain in the review tables and stored records.
    # A separate duplicate approval section is intentionally omitted.