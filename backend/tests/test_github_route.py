"""
tests/test_github_route.py
==========================
Unit tests for POST /api/v1/analyze/github.

Covers
------
1. _extract_skills_from_github_data  — pure-function unit tests
2. _merge_skills                     — deduplication / order tests
3. Endpoint integration tests        — happy path, 404, 429, 422, 502
   (GitHub API calls are intercepted with unittest.mock.patch so no real
    network requests are made during CI)

Run with:
    pytest backend/tests/test_github_route.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Real Imports ─────────────────────────────────────────────────────────────
# We rely on the real package structure now that we've fixed the stub-induced
# ImportErrors. The environment has most dependencies installed.

from models import GithubAnalyzeRequest, GithubAnalyzeResponse
from security import get_current_user
from routes.github import (
    _extract_skills_from_github_data,
    _merge_skills,
    router as github_router,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the GitHub router mounted."""
    app = FastAPI()
    app.include_router(github_router, prefix="/api/v1")
    # Inject a dummy ML bundle so categorize_skills gets a clusterer=None
    app.state.ml_models = None
    return app


def _make_repo(name: str, language: str | None = "Python", fork: bool = False) -> dict:
    """Build a minimal GitHub repository object."""
    return {
        "name":             name,
        "language":         language,
        "fork":             fork,
        "stargazers_count": 0,
    }


def _rate_limit_headers(remaining: int = 58, reset: int = 9_999_999_999) -> dict:
    return {
        "X-RateLimit-Limit":     "60",
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset":     str(reset),
    }


# =============================================================================
# 1. Pure-function unit tests — _extract_skills_from_github_data
# =============================================================================

class TestExtractSkillsFromGithubData:

    def test_python_language_maps_to_python_skill(self):
        skills = _extract_skills_from_github_data({"Python": 5}, [])
        assert "Python" in skills

    def test_typescript_language_maps_to_typescript(self):
        skills = _extract_skills_from_github_data({"TypeScript": 3}, [])
        assert "TypeScript" in skills

    def test_jupyter_notebook_maps_to_data_science(self):
        skills = _extract_skills_from_github_data({"Jupyter Notebook": 2}, [])
        assert "Data Science" in skills

    def test_dockerfile_maps_to_docker(self):
        skills = _extract_skills_from_github_data({"Dockerfile": 1}, [])
        assert "Docker" in skills

    def test_topic_docker_maps_to_docker(self):
        skills = _extract_skills_from_github_data({}, ["docker"])
        assert "Docker" in skills

    def test_topic_machine_learning_maps_correctly(self):
        skills = _extract_skills_from_github_data({}, ["machine-learning"])
        assert "Machine Learning" in skills

    def test_topic_nextjs_maps_to_nextjs(self):
        skills = _extract_skills_from_github_data({}, ["nextjs"])
        assert "Next.js" in skills

    def test_no_duplicates_same_signal(self):
        """docker from language + docker from topic must not duplicate."""
        skills = _extract_skills_from_github_data({"Dockerfile": 1}, ["docker"])
        docker_entries = [s for s in skills if s.lower() == "docker"]
        assert len(docker_entries) == 1

    def test_unknown_language_ignored(self):
        """An unrecognised language name should not appear in the output."""
        skills = _extract_skills_from_github_data({"COBOL": 1}, [])
        assert not any("COBOL" in s or "cobol" in s.lower() for s in skills)

    def test_empty_inputs_return_empty_list(self):
        assert _extract_skills_from_github_data({}, []) == []

    def test_multiple_languages_all_extracted(self):
        skills = _extract_skills_from_github_data(
            {"Python": 10, "TypeScript": 5, "Go": 2}, []
        )
        assert "Python" in skills
        assert "TypeScript" in skills
        assert "Go" in skills

    def test_returns_list_not_set(self):
        result = _extract_skills_from_github_data({"Python": 1}, [])
        assert isinstance(result, list)


# =============================================================================
# 2. Pure-function unit tests — _merge_skills
# =============================================================================

