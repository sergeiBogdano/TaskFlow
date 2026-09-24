from datetime import datetime, timedelta, timezone

import pytest

from app.web.api import ai_analytics as analytics
pytestmark = pytest.mark.skip(reason="AI analytics tests temporarily disabled")

@pytest.fixture
def llm_calls(monkeypatch):
    calls = []

    def fake(model, prompt, num_predict=600):
        calls.append({"model": model, "prompt": prompt})
        return f"[{model}] Анализ готов."

    monkeypatch.setattr(analytics, "_ollama_text", fake)
    return calls


@pytest.fixture(scope="module")
def seed_ai_data(admin_cookies, executor_cookies, event_loop):
    from sqlalchemy import select

    from app.core.database import async_session
    from app.core.models import Client, Task, User

    async def go():
        async with async_session() as session:
            admin = (await session.execute(select(User).where(User.username == "4dmin"))).scalar_one()
            executor = (await session.execute(select(User).where(User.username == "testexec"))).scalar_one()
            client = Client(
                org_name="AI Test Client",
                status="active",
                contract_start=datetime(2026, 1, 1),
                contract_end=datetime(2027, 12, 31),
            )
            session.add(client)
            await session.flush()
            now = datetime.now(timezone.utc)
            session.add_all([
                Task(title="AI overdue exec", status="todo", priority="high",
                     client_id=client.id, assignee_id=executor.id,
                     deadline=now - timedelta(days=20)),
                Task(title="AI overdue admin", status="in_progress", priority="medium",
                     client_id=client.id, assignee_id=admin.id,
                     deadline=now - timedelta(days=5)),
                Task(title="AI active future", status="todo", priority="low",
                     client_id=client.id, assignee_id=executor.id,
                     deadline=now + timedelta(days=10)),
                Task(title="AI done task", status="done", priority="medium",
                     client_id=client.id, assignee_id=executor.id,
                     deadline=now - timedelta(days=2),
                     completion_date=now - timedelta(hours=2)),
            ])
            await session.commit()
            return {"client_id": client.id, "executor_id": executor.id, "admin_id": admin.id}

    return event_loop.run_until_complete(go())


class TestAnalyticsOverdue:

    def test_overdue_facts_and_analysis(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/overdue", json={}, cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert data["facts"]["total"] >= 2
        assert "Анализ готов" in data["analysis"]
        assert data["model"] == "qwen2.5:3b"
        assert any(row["name"] == "testexec" for row in data["facts"]["by_assignee"])
        assert any(row["name"] == "AI Test Client" for row in data["facts"]["by_client"])
        assert data["facts"]["buckets"]["over_14"] >= 1

    def test_overdue_forbidden_for_executor(self, sync_request, executor_cookies, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/overdue", json={}, cookies=executor_cookies)
        assert resp.status_code == 403
        assert llm_calls == []

    def test_overdue_unauth(self, sync_request):
        assert sync_request("POST", "/api/ai/analytics/overdue", json={}, cookies={}).status_code == 401

    def test_overdue_llm_down_returns_facts(self, sync_request, admin_cookies, seed_ai_data, monkeypatch):
        def boom(model, prompt, num_predict=600):
            raise ConnectionError("no ollama")

        monkeypatch.setattr(analytics, "_ollama_text", boom)
        resp = sync_request("POST", "/api/ai/analytics/overdue", json={}, cookies=admin_cookies)
        assert resp.status_code == 503
        assert "facts" in resp.json()
        assert resp.json()["facts"]["total"] >= 2


class TestAnalyticsWorkloadDaily:

    def test_workload(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/workload", json={}, cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        row = next(r for r in data["facts"]["users"] if r["username"] == "testexec")
        assert row["active"] >= 2
        assert row["overdue"] >= 1
        assert "Анализ готов" in data["analysis"]

    def test_daily(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/daily", json={}, cookies=admin_cookies)
        assert resp.status_code == 200
        facts = resp.json()["facts"]
        assert facts["closed"] >= 1
        assert facts["overdue_total"] >= 2
        assert "created" in facts and "new_clients" in facts


class TestAnalyticsProject:

    def test_project_ok(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/analytics/project",
            json={"client_id": seed_ai_data["client_id"]}, cookies=admin_cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["facts"]["client"] == "AI Test Client"
        assert data["facts"]["overdue_count"] >= 2
        assert data["facts"]["max_lag_days"] >= 20
        assert "Анализ готов" in data["analysis"]

    def test_project_404(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/project", json={"client_id": 999999}, cookies=admin_cookies)
        assert resp.status_code == 404
        assert llm_calls == []


class TestAnalyticsBottlenecks:

    def test_bottlenecks(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request("POST", "/api/ai/analytics/bottlenecks", json={}, cookies=admin_cookies)
        assert resp.status_code == 200
        facts = resp.json()["facts"]
        assert facts["total_active"] >= 3
        assert abs(sum(item["share"] for item in facts["distribution"]) - 100.0) < 0.2
        assert "Анализ готов" in resp.json()["analysis"]


class TestTaskDescription:

    def test_description_ok(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/task-description",
            json={"title": "Подготовить аудит сайта", "client": "AI Test Client"},
            cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert "Анализ готов" in resp.json()["description"]

    def test_description_empty_title(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request("POST", "/api/ai/task-description", json={"title": "  "}, cookies=admin_cookies)
        assert resp.status_code == 400
        assert llm_calls == []


class TestSeoReport:

    def test_seo_report_ok(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/seo-report",
            json={
                "traffic": "вырос на 10%",
                "positions": [
                    {"key": "аудит сайта", "was": 5.0, "now": 2.0},
                    {"key": "продвижение", "was": 3.0, "now": 8.0},
                ],
            },
            cookies=admin_cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Анализ готов" in data["report"]
        deltas = {p["key"]: p["delta"] for p in data["facts"]["positions"]}
        assert deltas["аудит сайта"] == -3.0
        assert deltas["продвижение"] == 5.0

    def test_seo_report_empty(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request("POST", "/api/ai/seo-report", json={}, cookies=admin_cookies)
        assert resp.status_code == 400
        assert llm_calls == []


class TestAiChat:

    def test_chat_my_overdue(self, sync_request, executor_cookies, seed_ai_data, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/chat",
            json={"message": "Сколько у меня просроченных задач?"},
            cookies=executor_cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "my_overdue"
        assert data["facts"]["count"] >= 1
        assert "Анализ готов" in data["answer"]

    def test_chat_totals(self, sync_request, admin_cookies, seed_ai_data, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/chat", json={"message": "Сколько всего задач?"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["intent"] == "totals"
        assert resp.json()["facts"]["total"] >= resp.json()["facts"]["active"]

    def test_chat_help_without_llm(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request(
            "POST", "/api/ai/chat", json={"message": "привет, как дела?"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["intent"] == "help"
        assert llm_calls == []

    def test_chat_empty(self, sync_request, admin_cookies, llm_calls):
        resp = sync_request("POST", "/api/ai/chat", json={"message": "  "}, cookies=admin_cookies)
        assert resp.status_code == 400
        assert llm_calls == []

    def test_chat_unauth(self, sync_request):
        assert sync_request("POST", "/api/ai/chat", json={"message": "привет"}, cookies={}).status_code == 401
