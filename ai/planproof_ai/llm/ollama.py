import json
import urllib.error
import urllib.request
from typing import Callable

from ..errors import LLMUnavailableError, LLMResponseError
from .base import LLMAdapter, LLMRequest, LLMResponse

PostJson = Callable[[str, dict], dict]


def _default_post(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


class OllamaAdapter(LLMAdapter):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3",
                 post_json: PostJson | None = None, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_id = f"ollama/{model}"
        self._post = post_json or _default_post
        self.timeout = timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        prompt = request.prompt
        if request.diagnostics:
            prompt = f"{prompt}\n\nDiagnostics (redacted):\n{request.diagnostics}"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": request.max_tokens},
        }
        try:
            data = self._post(f"{self.base_url}/api/generate", payload)
        except urllib.error.URLError as exc:
            raise LLMUnavailableError(f"ollama unreachable: {exc}") from exc
        except (TimeoutError, OSError) as exc:
            raise LLMUnavailableError(f"ollama request failed: {exc}") from exc
        except LLMUnavailableError:
            raise
        text = data.get("response")
        if not isinstance(text, str):
            raise LLMResponseError("ollama response missing 'response' field")
        done = data.get("done", True)
        return LLMResponse(
            patch=None,
            rationale=text,
            model_id=self.model_id,
            finish_reason="stop" if done else "length",
            raw={"done": done, "model": data.get("model", self.model)},
        )
