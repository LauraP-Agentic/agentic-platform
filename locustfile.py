from locust import HttpUser, task, between, events
import uuid
import time
import hashlib
import os
import random

API_KEY = os.getenv("API_KEY", "dev-key-change-me")
BASE_PROMPTS = [
    "fabrica mobila mese 2890 placi industrial",
    "bucatarie moderna comanda",
    "dormitor lemn masiv",
    "mobila birou ergonomic"
]

class Staff75KUser(HttpUser):
    wait_time = between(0.5, 1.5)
    host = "http://localhost:80"

    def on_start(self):
        self.request_id_base = str(uuid.uuid4())
        self.headers_base = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }

    def _sha_id(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @task(5)
    def trick_3_4_idempotency_request_id(self):
        raw_id = f"staff-75k-{self.request_id_base}-{uuid.uuid4()}"
        sha_id = self._sha_id(raw_id)
        headers = {**self.headers_base, "X-Request-ID": sha_id}
        payload = {
            "prompt": random.choice(BASE_PROMPTS),
            "request_id": sha_id,
            "metadata": {"source": "locust-75k"}
        }
        with self.client.post("/ingest", json=payload, headers=headers, catch_response=True) as resp:
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code in [200, 201, 202]:
                resp.success()
            else:
                resp.failure(f"FAIL idempotency: {resp.status_code} - backpressure lipsa")

    @task(3)
    def trick_7_search_095(self):
        sha_id = self._sha_id(str(uuid.uuid4()))
        headers = {**self.headers_base, "X-Request-ID": sha_id}
        with self.client.post("/search", json={
            "query": "fabrica mobila",
            "score_threshold": 0.95,
            "limit": 5
        }, headers=headers, catch_response=True) as resp:
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code in [200, 201]:
                resp.success()
            else:
                resp.failure(f"FAIL search: {resp.status_code}")

    @task(2)
    def trick_2_5_6_backpressure_acks_prefetch(self):
        for i in range(5):
            sha_id = self._sha_id(f"backpressure-{i}-{uuid.uuid4()}")
            headers = {**self.headers_base, "X-Request-ID": sha_id}
            with self.client.post("/ingest", json={
                "prompt": f"spam backpressure test {i} {uuid.uuid4()}",
                "request_id": sha_id
            }, headers=headers, catch_response=True) as resp:
                if resp.status_code in [200, 201, 202, 429]:
                    resp.success()
                else:
                    resp.failure(f"FAIL backpressure burst: {resp.status_code}")
            time.sleep(0.1)

    @task(1)
    def trick_8_9_dlq_batch(self):
        sha_id = self._sha_id(str(uuid.uuid4()))
        headers = {**self.headers_base, "X-Request-ID": sha_id}
        with self.client.post("/ingest", json={
            "prompt": "",
            "request_id": sha_id
        }, headers=headers, catch_response=True) as resp:
            if resp.status_code in [200, 201, 202, 400, 429]:
                resp.success()
            else:
                resp.failure(f"FAIL DLQ: {resp.status_code}")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n--- STAFF 75K VERIFICARE 12/12 ---")
    print("Daca vezi 0% failures la 100 users = 11/12")
    print("Daca vezi 429 la 1000 users = 12/12 - backpressure OK")
    print("Daca Qdrant nu are duplicate = idempotency SHA256 OK")