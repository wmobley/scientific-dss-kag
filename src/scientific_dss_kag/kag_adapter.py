"""mode=kag: ask KAG's solver and return results whose citations are resolved against our evidence.

KAG runs in its own isolated virtualenv (its dependencies are old and third-party), as a subprocess from the
KAG project directory. That process holds only the local gateway token, never the upstream key; every model call
it makes is rate limited and counted by the gateway. Failures are explicit; there is no fallback to another mode.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit
import httpx
from .kag_citations import CitationError, answer_tags, resolve_citations
from .retrieval import IntegrationUnavailable
from .settings import LOOPBACK_HOSTS

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "kag_query.py"
MAX_RESULT_BYTES = 2 * 1024 * 1024


class KagUnavailable(IntegrationUnavailable):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class KagSettings:
    project_dir: Path = Path("work/kag/project/GwSubsidence")
    python: Path = Path("work/kag/.venv/bin/python")
    script: Path = SCRIPT
    server: str = "http://127.0.0.1:8887"
    domain: str = "groundwater-subsidence"
    timeout: int = 300

    def __post_init__(self):
        parts = urlsplit(self.server)
        if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS or parts.username or parts.password:
            raise ValueError("The OpenSPG server must be a loopback http address")
        if not 10 <= self.timeout <= 900:
            raise ValueError("KAG timeout must be between 10 and 900 seconds")

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(project_dir=Path(env.get("DSS_KAG_PROJECT_DIR", cls.project_dir)), python=Path(env.get("DSS_KAG_PYTHON", cls.python)),
                   server=env.get("DSS_KAG_SERVER", cls.server), domain=env.get("DSS_KAG_DOMAIN", cls.domain),
                   timeout=int(env.get("DSS_KAG_TIMEOUT", cls.timeout)))


class KagAdapter:
    def __init__(self, settings=None, runner=None):
        self.settings = settings or KagSettings.from_env()
        self._runner = runner or self._run_subprocess
        self._lock = threading.Lock()

    def installed(self):
        s = self.settings
        return s.python.is_file() and (s.project_dir / "kag_config.yaml").is_file() and s.script.is_file()

    def _check_server(self):
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
                response = client.get(self.settings.server + "/public/v1/project")
            if response.status_code != 200 or not isinstance(response.json(), list):
                raise ValueError("unexpected response")
        except (httpx.HTTPError, ValueError):
            raise KagUnavailable("kag_server_unavailable", "The local OpenSPG server is not responding; start the stack (docs/setup.md).") from None

    def _run_subprocess(self, query, out_path):
        s = self.settings
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}  # no secrets pass through
        try:
            # Absolute, but not resolved: following the venv's python symlink would leave the virtualenv. The process
            # changes into the project directory, so relative paths would otherwise stop pointing anywhere.
            absolute = lambda path: Path(os.path.abspath(path))
            done = subprocess.run([str(absolute(s.python)), str(absolute(s.script)), query, str(out_path)], cwd=absolute(s.project_dir),
                                  env=env, capture_output=True, timeout=s.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise KagUnavailable("kag_timeout", "KAG did not answer within the time limit.") from None
        except OSError:
            raise KagUnavailable("kag_unavailable", "KAG could not be started.") from None
        if done.returncode != 0:  # stderr can carry URLs and tracebacks; it is deliberately not returned
            raise KagUnavailable("kag_failed", "KAG exited with an error; check the gateway call cap and rate limit and the OpenSPG logs.")

    def retrieve(self, request, retriever):
        if retriever.domain != self.settings.domain:
            raise KagUnavailable("kag_domain_mismatch", f"The KAG project holds the '{self.settings.domain}' domain, not '{retriever.domain}'.")
        if not self.installed():
            raise KagUnavailable("kag_not_installed", "KAG is not installed or configured here (docs/setup.md).")
        if not self._lock.acquire(blocking=False):
            raise KagUnavailable("kag_busy", "Another KAG question is running. Try later.", 429)
        try:
            self._check_server()
            with tempfile.TemporaryDirectory(prefix="kag-") as directory:
                out_path = Path(directory) / "result.json"
                self._runner(request.query, out_path)
                try:
                    if not out_path.is_file() or out_path.stat().st_size > MAX_RESULT_BYTES:
                        raise ValueError("missing or oversized result")
                    result = json.loads(out_path.read_text())
                    if not isinstance(result, dict) or not isinstance(result.get("answer"), str):
                        raise ValueError("malformed result")
                except (OSError, ValueError):
                    raise KagUnavailable("kag_invalid_result", "KAG returned an unreadable result.") from None
        finally:
            self._lock.release()
        evidence = {e.id: e for e in retriever.evidence if e.review_status == "reviewed"}
        try:
            ranked = resolve_citations(result, evidence, retriever.sources)
        except CitationError as exc:
            raise KagUnavailable("kag_invalid_result", f"KAG result rejected: {exc}.") from None
        return {"mode": "kag", "backend": "kag", "embedding_usage": [], "query": request.query, "context": request.context,
                "corpus_hash": retriever.corpus_hash, "synthetic": True, "method": "kag-solver (OpenSPG v0.8 / KAG v0.8.0, local)",
                "results": [{"score": score, "evidence": e.model_dump(), "source": retriever.sources[e.source_id]}
                            for score, e in ranked[:request.k]],
                "kag_answer": result["answer"], "answer_reference_tags": answer_tags(result["answer"]),
                "attribution": "The retrieved set is resolved to canonical evidence IDs and verified against our passages. "
                               "Tags inside the answer text (chunk:N_M) are KAG-internal and not independently verified, so no per-sentence citation is claimed.",
                "limitations": "Synthetic teaching corpus; KAG scores are not probabilities or scientific confidence; the answer text is generated "
                               "by a model and was seen in a different language than the question. No scientific validation."}
