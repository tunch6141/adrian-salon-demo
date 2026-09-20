from pathlib import Path
import json
import os
import uuid

import streamlit as st

from .adapter import Intake, digest
from analytics.persistence import save_review
from .amendments import money_request, validate_sales
from .clarification import (
    questions,
    ai_extract,
    proposed,
    decision,
    context_note,
    validate_checkpoint,
    stock_reply,
)
from .review_ui import (
    business_zone,
    selected_records,
    explain_question,
    review_tables,
)


def setting(key):
    try:
        return str(st.secrets.get(key, os.environ.get(key, "")))
    except FileNotFoundError:
        return os.environ.get(key, "")


def render_chat(intake):
    raw = intake.source

    defaults = [
        ("p1_decisions", []),
        ("p1_context", []),
        ("p1_chat", {}),
        ("p1_pending", None),
        ("p1_sales", []),
    ]
    for name, default in defaults:
        st.session_state.setdefault(name, default)

    st.subheader("Clarify an issue with the owner")
    st.caption(
        "Confirmed decisions are remembered and reused. New ambiguities need review. "
        "The approval history records who confirmed each change and when." if st.session_state.get("pipeline_connected") else
        "Local preview only. Download a checkpoint before leaving; Supabase is not connected."
    )

    choices = {q["id"]: q for q in questions(intake)}
    labels = {identifier: q["label"] for identifier, q in choices.items()}
    labels["context"] = "Record a business event"
    labels["sale"] = "Record a missing sale"

    selected = st.selectbox(
        "What would you like to clarify?",
        list(labels),
        format_func=labels.get,
        key="p1_issue",
    )
    q = choices.get(selected)

    owner = st.text_input(
        "Name of person confirming",
        key="p1_owner",
        placeholder="For example, Adrian",
    )
    st.caption(
        "Self-reported name under the shared demo password, "
        "not a separately verified identity."
    )

    mode = st.radio(
        "Reply method",
        ["AI conversation", "Choose the correction directly"],
        horizontal=True,
        key="p1_mode",
    )

    api_key = setting("OPENAI_API_KEY")
    model = setting("CLARIFICATION_MODEL") or setting("OPENAI_MODEL")

    if mode == "AI conversation" and not (api_key and model):
        st.info(
            "AI conversation needs your existing OPENAI_API_KEY and "
            "OPENAI_MODEL secrets. Direct correction remains available."
        )

    if q:
        opening = q["question"]
    elif selected == "sale":
        opening = (
            "Tell me about the missing sale: staff, date and amount. "
            "I will ask you to review the accounting details before "
            "recording it."
        )
    else:
        opening = (
            "What happened in the business? I can save your explanation "
            "as owner-provided context. This does not automatically "
            "update inventory, costs, staff availability or revenue. "
            "Missing-sales requests have a separate review process."
        )

    with st.chat_message("assistant"):
        st.write(opening)

    selected_records(intake, q)

    history = st.session_state["p1_chat"].setdefault(selected, [])
    for message in history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Nesting the input makes it appear here, beneath the conversation.
    with st.container():
        text = st.chat_input(
            "Reply to the question or describe a business event",
            key="p1_chat_input",
            max_chars=2000,
        )

    if text:
        history.append({"role": "user", "content": text})
        st.session_state["p1_pending"] = None

        try:
            if explanation := explain_question(q, text):
                parsed = {
                    "intent": "clarify",
                    "message": explanation,
                }
            elif selected == "sale" or money_request(text):
                parsed = {"intent": "transaction"}
            elif (
                q
                and q["kind"] == "cost"
                and (local := stock_reply(q, text))
            ):
                parsed = local
            elif q is None:
                parsed = {"intent": "context"}
            elif not (api_key and model):
                parsed = {"intent": "not_configured"}
            else:
                with st.spinner("Interpreting your reply…"):
                    parsed = ai_extract(q, history, api_key, model)

            intent = parsed["intent"]

            if intent == "transaction":
                st.session_state["p1_pending"] = {
                    "kind": "sale",
                    "text": text,
                    "selected": selected,
                    "token": uuid.uuid4().hex,
                }
                answer = (
                    "This describes a possible missing financial transaction. "
                    "Review the sale date, staff, category, tax basis and "
                    "unique reference below. A cash receipt could also be "
                    "payment for an existing sale, so check that first."
                )

            elif intent == "clarify":
                answer = parsed["message"]

            elif intent == "answer":
                draft = proposed(q, parsed["value"], text)
                st.session_state["p1_pending"] = {
                    "kind": "correction",
                    "draft": draft,
                    "selected": selected,
                }
                answer = (
                    "Proposed change: "
                    + draft["summary"]
                    + " Please review before confirming."
                )

            elif intent == "context":
                st.session_state["p1_pending"] = {
                    "kind": "context",
                    "text": text,
                    "selected": selected,
                }
                answer = (
                    "I can record your exact wording as owner-provided "
                    "context. Review the entity and dates below. "
                    "This will not change bookings, inventory, costs, "
                    "revenue or staff availability."
                )

            elif intent == "not_configured":
                answer = (
                    "AI interpretation is not configured. Choose the "
                    "correction directly, or add your existing model settings."
                )

            elif intent == "uncertain":
                answer = (
                    "Please state the name/ID or unit cost in AUD excluding "
                    "GST explicitly. If unsure, leave this issue unresolved."
                )

            else:
                answer = (
                    "This chat handles data clarification and business "
                    "events. Full commercial investigation is not "
                    "connected here yet."
                )

        except Exception as exc:
            if isinstance(exc, ValueError):
                answer = str(exc)
            else:
                answer = (
                    "The AI request did not complete. Nothing was changed. "
                    "Retry or choose the correction directly."
                )

        history.append({"role": "assistant", "content": answer})
        st.rerun()

    if q and (
        mode == "Choose the correction directly"
        or not (api_key and model)
    ):
        if q["kind"] == "cost":
            value = st.text_input(
                "Unit cost in AUD excluding GST",
                key="p1_cost:" + selected,
            )
            evidence = "Owner entered AUD " + value + " excluding GST"
        else:
            options = {o["value"]: o["label"] for o in q["options"]}
            value = st.selectbox(
                "Confirmed identity",
                [""] + list(options),
                format_func=lambda x: options.get(x, "Select an identity"),
                key="p1_choice:" + selected,
            )
            evidence = (
                "Owner selected " + options.get(value, "") + " " + value
            )

        if st.button("Review proposed correction", key="p1_review"):
            try:
                st.session_state["p1_pending"] = {
                    "kind": "correction",
                    "draft": proposed(q, value, evidence),
                    "selected": selected,
                }
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    pending = st.session_state["p1_pending"]

    if pending and pending["selected"] == selected:
        if pending["kind"] == "correction":
            st.write(
                "**Proposed correction:** " + pending["draft"]["summary"]
            )
            st.caption(
                "Raw source files remain unchanged. The approved decision "
                "is reused automatically on matching future imports."
            )

            if st.button(
                "Confirm correction",
                type="primary",
                key="p1_confirm",
            ):
                try:
                    updated = st.session_state["p1_decisions"] + [
                        pending.setdefault("approved_decision", decision(pending["draft"], owner))
                    ]

                    approved = updated[-1]
                    approved.setdefault("rule_id", str(uuid.uuid4()))
                    if approved.get("record_id"):
                        from .adapter import KEYS
                        source_row = next((r['record'] for r in intake.raw if r['table']==approved['table'] and
                            r['record'].get(KEYS[approved['table']])==approved['record_id']), {})
                        approved.setdefault("source_row_hash", digest(source_row))
                    Intake(raw, updated)
                    save_review(st.session_state, setting, {"decisions":updated}, owner,
                                "correction", pending.setdefault("event_id",str(uuid.uuid4())))
                    st.session_state["p1_pending"] = None
                    st.session_state.pop("piece1_check_results", None)
                    st.session_state["p1_notice"] = (
                        "Correction confirmed and data reprocessed."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        elif pending["kind"] == "sale":
            from .sales_ui import render_sale

            render_sale(pending, owner)

        else:
            st.write("**Owner-provided event:** " + pending["text"])

            entity = st.selectbox(
                "Who does this concern?",
                ["Salon", "Sarah", "Matthew", "Sam"],
                key="p1_event_entity",
            )
            start = st.date_input(
                "Event start date",
                value=None,
                key="p1_event_start",
            )
            end = st.date_input(
                "Event end date",
                value=None,
                key="p1_event_end",
            )

            if st.button(
                "Confirm business context",
                type="primary",
                key="p1_confirm_context",
            ):
                try:
                    if not start or not end:
                        raise ValueError("Choose both event dates.")

                    note = context_note(
                        pending["text"], entity, start, end, owner
                    )
                    note = pending.setdefault("approved_note", note)
                    save_review(st.session_state, setting, {"context":st.session_state["p1_context"]+[note]},
                                owner,"context",pending.setdefault("event_id",str(uuid.uuid4())))
                    st.session_state["p1_pending"] = None
                    st.session_state["p1_notice"] = (
                        "Owner context recorded. "
                        "No analytical figures changed."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        if st.button("Discard proposal", key="p1_discard"):
            st.session_state["p1_pending"] = None
            st.rerun()

    for note in st.session_state["p1_context"]:
        if money_request(note["explanation"]):
            st.warning(
                "A saved context note describes a possible financial "
                "correction. Context alone does not change revenue. "
                "Check the confirmed manual-sales list before adding it: "
                + note["explanation"]
            )
            if st.button(
                "Review this note as a missing sale",
                key="convert:" + note["context_id"],
            ):
                st.session_state["p1_pending"] = {
                    "kind": "sale",
                    "text": note["explanation"],
                    "selected": selected,
                    "token": uuid.uuid4().hex,
                }
                st.rerun()

    checkpoint = {
        "format": "piece1_owner_review_v1",
        "decisions": st.session_state["p1_decisions"],
        "context": st.session_state["p1_context"],
        "sales": st.session_state["p1_sales"],
    }

    with st.expander("Approved decisions and business context"):
        review_tables(checkpoint, business_zone(intake))
        st.caption(
            "Business context preserves the owner's explanation. "
            "Ask your salon can retrieve these notes for the relevant "
            "entity and dates."
        )

    st.download_button(
        "Download owner-review checkpoint",
        json.dumps(checkpoint, indent=2),
        file_name="owner_review_checkpoint.json",
        mime="application/json",
    )

    with st.expander("Restore an owner-review checkpoint"):
        upload = st.file_uploader(
            "Checkpoint JSON",
            type=["json"],
            key="p1_restore_file",
        )

        if upload:
            try:
                if upload.size > 200000:
                    raise ValueError("Checkpoint too large.")

                data = json.loads(upload.getvalue())
                decisions, notes = validate_checkpoint(data, raw)
                sales = validate_sales(data.get("sales", []))

                review_tables(
                    {
                        "decisions": decisions,
                        "context": notes,
                        "sales": sales,
                    },
                    business_zone(intake),
                )

                st.caption(
                    "Restoring adds reviewed decisions, notes and sales while preserving earlier approval history. Enter your name above and review first."
                )

                if st.button(
                    "Restore reviewed checkpoint",
                    key="p1_restore_confirm",
                ):
                    updates = {}
                    for name, incoming in [("decisions",decisions),("context",notes),("sales",sales)]:
                        existing = st.session_state["p1_"+name]
                        updates[name] = existing+[row for row in incoming if row not in existing]
                    save_review(st.session_state,setting,updates,owner,"checkpoint_restore",
                                str(uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(updates,sort_keys=True)+str(st.session_state.get("pipeline_version")))))
                    st.session_state["p1_pending"] = None
                    st.session_state["p1_chat"] = {}
                    st.session_state.pop("piece1_check_results", None)
                    st.rerun()

            except (ValueError, KeyError, TypeError) as exc:
                st.error("Checkpoint not restored: " + str(exc))
