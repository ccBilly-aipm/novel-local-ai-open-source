import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.models.entities import ModelProvider
from app.providers.adapters import OpenAICompatibleAdapter


class _CapturingHandler(BaseHTTPRequestHandler):
    """Records the last request body so tests can assert on the payload."""

    captured_payload = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _CapturingHandler.captured_payload = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _run_generate(default_options):
    """Spin up a capturing server, run one generate_text, return the captured payload."""
    _CapturingHandler.captured_payload = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        provider = ModelProvider(
            name="cloud-mock",
            provider_type="cloud_openai_compatible",
            base_url="http://127.0.0.1:{}/v1".format(port),
            model="mock-model",
            api_key="",
            default_options_json=json.dumps(default_options),
            timeout_seconds=5,
        )
        result = OpenAICompatibleAdapter(provider).generate_text("测试提示", {})
        assert result.text == "OK"
        return _CapturingHandler.captured_payload
    finally:
        server.shutdown()
        server.server_close()


def test_token_param_defaults_to_max_tokens():
    """Without token_param, the payload keeps the legacy max_tokens key (no behavior change)."""
    payload = _run_generate({"max_tokens": 1234, "temperature": 0.5})
    assert payload is not None
    assert payload["max_tokens"] == 1234
    assert "max_completion_tokens" not in payload
    assert "token_param" not in payload  # must never leak into the request body


def test_token_param_renames_to_max_completion_tokens():
    """token_param=max_completion_tokens moves the value to the new key and drops max_tokens."""
    payload = _run_generate(
        {"max_tokens": 3200, "temperature": 0.7, "token_param": "max_completion_tokens"}
    )
    assert payload is not None
    assert payload["max_completion_tokens"] == 3200
    assert "max_tokens" not in payload
    assert "token_param" not in payload  # the control key must not reach the server
