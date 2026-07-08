from __future__ import annotations

import streamlit as st
import pandas as pd
import altair as alt

from rtce_client import RTCEClient, RTCEConfig

st.set_page_config(page_title="Agent Observability", layout="wide")


@st.cache_resource
def get_client() -> RTCEClient:
    return RTCEClient(RTCEConfig.from_env())


@st.cache_data(ttl=15)
def load_sessions() -> pd.DataFrame:
    client = get_client()
    return client.query(
        "session_summaries",
        'SELECT "TRACE_ID", "SERVICE_NAME", "timestamp", "DURATION_MS", '
        '"TOTAL_LLM_CALLS", "TOTAL_TOOL_CALLS", "TOTAL_INPUT_TOKENS", '
        '"TOTAL_OUTPUT_TOKENS", "EXIT_REASON", "ERROR" '
        'FROM "session_summaries" ORDER BY "timestamp" DESC LIMIT 200',
    )


@st.cache_data(ttl=15)
def load_llm_calls() -> pd.DataFrame:
    client = get_client()
    return client.query(
        "llm_call_completed",
        'SELECT "TRACE_ID", "SPAN_ID", "PARENT_SPAN_ID", "SERVICE_NAME", '
        '"MODEL", "PROVIDER", "DURATION_MS", "INPUT_TOKENS", "OUTPUT_TOKENS", '
        '"TOTAL_TOKENS", "RESPONSE_CONTENT", "FINISH_REASON", "ERROR" '
        'FROM "llm_call_completed" LIMIT 200',
    )


@st.cache_data(ttl=15)
def load_tool_calls() -> pd.DataFrame:
    client = get_client()
    return client.query(
        "tool_call_completed",
        'SELECT "TRACE_ID", "SPAN_ID", "PARENT_SPAN_ID", "SERVICE_NAME", '
        '"TOOL_NAME", "TOOL_INPUT", "TOOL_OUTPUT", '
        '"DURATION_MS", "SUCCESS", "ERROR" '
        'FROM "tool_call_completed" LIMIT 200',
    )


@st.cache_data(ttl=15)
def load_trace_tool_calls(trace_id: str) -> pd.DataFrame:
    client = get_client()
    return client.query(
        "tool_call_completed",
        f'SELECT "TRACE_ID", "SPAN_ID", "PARENT_SPAN_ID", "SERVICE_NAME", '
        f'"TOOL_NAME", "TOOL_INPUT", "TOOL_OUTPUT", '
        f'"DURATION_MS", "SUCCESS", "ERROR" '
        f'FROM "tool_call_completed" WHERE "TRACE_ID" = \'{trace_id}\' LIMIT 50',
    )


