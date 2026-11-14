[![CI](https://github.com/LauraP-Agentic/agentic-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/LauraP-Agentic/agentic-platform/actions)
# Agentic AI Platform - Prototype

> **Prototype of an innovative agentic AI platform | Python & LLMs | Scalable architecture designed for high-concurrency (principles for 15M+ scale) | Educational / Portfolio Project**


This is a portfolio prototype demonstrating how to design, build, and test a scalable agentic AI platform using modern Python stack. Built as an educational project to showcase engineering skills relevant for large-scale AI systems.

### ⚠️ Disclaimer - Transparency & Legal Safety
This repository is a **portfolio / educational prototype**. It is **NOT** a production platform currently serving 15 million users. 
The architecture, testing methodology (Locust), and scalability patterns (Docker, async, gateway-worker) are **designed following principles used for platforms at 15M+ scale**. No claims of current production traffic, user data, or commercial operation are made.

### Architecture
`Client -> Gateway (FastAPI) -> Worker (async) -> Qdrant`

### What This Prototype Demonstrates (Mapped to AI Engineer Role)
This project was built to demonstrate practical skills for:
- **Develop and enhance an innovative agentic AI platform** -> Modular `app/` structure with gateway and worker components
- **Build AI-powered solutions using Python and LLMs** -> Python 3.11, FastAPI-ready structure, LLM integration point in `app/`
- **Principles for platforms serving 15M+ users** -> Dockerized, stateless services, horizontal scaling via `docker-compose.yml`, load testing strategy
- **Work with emerging AI technologies and tools** -> Docker, Locust, FastAPI, async patterns
- **Support ongoing development of scalable AI solutions** -> Clean `.gitignore`, reproducible builds, performance testing

### 🛠️ Tech Stack
- **Framework:** FastAPI (app structure)
- **Infra:** Docker & Docker Compose
- **Testing:** Locust - load testing for high-concurrency
- **Concepts:** Agentic AI, Gateway-Worker pattern, Backpressure handling, Scalability
- **LLM:** Groq API - llama-3.3-70b-versatile 
- **Cache**: Redis for rate limiting
- **Observability**: Prometheus + structlog

### 📁 Repository Structure
```
app/                  -> Core application (gateway / workers / agents)
Dockerfile            -> Production-ready container build
docker-compose.yml    -> Multi-service orchestration for local scalability
locustfile.py         -> Load test (designed for up to 75k concurrent users simulation)
requirements.txt      -> Python dependencies
.gitignore            -> Ensures clean repo (no cache, reports, env)
```

### 🚀 How to Run (Local)
```bash
# 1. Build and start
docker-compose up --build

# 2. Run load tests
pip install -r requirements.txt
locust -f locustfile.py
# Open http://localhost:8089
```

### 📈 Scalability & Load Testing
- Load testing script included (`locustfile.py`) to simulate high concurrency
- Stateless services designed for horizontal scaling
- Docker Compose demonstrates how to scale workers: `docker-compose up --scale worker=3`
- Architecture principles align with systems serving 15M+ users: decoupling, async processing, containerization

 ### Mapped to THRYVE Job - 15M Platform
- Agentic platform -> gateway/worker structure
- Python & LLMs -> Groq integration
- Scalable -> Docker, async, rate limiting

### Scalability: Prototype vs 15M Production
Covered: stateless, async, docker-compose scale worker=3, Locust
Roadmap to 15M: Kubernetes + HPA, Kafka for backpressure, Redis Cluster, Prometheus + Grafana

### 🎯 Purpose
This repo is part of my portfolio for **Artificial Intelligence Engineer** roles, focusing on building **scalable, production-minded agentic AI platforms**. It showcases code organization, DevOps awareness, and performance testing mindset.

### 👩‍💻 Author
Laura P. - Agentic AI Platform Prototype - 2026

### 📝 License & Rights
© 2026 Laura P. All Rights Reserved.
This is a portfolio / educational prototype. Code is shared for demonstration and recruitment purposes only. No permission is granted for commercial use, reproduction, or distribution without explicit written consent from the author.