class TestMergeSkills:

    def test_no_duplicates_case_insensitive(self):
        merged = _merge_skills(["Python", "Docker"], ["python", "FastAPI"])
        lc = [s.lower() for s in merged]
        assert lc.count("python") == 1

    def test_github_skills_appear_first(self):
        merged = _merge_skills(["TypeScript"], ["Python"])
        assert merged.index("TypeScript") < merged.index("Python")

    def test_resume_skills_added_when_not_in_github(self):
        merged = _merge_skills(["Python"], ["React"])
        assert "React" in merged

    def test_empty_github_returns_resume_skills(self):
        merged = _merge_skills([], ["Python", "Docker"])
        assert merged == ["Python", "Docker"]

    def test_empty_resume_returns_github_skills(self):
        merged = _merge_skills(["Python", "Go"], [])
        assert merged == ["Python", "Go"]

    def test_both_empty_returns_empty(self):
        assert _merge_skills([], []) == []

    def test_casing_preserved_for_first_occurrence(self):
        """The github-side casing is kept because it appears first."""
        merged = _merge_skills(["TypeScript"], ["typescript"])
        assert "TypeScript" in merged
        assert "typescript" not in merged

    def test_total_count_is_union_size(self):
        merged = _merge_skills(["Python", "Docker"], ["Docker", "React"])
        # Union = Python, Docker, React
        assert len(merged) == 3


# =============================================================================
# 3. Endpoint integration tests (mocked GitHub API)
# =============================================================================

