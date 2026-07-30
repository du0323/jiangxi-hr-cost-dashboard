from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Optional, Union

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.normalize import normalize_month_data


class MonthRepository:
    def list_months(self) -> list[str]:
        raise NotImplementedError

    def load_month(self, ym: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def save_month(self, ym: str, data: dict[str, Any]) -> None:
        raise NotImplementedError


class LocalMonthRepository(MonthRepository):
    def __init__(self, base_dir: Union[str, Path]):
        self.base_dir = Path(base_dir)

    def _file_path(self, ym: str) -> Path:
        return self.base_dir / f"{ym}.json"

    def list_months(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return sorted((path.stem for path in self.base_dir.glob("*.json")), reverse=True)

    def load_month(self, ym: str) -> Optional[dict[str, Any]]:
        file_path = self._file_path(ym)
        if not file_path.exists():
            return None
        return normalize_month_data(json.loads(file_path.read_text(encoding="utf-8")))

    def save_month(self, ym: str, data: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        normalized = normalize_month_data(data)
        self._file_path(ym).write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class GitHubMonthRepository(MonthRepository):
    def __init__(self, repo: str, branch: str, token: str, data_dir: str):
        self.repo = repo
        self.branch = branch
        self.token = token
        self.data_dir = data_dir.strip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _content_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{path}"

    def list_months(self) -> list[str]:
        response = self.session.get(self._content_url(self.data_dir), params={"ref": self.branch}, timeout=30)
        response.raise_for_status()
        items = response.json()
        months = [item["name"].removesuffix(".json") for item in items if item.get("name", "").endswith(".json")]
        return sorted(months, reverse=True)

    def load_month(self, ym: str) -> Optional[dict[str, Any]]:
        path = f"{self.data_dir}/{ym}.json"
        response = self.session.get(self._content_url(path), params={"ref": self.branch}, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"])
        return normalize_month_data(json.loads(content.decode("utf-8")))

    def save_month(self, ym: str, data: dict[str, Any]) -> None:
        path = f"{self.data_dir}/{ym}.json"
        sha = None
        existing = self.session.get(self._content_url(path), params={"ref": self.branch}, timeout=30)
        if existing.ok:
            sha = existing.json().get("sha")
        elif existing.status_code != 404:
            existing.raise_for_status()

        normalized = normalize_month_data(data)
        encoded = base64.b64encode(
            json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")
        body: dict[str, Any] = {
            "message": f"Update month data {ym}",
            "content": encoded,
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha
        response = self.session.put(self._content_url(path), json=body, timeout=30)
        response.raise_for_status()


def _secret_or_env(key: str, env_key: str, default: str = "") -> str:
    try:
        value = st.secrets.get(key, os.getenv(env_key, default))
    except StreamlitSecretNotFoundError:
        value = os.getenv(env_key, default)
    return str(value)



def get_repository() -> MonthRepository:
    storage_mode = _secret_or_env("storage_mode", "STORAGE_MODE", "local").lower()
    data_dir = _secret_or_env("data_dir", "DATA_DIR", "data")
    if storage_mode == "github":
        token = _secret_or_env("github_token", "GITHUB_TOKEN")
        repo = _secret_or_env("github_repo", "GITHUB_REPO")
        branch = _secret_or_env("github_branch", "GITHUB_BRANCH", "main")
        if not token or not repo:
            raise RuntimeError("GitHub storage mode requires github_token and github_repo.")
        return GitHubMonthRepository(repo=repo, branch=branch, token=token, data_dir=data_dir)
    return LocalMonthRepository(Path(__file__).resolve().parent.parent / data_dir)
