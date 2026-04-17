from __future__ import annotations

import random

from locust import HttpUser, between, events, task


SEARCH_TERMS = ["data", "user", "admin", "report", "analytics"]
SQLI_TERMS = ["1' OR '1'='1", "UNION SELECT", "DROP TABLE users"]
VALID_USERS = [
    {"username": "admin", "password": "admin123"},
    {"username": "user1", "password": "password1"},
    {"username": "analyst", "password": "analyst99"},
]


class OperatorUser(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def health_check(self):
        self.client.get("/health", name="/health")

    @task(3)
    def get_data(self):
        page = random.randint(1, 3)
        self.client.get(f"/api/data?page={page}&per_page=10", name="/api/data")

    @task(3)
    def get_users(self):
        self.client.get("/api/users", name="/api/users")

    @task(2)
    def search_normal(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(f"/search?q={term}", name="/search")

    @task(1)
    def metrics(self):
        self.client.get("/metrics", name="/metrics")

    @task(1)
    def login_attempt(self):
        credentials = random.choice(VALID_USERS)
        self.client.post("/login", json=credentials, name="/login")

    @task(1)
    def upload_probe(self):
        payload = {"content": "x" * random.randint(128, 2048)}
        self.client.post("/api/upload", json=payload, name="/api/upload")

    @task(1)
    def suspicious_search(self):
        term = random.choice(SQLI_TERMS)
        self.client.get(f"/search?q={term}", name="/search_suspicious")

    @task(1)
    def investigation_flow(self):
        login = self.client.post("/login", json=VALID_USERS[0], name="/login_admin")
        if login.status_code == 200 and login.json().get("token"):
            token = login.json()["token"]
            self.client.get("/admin", headers={"Authorization": f"Bearer {token}"}, name="/admin")
            self.client.get("/search?q=admin", name="/search_admin")


class AnalystUser(HttpUser):
    wait_time = between(3, 6)
    weight = 1

    @task(2)
    def analyst_login(self):
        self.client.post("/login", json=VALID_USERS[2], name="/login_analyst")

    @task(1)
    def browse_data(self):
        self.client.get("/api/data?page=1&per_page=20", name="/api/data")


@events.quitting.add_listener
def on_locust_quit(environment, **kwargs):
    stats = environment.stats.total
    p99 = stats.get_response_time_percentile(0.99)

    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"  Total requests:     {stats.num_requests:,}")
    print(f"  Failures:           {stats.num_failures:,} ({100 * stats.fail_ratio:.1f}%)")
    print(f"  Requests/s:         {stats.current_rps:.1f}")
    print(f"  Median latency:     {stats.median_response_time:.0f}ms")
    print(f"  p95 latency:        {stats.get_response_time_percentile(0.95):.0f}ms")
    print(f"  p99 latency:        {p99:.0f}ms")
    print(f"  Max latency:        {stats.max_response_time:.0f}ms")
    print("=" * 60)

    if p99 < 100:
        print(f"  ✓ p99 < 100ms  (actual: {p99:.0f}ms)")
    else:
        print(f"  ✗ p99 >= 100ms (actual: {p99:.0f}ms) - FAILED")