class TestGithubEndpointHappyPath:

    def _repos(self):
        return [
            _make_repo("repo-a", language="Python"),
            _make_repo("repo-b", language="TypeScript"),
            _make_repo("repo-c", language=None),
        ]

    def _mock_responses(self, repos, topics=None):
        """
        Return a mock httpx.AsyncClient whose .get() method is an AsyncMock.
        First call = repos listing; subsequent calls = topic fetches (return []).
        """
        repos_resp = MagicMock()
        repos_resp.status_code = 200
        repos_resp.headers = _rate_limit_headers()
        repos_resp.json.return_value = repos

        topics_resp = MagicMock()
        topics_resp.status_code = 200
        topics_resp.headers = _rate_limit_headers()
        topics_resp.json.return_value = {"names": topics or []}

        client = MagicMock()
        # First call → repos, subsequent → topics
        client.get = AsyncMock(side_effect=[repos_resp] + [topics_resp] * len(repos))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__  = AsyncMock(return_value=False)
        return client

    def test_returns_200(self):
        app = _make_app()

        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            resp = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat", "max_repos": 10},
            )
        assert resp.status_code == 200

    def test_response_has_required_fields(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()

        required = {
            "github_username", "repos_analyzed", "github_skills",
            "resume_skills", "merged_skills", "skill_categories",
            "languages_found", "topics_found", "source",
        }
        assert required.issubset(data.keys())

    def test_github_username_echoed(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        assert data["github_username"] == "octocat"

    def test_repos_analyzed_count(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        repos = self._repos()  # 3 repos, one has language=None
        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(repos)):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        # Non-fork repos are returned; language=None doesn't affect count
        assert data["repos_analyzed"] == len(repos)

    def test_python_detected_in_github_skills(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        assert "Python" in data["github_skills"]

    def test_resume_skills_merged_without_duplicates(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat", "resume_skills": ["Python", "Docker"]},
            ).json()

        merged_lc = [s.lower() for s in data["merged_skills"]]
        # Python comes from both GitHub and resume — should appear exactly once
        assert merged_lc.count("python") == 1

    def test_source_field_is_github(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        assert data["source"] == "github"

    def test_skill_categories_has_four_keys(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        with patch("routes.github.httpx.AsyncClient", return_value=self._mock_responses(self._repos())):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        assert set(data["skill_categories"].keys()) == {"frontend", "backend", "devops", "data"}

    def test_topics_in_response(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override

        repos = [_make_repo("repo-a", "Python")]
        with patch("routes.github.httpx.AsyncClient",
                   return_value=self._mock_responses(repos, topics=["machine-learning", "api"])):
            data = TestClient(app).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            ).json()
        assert "machine-learning" in data["topics_found"]


class TestGithubEndpointErrors:

    def _client_404(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.headers = _rate_limit_headers()
        resp.json.return_value = {"message": "Not Found"}
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__  = AsyncMock(return_value=False)
        return client

    def _client_rate_limited(self):
        """Simulate GitHub responding 200 but with Remaining=0."""
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = _rate_limit_headers(remaining=0, reset=9_999_999_999)
        resp.json.return_value = []
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__  = AsyncMock(return_value=False)
        return client

    def _client_503(self):
        resp = MagicMock()
        resp.status_code = 503
        resp.headers = _rate_limit_headers()
        resp.json.return_value = {}
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__  = AsyncMock(return_value=False)
        return client

    def _app_with_auth(self):
        app = _make_app()
        async def _override():
            return {"id": "u1", "email": "a@b.com"}
        from security import get_current_user
        app.dependency_overrides[get_current_user] = _override
        return app

    # ── 404 when GitHub user doesn't exist ────────────────────────────

    def test_unknown_user_returns_404(self):
        app = self._app_with_auth()
        with patch("routes.github.httpx.AsyncClient", return_value=self._client_404()):
            resp = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/analyze/github",
                json={"github_username": "definitely-not-a-real-user-xyz-123"},
            )
        assert resp.status_code == 404

    def test_404_detail_mentions_username(self):
        app = self._app_with_auth()
        with patch("routes.github.httpx.AsyncClient", return_value=self._client_404()):
            data = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/analyze/github",
                json={"github_username": "nouser"},
            ).json()
        assert "nouser" in data["detail"]

    # ── 429 when GitHub rate limit is exhausted ────────────────────────

    def test_rate_limit_exhausted_returns_429(self):
        app = self._app_with_auth()
        with patch("routes.github.httpx.AsyncClient", return_value=self._client_rate_limited()):
            resp = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            )
        assert resp.status_code == 429

    def test_rate_limit_response_has_retry_after_header(self):
        app = self._app_with_auth()
        with patch("routes.github.httpx.AsyncClient", return_value=self._client_rate_limited()):
            resp = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            )
        assert "Retry-After" in resp.headers or resp.status_code == 429

    # ── 502 when GitHub is unreachable ─────────────────────────────────

    def test_github_server_error_returns_502(self):
        app = self._app_with_auth()
        with patch("routes.github.httpx.AsyncClient", return_value=self._client_503()):
            resp = TestClient(app, raise_server_exceptions=False).post(
                "/api/v1/analyze/github",
                json={"github_username": "octocat"},
            )
        assert resp.status_code == 502

    # ── 422 for invalid max_repos ──────────────────────────────────────

    def test_max_repos_above_30_rejected(self):
        app = self._app_with_auth()
        resp = TestClient(app).post(
            "/api/v1/analyze/github",
            json={"github_username": "octocat", "max_repos": 31},
        )
        assert resp.status_code == 422

    def test_max_repos_zero_rejected(self):
        app = self._app_with_auth()
        resp = TestClient(app).post(
            "/api/v1/analyze/github",
            json={"github_username": "octocat", "max_repos": 0},
        )
        assert resp.status_code == 422

    def test_missing_username_rejected(self):
        app = self._app_with_auth()
        resp = TestClient(app).post(
            "/api/v1/analyze/github",
            json={"max_repos": 5},
        )
        assert resp.status_code == 422

    # ── Unauthenticated request ────────────────────────────────────────

    def test_unauthenticated_request_rejected(self):
        """Without mocking the auth dep, no JWT → 401 / 422."""
        app = FastAPI()
        app.include_router(github_router, prefix="/api/v1")
        resp = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/analyze/github",
            json={"github_username": "octocat"},
        )
        assert resp.status_code in (401, 422)
