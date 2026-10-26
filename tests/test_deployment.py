"""Deployment contracts and privacy of request telemetry, using synthetic inputs."""
import asyncio
import json
from pathlib import Path
from xml.etree import ElementTree

import httpx


def test_static_hosting_artifact_and_api_boundary():
    config = json.loads(Path("firebase.json").read_text())
    hosting = config["hosting"]
    public = Path(hosting["public"])
    assert public == Path("frontend")
    assert hosting["rewrites"] == [{"source": "/api/**", "run": {
        "serviceId": "fundo-centenario", "region": "southamerica-east1", "pinTag": True}}]
    assert not any(public.rglob(".env*"))
    assert not any(public.rglob("*.jsonl"))
    urls = ElementTree.parse(public / "sitemap.xml").findall("{*}url/{*}loc")
    assert {url.text for url in urls} == {
        "https://fundocentenario.com.br/", "https://fundocentenario.com.br/como-apoiar/"}
    for path in (public / "index.html", public / "como-apoiar/index.html"):
        assert 'rel="canonical"' in path.read_text(encoding="utf-8")
    headers = {item["source"]: {header["key"]: header["value"] for header in item["headers"]}
               for item in hosting["headers"]}
    assert headers["/api/**"]["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["**"]["Content-Security-Policy"]
    # Unversioned JS/CSS/HTML must revalidate, otherwise rollback can keep stale code.
    assert headers["**"]["Cache-Control"] == "public, max-age=0, must-revalidate"


def test_request_logs_exclude_untrusted_values_and_errors_are_not_cached(tmp_path, monkeypatch):
    from backend.app import config
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    from backend.app import main
    events = []
    monkeypatch.setattr(main.request_logger, "info", lambda message: events.append(json.loads(message)))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
            response = await client.get("/api/not-a-route-sensitive?email=sensitive", headers={
                "X-Request-ID": "sensitive", "X-Donation-Token": "sensitive"})
            assert response.status_code == 404
            assert len(response.headers["X-Request-ID"]) == 32
            response = await client.post("/api/donations/intents", content=b"sensitive" * 5000)
            assert response.status_code == 413
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            await client.get("/api/health?token=sensitive")
    asyncio.run(check())
    assert len(events) == 3
    assert "sensitive" not in json.dumps(events)
    assert events[-1]["route"] == "/api/health"
    assert all(event["duration_ms"] >= 0 for event in events)