@st.cache_data(ttl=15)
def load_trace_llm_calls(trace_id: str) -> pd.DataFrame:
    client = get_client()
    return client.query(
        "llm_call_completed",
        f'SELECT "TRACE_ID", "SPAN_ID", "PARENT_SPAN_ID", "SERVICE_NAME", '
        f'"MODEL", "PROVIDER", "DURATION_MS", "INPUT_TOKENS", "OUTPUT_TOKENS", '
        f'"TOTAL_TOKENS", "RESPONSE_CONTENT", "FINISH_REASON", "ERROR" '
        f'FROM "llm_call_completed" WHERE "TRACE_ID" = \'{trace_id}\' LIMIT 50',
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Agent Observability")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Sessions", "Session Detail", "Models", "Tools"],
)

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
if page == "Overview":
    st.title("Overview")

    sessions = load_sessions()
    llm_calls = load_llm_calls()
    tool_calls = load_tool_calls()

    if sessions.empty:
        st.warning("No session data available yet.")
        st.stop()

    total_sessions = len(sessions)
    error_sessions = len(sessions[sessions["EXIT_REASON"] == "error"])
    error_rate = error_sessions / total_sessions * 100 if total_sessions else 0
    total_tokens = (
        sessions["TOTAL_INPUT_TOKENS"].sum() + sessions["TOTAL_OUTPUT_TOKENS"].sum()
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sessions", total_sessions)
    col2.metric("Error Rate", f"{error_rate:.1f}%")
    col3.metric("Total LLM Calls", int(sessions["TOTAL_LLM_CALLS"].sum()))
    col4.metric("Total Tokens", f"{int(total_tokens):,}")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Total Tool Calls", int(sessions["TOTAL_TOOL_CALLS"].sum()))
    col6.metric("Avg Duration (ms)", f"{sessions['DURATION_MS'].mean():.0f}")
    col7.metric(
        "Avg Tokens / Session",
        f"{total_tokens / total_sessions:,.0f}" if total_sessions else "0",
    )
    col8.metric("Avg LLM Calls / Session", f"{sessions['TOTAL_LLM_CALLS'].mean():.1f}")

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Sessions by Status")
        status_counts = sessions["EXIT_REASON"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        chart = (
            alt.Chart(status_counts)
            .mark_bar()
            .encode(
                x=alt.X("Status:N"),
                y=alt.Y("Count:Q"),
                color=alt.Color(
                    "Status:N",
                    scale=alt.Scale(
                        domain=["completed", "error"],
                        range=["#4CAF50", "#F44336"],
                    ),
                ),
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("LLM Calls by Model")
        if not llm_calls.empty:
            model_counts = llm_calls["MODEL"].value_counts().reset_index()
            model_counts.columns = ["Model", "Count"]
            chart = (
                alt.Chart(model_counts)
                .mark_bar()
                .encode(
                    x=alt.X("Count:Q"),
                    y=alt.Y("Model:N", sort="-x"),
                    color=alt.Color("Model:N", legend=None),
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("Recent Errors")
    errors = sessions[sessions["EXIT_REASON"] == "error"][
        ["TRACE_ID", "SERVICE_NAME", "DURATION_MS", "TOTAL_LLM_CALLS", "ERROR"]
    ]
    if errors.empty:
        st.success("No recent errors.")
    else:
        st.dataframe(errors, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
elif page == "Sessions":
    st.title("Sessions")

    sessions = load_sessions()

    if sessions.empty:
        st.warning("No session data available yet.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect(
            "Exit Reason",
            options=sessions["EXIT_REASON"].unique().tolist(),
            default=sessions["EXIT_REASON"].unique().tolist(),
        )
    with col2:
        service_filter = st.multiselect(
            "Service",
            options=sessions["SERVICE_NAME"].unique().tolist(),
            default=sessions["SERVICE_NAME"].unique().tolist(),
        )

    filtered = sessions[
        sessions["EXIT_REASON"].isin(status_filter)
        & sessions["SERVICE_NAME"].isin(service_filter)
    ]

    st.dataframe(
        filtered[
            [
                "TRACE_ID",
                "SERVICE_NAME",
                "timestamp",
                "DURATION_MS",
                "TOTAL_LLM_CALLS",
                "TOTAL_TOOL_CALLS",
                "TOTAL_INPUT_TOKENS",
                "TOTAL_OUTPUT_TOKENS",
                "EXIT_REASON",
                "ERROR",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "TRACE_ID": st.column_config.TextColumn("Trace ID", width="medium"),
            "DURATION_MS": st.column_config.NumberColumn("Duration (ms)", format="%.1f"),
            "TOTAL_INPUT_TOKENS": st.column_config.NumberColumn("Input Tokens"),
            "TOTAL_OUTPUT_TOKENS": st.column_config.NumberColumn("Output Tokens"),
        },
    )

    st.divider()
    st.subheader("Duration Distribution")
    hist = (
        alt.Chart(filtered)
        .mark_bar()
        .encode(
            alt.X("DURATION_MS:Q", bin=alt.Bin(maxbins=20), title="Duration (ms)"),
            alt.Y("count()", title="Sessions"),
            color=alt.Color("EXIT_REASON:N", scale=alt.Scale(
                domain=["completed", "error"], range=["#4CAF50", "#F44336"]
            )),
        )
        .properties(height=300)
    )
    st.altair_chart(hist, use_container_width=True)

# ---------------------------------------------------------------------------
# Session Detail
# ---------------------------------------------------------------------------
elif page == "Session Detail":
    st.title("Session Detail")

    sessions = load_sessions()
    trace_ids = sessions["TRACE_ID"].tolist() if not sessions.empty else []

    col_select, col_input = st.columns([1, 1])
    with col_select:
        dropdown_trace = st.selectbox(
            "Select from completed sessions",
            [""] + trace_ids,
            index=0,
        )
    with col_input:
        manual_trace = st.text_input(
            "Or paste a Trace / Session ID",
            placeholder="e.g. eddc2fa7-767f-425a-8472-bcf33f58c52e",
        )

    selected_trace = manual_trace.strip() or dropdown_trace
    if not selected_trace:
        st.info("Select a session or paste a trace ID above.")
        st.stop()

    # Show session summary metrics if available
    session_match = sessions[sessions["TRACE_ID"] == selected_trace] if not sessions.empty else pd.DataFrame()
    if not session_match.empty:
        session_row = session_match.iloc[0]

        def _safe_int(val: object) -> str:
            try:
                if pd.isna(val):
                    return "—"
                return str(int(val))
            except (ValueError, TypeError):
                return "—"

        def _safe_float(val: object) -> str:
            try:
                if pd.isna(val):
                    return "—"
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return "—"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Duration (ms)", _safe_float(session_row.get("DURATION_MS")))
        col2.metric("LLM Calls", _safe_int(session_row.get("TOTAL_LLM_CALLS")))
        col3.metric("Tool Calls", _safe_int(session_row.get("TOTAL_TOOL_CALLS")))
        col4.metric("Status", session_row.get("EXIT_REASON", "—") or "—")

        col5, col6, col7, _ = st.columns(4)
        col5.metric("Input Tokens", _safe_int(session_row.get("TOTAL_INPUT_TOKENS")))
        col6.metric("Output Tokens", _safe_int(session_row.get("TOTAL_OUTPUT_TOKENS")))
        in_tok = session_row.get("TOTAL_INPUT_TOKENS")
        out_tok = session_row.get("TOTAL_OUTPUT_TOKENS")
        try:
            total_tok = int(in_tok or 0) + int(out_tok or 0) if pd.notna(in_tok) and pd.notna(out_tok) else "—"
        except (ValueError, TypeError):
            total_tok = "—"
        col7.metric("Total Tokens", total_tok)

        err = session_row.get("ERROR")
        if pd.notna(err) and err:
            st.error(f"Error: {err}")
    else:
        st.info(f"Session `{selected_trace}` is active (no session.end yet) — showing live events.")

    st.divider()

    # Load completed spans from derived topics
    tool_calls = load_trace_tool_calls(selected_trace)
    llm_calls_trace = load_trace_llm_calls(selected_trace)

    has_data = not tool_calls.empty or not llm_calls_trace.empty

    if not has_data:
        st.warning("No completed spans found for this trace yet. Events may still be processing through Flink.")
        st.stop()

    # Show quick stats for active sessions
    if session_match.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Tool Calls", len(tool_calls))
        col2.metric("LLM Calls", len(llm_calls_trace))
        unique_tools = tool_calls["TOOL_NAME"].nunique() if not tool_calls.empty else 0
        col3.metric("Unique Tools", unique_tools)

    # Build the trace waterfall from completed spans
    st.subheader("Trace Waterfall")

    waterfall_rows = []

    for _, row in llm_calls_trace.iterrows():
        error = row.get("ERROR")
        error = error if pd.notna(error) else None
        duration = row.get("DURATION_MS")
        model = row.get("MODEL")
        label = f"LLM: {model if pd.notna(model) else 'unknown'}"

        in_tok = row.get("INPUT_TOKENS")
        out_tok = row.get("OUTPUT_TOKENS")
        tokens = None
        if pd.notna(in_tok) and pd.notna(out_tok):
            tokens = f"{int(in_tok)} in / {int(out_tok)} out"

        parent = row.get("PARENT_SPAN_ID")
        waterfall_rows.append({
            "Span": label,
            "Span ID": str(row["SPAN_ID"])[:12] + "...",
            "Parent": (str(parent)[:12] + "...") if pd.notna(parent) and parent else "—",
            "Duration (ms)": round(float(duration), 1) if pd.notna(duration) else None,
            "Tokens": tokens,
            "Error": error,
            "color": "#F44336" if error else "#2196F3",
        })

    for _, row in tool_calls.iterrows():
        error = row.get("ERROR")
        error = error if pd.notna(error) else None
        duration = row.get("DURATION_MS")
        tool_name = row.get("TOOL_NAME")
        label = f"Tool: {tool_name if pd.notna(tool_name) else 'unknown'}"

        parent = row.get("PARENT_SPAN_ID")
        waterfall_rows.append({
            "Span": label,
            "Span ID": str(row["SPAN_ID"])[:12] + "...",
            "Parent": (str(parent)[:12] + "...") if pd.notna(parent) and parent else "—",
            "Duration (ms)": round(float(duration), 1) if pd.notna(duration) else None,
            "Tokens": None,
            "Error": error,
            "color": "#F44336" if error else "#FF9800",
        })

    if waterfall_rows:
        wf_df = pd.DataFrame(waterfall_rows)

        # Waterfall bar chart
        wf_chart_data = wf_df[wf_df["Duration (ms)"].notna()].copy()
        if not wf_chart_data.empty:
            wf_chart_data = wf_chart_data.sort_values("Duration (ms)", ascending=False).reset_index(drop=True)
            wf_chart_data["index"] = range(len(wf_chart_data))

            chart = (
                alt.Chart(wf_chart_data)
                .mark_bar()
                .encode(
                    x=alt.X("Duration (ms):Q", title="Duration (ms)"),
                    y=alt.Y("index:O", title="", axis=alt.Axis(labels=False, ticks=False)),
                    color=alt.Color("color:N", scale=None),
                    tooltip=["Span", "Duration (ms)", "Tokens", "Error"],
                )
                .properties(height=max(len(wf_chart_data) * 35, 100))
            )

            text = chart.mark_text(align="left", dx=5, fontSize=12).encode(
                text="Span:N",
            )

            st.altair_chart(chart + text, use_container_width=True)
    else:
        st.info("No completed spans found — events may still be processing.")

    # Expandable span details with input/output
    st.divider()
    st.subheader("Span Details")

    # Interleave LLM and tool calls, sorted by start_time if available
    all_spans = []
    for _, row in llm_calls_trace.iterrows():
        all_spans.append(("llm", row))
    for _, row in tool_calls.iterrows():
        all_spans.append(("tool", row))

    # Sort by START_TIME if present
    def _sort_key(item: tuple) -> str:
        row = item[1]
        st_val = row.get("START_TIME", "")
        return str(st_val) if pd.notna(st_val) else ""
    all_spans.sort(key=_sort_key)

    def _try_parse_json(raw: str) -> object | None:
        import json as _json
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError, ValueError):
            return None

    def _pretty_json(raw: str, max_len: int = 4000) -> str:
        """Pretty-print JSON, recursively unpacking stringified JSON values."""
        import json as _json
        text = str(raw)
        obj = _try_parse_json(text)
        if obj is not None:
            obj = _deep_unpack_json(obj)
            text = _json.dumps(obj, indent=2, ensure_ascii=False)
        if len(text) > max_len:
            text = text[:max_len] + "\n… (truncated)"
        return text

    def _deep_unpack_json(obj: object) -> object:
        """Recursively parse string values that look like JSON."""
        if isinstance(obj, dict):
            return {k: _deep_unpack_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_deep_unpack_json(v) for v in obj]
        if isinstance(obj, str) and len(obj) > 1:
            parsed = _try_parse_json(obj)
            if isinstance(parsed, (dict, list)):
                return _deep_unpack_json(parsed)
        return obj

    def _render_tool_output(container, raw: str, max_len: int = 5000) -> None:
        """Render tool output with special handling for stdout/stderr structure."""
        import json as _json
        obj = _try_parse_json(raw)
        if isinstance(obj, dict) and "stdout" in obj:
            stdout = obj.get("stdout", "")
            stderr = obj.get("stderr", "")
            if stdout:
                stdout_parsed = _try_parse_json(stdout)
                if isinstance(stdout_parsed, (dict, list)):
                    stdout_parsed = _deep_unpack_json(stdout_parsed)
                    display = _json.dumps(stdout_parsed, indent=2, ensure_ascii=False)
                    if len(display) > max_len:
                        display = display[:max_len] + "\n… (truncated)"
                    container.code(display, language="json")
                else:
                    if len(stdout) > max_len:
                        stdout = stdout[:max_len] + "\n… (truncated)"
                    container.code(stdout, language=None)
            if stderr:
                container.markdown("**stderr:**")
                if len(stderr) > 2000:
                    stderr = stderr[:2000] + "\n… (truncated)"
                container.code(stderr, language=None)
            if not stdout and not stderr:
                container.caption("No output.")
        else:
            container.code(_pretty_json(raw, max_len=max_len), language="json")

    for i, (span_type, row) in enumerate(all_spans):
        error = row.get("ERROR")
        has_error = pd.notna(error) and error

        if span_type == "llm":
            model = row.get("MODEL", "unknown")
            duration = row.get("DURATION_MS")
            dur_str = f"{float(duration):.0f}ms" if pd.notna(duration) else "—"
            in_tok = row.get("INPUT_TOKENS")
            out_tok = row.get("OUTPUT_TOKENS")
            tok_str = ""
            if pd.notna(in_tok) and pd.notna(out_tok):
                tok_str = f" | {int(in_tok)} in / {int(out_tok)} out"
            icon = "🔴" if has_error else "🟢"
            header = f"{icon} LLM: {model} — {dur_str}{tok_str}"

            with st.expander(header, expanded=has_error):
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.markdown(f"**Span ID**  \n`{row.get('SPAN_ID', '—')}`")
                col_b.markdown(f"**Provider**  \n{row.get('PROVIDER', '—')}")
                col_c.markdown(f"**Finish Reason**  \n{row.get('FINISH_REASON', '—')}")
                col_d.markdown(f"**Duration**  \n{dur_str}")

                if has_error:
                    st.error(f"Error: {error}")

                response = row.get("RESPONSE_CONTENT")
                if pd.notna(response) and response:
                    st.markdown("##### Response")
                    st.code(_pretty_json(response), language="json")

        elif span_type == "tool":
            tool_name = row.get("TOOL_NAME", "unknown")
            duration = row.get("DURATION_MS")
            dur_str = f"{float(duration):.0f}ms" if pd.notna(duration) else "—"
            success = row.get("SUCCESS")
            icon = "🔴" if has_error else ("🟢" if success else "🟡")
            header = f"{icon} Tool: {tool_name} — {dur_str}"

            with st.expander(header, expanded=has_error):
                col_a, col_b, col_c = st.columns(3)
                col_a.markdown(f"**Span ID**  \n`{row.get('SPAN_ID', '—')}`")
                col_b.markdown(f"**Duration**  \n{dur_str}")
                col_c.markdown(f"**Success**  \n{'Yes' if success else 'No'}")

                if has_error:
                    st.error(f"Error: {error}")

                tool_input = row.get("TOOL_INPUT")
                tool_output = row.get("TOOL_OUTPUT")
                has_input = pd.notna(tool_input) and tool_input
                has_output = pd.notna(tool_output) and tool_output

                if has_input or has_output:
                    tab_input, tab_output = st.tabs(["Input", "Output"])
                    with tab_input:
                        if has_input:
                            st.code(_pretty_json(tool_input), language="json")
                        else:
                            st.caption("No input recorded.")
                    with tab_output:
                        if has_output:
                            _render_tool_output(st, str(tool_output))
                        else:
                            st.caption("No output recorded.")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
elif page == "Models":
    st.title("Model Performance")

    llm_calls = load_llm_calls()
    if llm_calls.empty:
        st.warning("No LLM call data available.")
        st.stop()

    models = llm_calls["MODEL"].unique().tolist()

    # Per-model stats
    stats = []
    for model in models:
        subset = llm_calls[llm_calls["MODEL"] == model]
        error_count = subset["ERROR"].notna().sum()
        stats.append({
            "Model": model,
            "Provider": subset["PROVIDER"].iloc[0],
            "Calls": len(subset),
            "Avg Duration (ms)": round(subset["DURATION_MS"].mean(), 1),
            "P95 Duration (ms)": round(subset["DURATION_MS"].quantile(0.95), 1),
            "Avg Input Tokens": int(subset["INPUT_TOKENS"].mean()),
            "Avg Output Tokens": int(subset["OUTPUT_TOKENS"].mean()),
            "Error Count": int(error_count),
            "Error Rate": f"{error_count / len(subset) * 100:.1f}%",
        })

    st.dataframe(pd.DataFrame(stats), use_container_width=True, hide_index=True)

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Duration by Model")
        box = (
            alt.Chart(llm_calls)
            .mark_boxplot(extent="min-max")
            .encode(
                x=alt.X("MODEL:N", title="Model"),
                y=alt.Y("DURATION_MS:Q", title="Duration (ms)"),
                color="MODEL:N",
            )
            .properties(height=350)
        )
        st.altair_chart(box, use_container_width=True)

    with right:
        st.subheader("Token Usage by Model")
        token_data = llm_calls.melt(
            id_vars=["MODEL"],
            value_vars=["INPUT_TOKENS", "OUTPUT_TOKENS"],
            var_name="Token Type",
            value_name="Tokens",
        )
        token_data["Token Type"] = token_data["Token Type"].map({
            "INPUT_TOKENS": "Input",
            "OUTPUT_TOKENS": "Output",
        })
        bars = (
            alt.Chart(token_data)
            .mark_bar()
            .encode(
                x=alt.X("MODEL:N", title="Model"),
                y=alt.Y("mean(Tokens):Q", title="Avg Tokens"),
                color=alt.Color("Token Type:N", scale=alt.Scale(
                    domain=["Input", "Output"], range=["#2196F3", "#FF9800"]
                )),
                xOffset="Token Type:N",
            )
            .properties(height=350)
        )
        st.altair_chart(bars, use_container_width=True)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
elif page == "Tools":
    st.title("Tool Usage")

    tool_calls = load_tool_calls()
    if tool_calls.empty:
        st.warning("No tool call data available.")
        st.stop()

    tools = tool_calls["TOOL_NAME"].unique().tolist()

    stats = []
    for tool in tools:
        subset = tool_calls[tool_calls["TOOL_NAME"] == tool]
        success_count = subset["SUCCESS"].sum() if "SUCCESS" in subset.columns else len(subset)
        stats.append({
            "Tool": tool,
            "Calls": len(subset),
            "Avg Duration (ms)": round(subset["DURATION_MS"].mean(), 1),
            "Max Duration (ms)": round(subset["DURATION_MS"].max(), 1),
            "Success Rate": f"{success_count / len(subset) * 100:.1f}%",
            "Error Count": int(subset["ERROR"].notna().sum()),
        })

    st.dataframe(
        pd.DataFrame(stats).sort_values("Calls", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Call Volume by Tool")
        call_counts = tool_calls["TOOL_NAME"].value_counts().reset_index()
        call_counts.columns = ["Tool", "Count"]
        chart = (
            alt.Chart(call_counts)
            .mark_bar()
            .encode(
                x=alt.X("Count:Q"),
                y=alt.Y("Tool:N", sort="-x"),
                color=alt.Color("Tool:N", legend=None),
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("Duration by Tool")
        box = (
            alt.Chart(tool_calls)
            .mark_boxplot(extent="min-max")
            .encode(
                x=alt.X("TOOL_NAME:N", title="Tool"),
                y=alt.Y("DURATION_MS:Q", title="Duration (ms)"),
                color="TOOL_NAME:N",
            )
            .properties(height=300)
        )
        st.altair_chart(box, use_container_width=True)
