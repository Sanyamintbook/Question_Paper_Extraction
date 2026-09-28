"""Opt-in client for a local or explicitly permitted remote chat endpoint."""
from __future__ import annotations
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ModelClient:
    def __init__(self):
        self.url = os.environ.get("PAPER_AI_URL", "http://127.0.0.1:11434/v1/chat/completions")
        self.model = os.environ.get("PAPER_AI_MODEL", "")
        self.key = os.environ.get("PAPER_AI_API_KEY", "")
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            raise ValueError("PAPER_AI_URL must be an HTTP(S) endpoint without embedded credentials")
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if not local and os.environ.get("PAPER_AI_ALLOW_REMOTE") != "1":
            raise ValueError("Remote document transfer requires PAPER_AI_ALLOW_REMOTE=1")
        if not local and parsed.scheme != "https":
            raise ValueError("Remote AI endpoints must use HTTPS")
        if not self.model:
            raise ValueError("Set PAPER_AI_MODEL before enabling AI analysis")

    def extract(self, instruction, payload, schema):
        body = {"model": self.model, "temperature": 0, "stream": False,
                "messages": [{"role": "system", "content": instruction},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "schema": schema.model_json_schema()}}}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        request = Request(self.url, json.dumps(body).encode(), headers)
        with urlopen(request, timeout=120) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("AI response exceeded size limit")
        content = json.loads(raw)["choices"][0]["message"]["content"]
        return schema.model_validate_json(content)
