from __future__ import annotations

import json
import os
from base64 import b64encode
from dataclasses import dataclass

import requests
import pandas as pd
from dotenv import load_dotenv


@dataclass
class RTCEConfig:
    base_url: str
    auth_header: str

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> RTCEConfig:
        load_dotenv(dotenv_path)
        org_id = os.environ["RTCE_ORG_ID"]
        env_id = os.environ["RTCE_ENV_ID"]
        cluster_id = os.environ["RTCE_CLUSTER_ID"]
        api_key = os.environ["RTCE_API_KEY"]
        api_secret = os.environ["RTCE_API_SECRET"]

        base_url = (
            f"https://mcp.{os.environ.get('RTCE_REGION', 'us-east-1')}.aws.confluent.cloud"
            f"/mcp/v1/context-engine/organizations/{org_id}"
            f"/environments/{env_id}/kafka-clusters/{cluster_id}"
        )
        token = b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return cls(base_url=base_url, auth_header=f"Basic {token}")


class RTCEClient:
    def __init__(self, config: RTCEConfig) -> None:
        self._config = config
        self._request_id = 0

    def _call(self, method: str, tool_name: str, arguments: dict) -> dict:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = requests.post(
            self._config.base_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._config.auth_header,
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if "error" in data:
                    raise RuntimeError(data["error"]["message"])
                text = data["result"]["content"][0]["text"]
                return json.loads(text)
        raise RuntimeError(f"No data in RTCE response: {resp.text[:200]}")

    def list_topics(self) -> list[dict]:
        result = self._call("tools/call", "listTopics", {})
        return result["rows"]["topics"]

    def get_metadata(self, topic: str) -> list[dict]:
        result = self._call("tools/call", "getMetadata", {"topic_name": topic})
        return result["rows"]["columns"]

    def query(self, topic: str, sql: str, max_rows: int = 200) -> pd.DataFrame:
        result = self._call(
            "tools/call",
            "queryData",
            {"topic_name": topic, "query": sql, "max_result_rows": max_rows},
        )
        if result.get("status") == "error":
            err = result.get("error", {})
            detail = err.get("details", {}).get("detail", err.get("message", "unknown"))
            raise RuntimeError(f"RTCE query error: {detail}")
        rows_data = result.get("rows", {})
        columns = [c["name"] for c in rows_data.get("schema", {}).get("columns", [])]
        rows = [r["row"] for r in rows_data.get("data", [])]
        if not rows:
            return pd.DataFrame(columns=columns)
        df = pd.DataFrame(rows, columns=columns)
        return _coerce_types(df, rows_data["schema"]["columns"])


def _coerce_types(df: pd.DataFrame, schema_cols: list[dict]) -> pd.DataFrame:
    for col_def in schema_cols:
        name = col_def["name"]
        dtype = col_def["type"]["type"]
        if name not in df.columns:
            continue
        if dtype in ("BIGINT", "INTEGER", "INT"):
            df[name] = pd.to_numeric(df[name], errors="coerce").astype("Int64")
        elif dtype == "DOUBLE":
            df[name] = pd.to_numeric(df[name], errors="coerce")
        elif dtype == "BOOLEAN":
            df[name] = df[name].map({"TRUE": True, "FALSE": False, "true": True, "false": False})
    return df
