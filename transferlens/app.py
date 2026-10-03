"""TransferLens review workspace. Run with: streamlit run transferlens/app.py"""

from __future__ import annotations

import html
import io
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st

from transferlens.config import Settings, load_settings
from transferlens.extract.pipeline import ExtractionUnavailable, run_extraction
from transferlens.extract.textract import ExtractionError
from transferlens.policy import load_policy
from transferlens.review import ReviewError, decide_export, evaluate, findings_for_run, override_finding, supersede
from transferlens.scoring.baseline import BaselineError, load_manual_baseline
from transferlens.scoring.metrics import compare_packet
from transferlens.sessions import ReviewSession, SessionError
from transferlens.ui.packets import UploadError, accept_pdf, load_demo_packet
from transferlens.ui.preview import illustrative_results
from transferlens.ui.styles import CSS, ROLE_LABELS, STATUS_LABELS

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ("Case", "Review", "Outcome", "Metrics")


def main() -> None:
    st.set_page_config(page_title="TransferLens", page_icon="TL", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    _ensure_state()
    settings = load_settings({"TRANSFERLENS_PROJECT_ROOT": str(ROOT), **_public_env()})
    policy = load_policy(settings.policy_path)
    _sidebar(settings.runtime)
    screen = st.session_state.screen
    if screen == "Case":
        _case(policy)
    elif screen == "Review":
        _review(policy, settings.demo_reference_date, settings)
    elif screen == "Outcome":
        _outcome()
    else:
        _metrics()


def _public_env() -> dict[str, str]:
    import os

    kept = {}
    for name in (
        "TRANSFERLENS_RUNTIME",
        "TRANSFERLENS_DATA_DIR",
        "TRANSFERLENS_BUCKET",
        "TRANSFERLENS_TABLE",
        "TRANSFERLENS_LOG_GROUP",
        "TRANSFERLENS_EXPECTED_ACCOUNT_ID",
        "TRANSFERLENS_DEMO_REFERENCE_DATE",
        "BEDROCK_MODEL_ID",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        if name in os.environ:
            kept[name] = os.environ[name]
    return kept


def _ensure_state() -> None:
    st.session_state.setdefault("screen", "Case")
    st.session_state.setdefault("case_id", "")
    st.session_state.setdefault("documents", {})
    st.session_state.setdefault("clock", None)
    st.session_state.setdefault("findings", ())
    st.session_state.setdefault("run_id", "run-1")
    st.session_state.setdefault("layout", "waiting")
    st.session_state.setdefault("run_serial", 1)


def _sidebar(runtime: str) -> None:
    with st.sidebar:
        st.markdown('<p class="brand">TransferLens</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="brand-sub">Full cash transfer into an open Traditional IRA. Nothing is submitted.</p>',
            unsafe_allow_html=True,
        )
        choice = st.radio("Workspace", SCREENS, index=SCREENS.index(st.session_state.screen), label_visibility="collapsed")
        st.session_state.screen = choice
        st.markdown(f'<p class="fine">{html.escape(_runtime_note(runtime))}</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="fine">Demo policy only. These are not verified LPL processing rules.</p>',
            unsafe_allow_html=True,
        )


def _case(policy: dict) -> None:
    st.title("Prepare the packet")
    st.markdown(
        '<p class="lede">Add the four documents. The review compares them with each other and with the demo policy.</p>',
        unsafe_allow_html=True,
    )
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Demo packet")
        st.write("Case TR-2026-001. Four static PDFs, already assigned to their roles.")
        if st.button("Open demo packet", type="primary"):
            case_id, documents = load_demo_packet(ROOT)
            _open_case(case_id, documents)
            st.rerun()
    with right:
        st.subheader("Upload a packet")
        case_id = st.text_input("Case id", value="local-packet")
        uploads = {}
        for role in policy["required_document_roles"]:
            uploads[role] = st.file_uploader(ROLE_LABELS[role], type=["pdf"], key=f"upload-{role}")
        if st.button("Use uploaded PDFs"):
            _open_uploads(case_id.strip(), uploads, policy["required_document_roles"])
    _document_table()
    if st.session_state.documents and st.button("Continue to review"):
        st.session_state.screen = "Review"
        st.rerun()


def _open_case(case_id: str, documents: dict) -> None:
    st.session_state.case_id = case_id
    st.session_state.documents = documents
    st.session_state.clock = None
    st.session_state.findings = ()
    st.session_state.run_serial = 1
    st.session_state.run_id = "run-1"
    st.session_state.layout = "waiting"


def _open_uploads(case_id: str, uploads: dict, roles: list[str]) -> None:
    if not case_id:
        st.error("Enter a case id.")
        return
    missing = [ROLE_LABELS[role] for role in roles if uploads[role] is None]
    if missing:
        st.error("Still needed: " + ", ".join(missing) + ".")
        return
    documents = {}
    try:
        for role in roles:
            uploaded = uploads[role]
            documents[role] = accept_pdf(uploaded.name, uploaded.getvalue())
    except UploadError as exc:
        st.error(str(exc))
        return
    _open_case(case_id, documents)
    st.rerun()


def _document_table() -> None:
    documents = st.session_state.documents
    if not documents:
        return
    st.subheader(st.session_state.case_id or "Packet")
    rows = []
    for role, document in documents.items():
        rows.append(
            {
                "Role": ROLE_LABELS.get(role, role),
                "File": document["filename"],
                "SHA-256": document["sha256"][:12],
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def _review(policy: dict, reference_date, settings: Settings) -> None:
    if not st.session_state.documents:
        st.title("Review")
        st.info("Open a packet on the Case screen first.")
        return
    st.title("Review")
    st.markdown(
        f'<p class="lede">{html.escape(st.session_state.case_id)} · reference date {reference_date.isoformat()}</p>',
        unsafe_allow_html=True,
    )
    _timer()
    if st.session_state.layout == "illustrative":
        st.markdown(
            '<div class="banner">Illustrative check layout for the demo packet. Textract and Bedrock did not read these pages. This preview is excluded from the metrics.</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.layout == "replay":
        st.markdown(
            '<div class="banner">Replay is using saved Textract and Bedrock output. It is excluded from live AI timing.</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.layout != "live":
        st.markdown(f'<div class="banner quiet">{html.escape(_extract_banner(settings.runtime))}</div>', unsafe_allow_html=True)
        if st.button("Extract fields"):
            _extract(settings, policy, reference_date)
    document, findings = st.columns([1.15, 0.85], gap="large")
    with document:
        _viewer()
    with findings:
        if st.button("Show illustrative check layout"):
            results = illustrative_results(policy, reference_date)
            st.session_state.findings = findings_for_run(st.session_state.run_id, results)
            st.session_state.layout = "illustrative"
            st.rerun()
        _finding_list(policy)


def _extract(settings: Settings, policy: dict, reference_date) -> None:
    try:
        extracted = run_extraction(
            settings,
            st.session_state.case_id,
            st.session_state.documents,
            st.session_state.run_id,
        )
    except (ExtractionUnavailable, ExtractionError) as exc:
        st.warning(str(exc))
        return
    results = evaluate(
        policy,
        reference_date,
        extracted.claims,
        extracted.blocks,
        extracted.signatures,
        frozenset(st.session_state.documents),
    )
    st.session_state.findings = findings_for_run(st.session_state.run_id, results)
    st.session_state.layout = "replay" if settings.replay else "live"
    st.rerun()


def _runtime_note(runtime: str) -> str:
    if runtime == "aws":
        return "Runtime: aws. Extract fields uploads this packet, then calls Textract and Bedrock."
    if runtime == "replay":
        return "Runtime: replay. Extract fields reads saved Textract and Bedrock output."
    return "Runtime: local. Textract and Bedrock are not called."


def _extract_banner(runtime: str) -> str:
    if runtime == "aws":
        return "Extract fields stores the PDFs, reads them with Textract, and asks Bedrock for cited fields. The caller account is checked first."
    return "Textract reads the pages. Bedrock returns fields tied to those text blocks. This local session does not call either service."


def _timer() -> None:
    clock = st.session_state.clock
    work = "Not started" if clock is None else _format_seconds(clock.work_seconds())
    c1, c2, c3, c4, c5 = st.columns([1.4, 1, 1, 1, 1])
    c1.metric("Work time", work)
    if c2.button("Start"):
        _clock("review_started")
    if c3.button("Pause"):
        _clock("review_paused")
    if c4.button("Resume"):
        _clock("review_resumed")
    if c5.button("Finish"):
        _clock("review_finished")


def _clock(event_type: str) -> None:
    clock = st.session_state.clock
    if clock is None:
        clock = ReviewSession(replay=False)
        st.session_state.clock = clock
    try:
        clock.record(uuid4().hex, event_type, datetime.now(timezone.utc))
    except SessionError as exc:
        st.warning(str(exc))
        return
    st.rerun()


def _viewer() -> None:
    documents = st.session_state.documents
    role = st.selectbox(
        "Document",
        list(documents),
        format_func=lambda item: ROLE_LABELS.get(item, item),
    )
    document = documents[role]
    count = _page_count(document["data"])
    page = st.number_input("Page", min_value=1, max_value=max(count, 1), value=1)
    image = _render_page(document["data"], int(page) - 1)
    if image is None:
        st.download_button("Download PDF", document["data"], file_name=document["filename"])
        return
    st.markdown('<div class="doc-frame">', unsafe_allow_html=True)
    st.image(image, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption(f"{document['filename']} · page {int(page)} of {count}")


@st.cache_data(show_spinner=False)
def _page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


@st.cache_data(show_spinner=False)
def _render_page(data: bytes, page_index: int) -> bytes | None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        if page_index < 0 or page_index >= len(pdf):
            return None
        bitmap = pdf[page_index].render(scale=1.7)
        buffer = io.BytesIO()
        bitmap.to_pil().save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None
    finally:
        pdf.close()


def _finding_list(policy: dict) -> None:
    findings = st.session_state.findings
    if not findings or st.session_state.layout == "waiting":
        st.subheader("Checks")
        for group in policy["rule_groups"]:
            st.markdown(
                f'<div class="finding"><span class="pill waiting">Waiting</span><strong>{html.escape(group["title"])}</strong>'
                "<p>Waiting for extracted fields.</p></div>",
                unsafe_allow_html=True,
            )
        return
    st.subheader("Checks")
    for finding in findings:
        status = finding.result.status
        label = STATUS_LABELS.get(status, status)
        st.markdown(
            f'<div class="finding"><span class="pill {html.escape(status)}">{html.escape(label)}</span>'
            f"<strong>{html.escape(_humanize(finding.result.explanation))}</strong>"
            f"<p>{html.escape(finding.result.recommended_action)}</p></div>",
            unsafe_allow_html=True,
        )


def _outcome() -> None:
    st.title("Outcome")
    if not st.session_state.documents:
        st.info("Open a packet on the Case screen first.")
        return
    findings = st.session_state.findings
    layout = st.session_state.layout
    if layout == "illustrative" and findings:
        decision = decide_export(findings, st.session_state.run_id)
        allowed = False
        decision_reasons = (*decision.reasons, "Illustrative layout is excluded from export.")
        st.markdown(
            '<div class="banner">This outcome is the illustrative layout. It is not an extraction result and cannot be exported as a finished review.</div>',
            unsafe_allow_html=True,
        )
    elif layout in {"replay", "live"} and findings:
        decision = decide_export(findings, st.session_state.run_id)
        allowed = decision.allowed and layout == "live"
        decision_reasons = decision.reasons
        if layout == "replay":
            allowed = False
            decision_reasons = (*decision_reasons, "Replay is excluded from packet export.")
    else:
        allowed = False
        decision_reasons = ("Field extraction has not run.",)
        st.markdown(
            '<div class="banner quiet">Export stays closed until the six checks have run on extracted fields and every blocking finding is resolved.</div>',
            unsafe_allow_html=True,
        )
    st.subheader("Export")
    if allowed:
        st.success("Blocking findings are resolved. Packet export can be enabled after a live review.")
    else:
        st.error("Export is closed.")
        for reason in decision_reasons:
            st.write(reason)
    blocking = [item for item in findings if item.result.blocking and item.disposition == "unresolved"]
    if blocking and layout in {"illustrative", "live"}:
        st.subheader("Override")
        st.caption("An override needs a recorded reason. Illustrative overrides are shown here and are not saved as a measured review.")
        labels = {f"{item.result.rule_id} — {item.result.explanation}": item for item in blocking}
        choice = st.selectbox("Blocking finding", list(labels))
        reason = st.text_input("Reason")
        if st.button("Record override"):
            try:
                updated = override_finding(labels[choice], reason)
            except ReviewError as exc:
                st.warning(str(exc))
            else:
                st.session_state.findings = tuple(
                    updated if item.finding_id == updated.finding_id else item for item in findings
                )
                st.rerun()
    st.subheader("Corrected document")
    st.caption("A correction is a new upload. It starts another run, and earlier approvals do not carry forward.")
    role = st.selectbox("Role to replace", list(ROLE_LABELS), format_func=lambda item: ROLE_LABELS[item])
    replacement = st.file_uploader("Corrected PDF", type=["pdf"], key="correction-pdf")
    if st.button("Replace document") and replacement is not None:
        try:
            document = accept_pdf(replacement.name, replacement.getvalue())
        except UploadError as exc:
            st.error(str(exc))
        else:
            st.session_state.documents[role] = document
            st.session_state.findings = supersede(st.session_state.findings)
            st.session_state.run_serial += 1
            st.session_state.run_id = f"run-{st.session_state.run_serial}"
            st.session_state.layout = "waiting"
            st.rerun()


def _metrics() -> None:
    st.title("Time and accuracy")
    st.markdown(
        '<p class="lede">Manual time comes from the stopwatch CSV. Assisted time comes from a finished live review. Replay and the illustrative layout are excluded.</p>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("Manual baseline CSV", type=["csv"])
    manual_value, manual_note = _manual_tile(uploaded)
    tiles = (
        ("Manual review", manual_value, manual_note),
        ("Assisted review", "Not measured", "No live extraction session"),
        ("Manual work reduced", "Not measured", "Needs assisted time as well"),
        ("Defects found", "Not measured", "Scored after a live review"),
        ("Packet readiness", "Not measured", "Ready decision against the case"),
    )
    columns = st.columns(len(tiles))
    for column, (label, value, note) in zip(columns, tiles, strict=True):
        with column:
            st.markdown(
                f'<div class="tile"><div class="tile-label">{html.escape(label)}</div>'
                f'<div class="tile-value">{html.escape(value)}</div>'
                f'<div class="tile-note">{html.escape(note)}</div></div>',
                unsafe_allow_html=True,
            )
    st.caption("A screen example is 12 minutes, 4 minutes, 67 percent, and 3 of 3. Those figures are the layout, not a result.")


def _manual_tile(uploaded) -> tuple[str, str]:
    if uploaded is None:
        return "Not measured", "No completed baseline row"
    schema = ROOT / "benchmark" / "manual_baseline_schema.json"
    target = ROOT / ".local-data" / "baseline-upload.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(uploaded.getvalue())
    try:
        rows = load_manual_baseline(target, schema)
    except BaselineError as exc:
        return "Not measured", str(exc)
    packet_id = st.session_state.case_id or "TR-2026-001"
    snapshot = compare_packet(packet_id, rows, [])
    if snapshot.manual_work_seconds is None:
        return "Not measured", "No positive manual baseline for this packet"
    label = "session" if snapshot.sample_manual == 1 else "sessions"
    return _format_seconds(int(snapshot.manual_work_seconds)), f"{snapshot.sample_manual} completed {label}"


def _humanize(text: str) -> str:
    for role, label in ROLE_LABELS.items():
        text = text.replace(role, label)
    replacements = {
        "source_account_number": "Source account",
        "receiving_account_number": "Receiving account",
        "full_transfer": "Full transfer",
        "cash_transfer": "Cash transfer",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _format_seconds(seconds: int) -> str:
    minutes, rest = divmod(max(seconds, 0), 60)
    return f"{minutes}:{rest:02d}"


if __name__ == "__main__":
    main()
