from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
import uuid
import os
import json
import hashlib
import logging
import time
import redis
from redis import ConnectionPool
from app.gateway import celery_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agentic.gateway")

class Settings:
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    API_KEY: str = os.getenv("API_KEY", "dev-key")
    ENV: str = os.getenv("ENV", "dev")
    MAX_QUEUE_LEN: int = int(os.getenv("MAX_QUEUE_LEN", "200"))
    IDEMPOTENCY_TTL: int = int(os.getenv("IDEMPOTENCY_TTL", "86400"))
    RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))

settings = Settings()

pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True, max_connections=50, socket_connect_timeout=2, socket_timeout=2, retry_on_timeout=True)
r = redis.Redis(connection_pool=pool)

BLOCKED_WORDS = frozenset(["bomba", "droguri", "arma", "ilegal", "cum sa omor", "exploziv", "cocaina", "kill", "bomb"])

class IngestRequest(BaseModel):
    prompt: Optional[str] = Field(None, min_length=1, max_length=10000)
    query: Optional[str] = Field(None, min_length=1, max_length=10000)
    payload: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_effective_prompt(self) -> str:
        if self.prompt:
            return self.prompt
        if self.query:
            return self.query
        if self.payload and isinstance(self.payload, dict) and "prompt" in self.payload:
            return str(self.payload["prompt"])
        return json.dumps(self.model_dump(), ensure_ascii=False)

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(10, ge=1, le=100)
    score_threshold: float = Field(0.85, ge=0.0, le=1.0)

app = FastAPI(
    title="Agentic Platform 15M",
    version="1.0.0",
    docs_url=None if settings.ENV == "prod" else "/docs",
    redoc_url=None if settings.ENV == "prod" else "/redoc",
    openapi_url=None if settings.ENV == "prod" else "/openapi.json"
)

@app.middleware("http")
async def add_security_headers_and_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Process-Time"] = str(time.time() - start)
    return response

def get_redis():
    try:
        r.ping()
        return r
    except redis.exceptions.ConnectionError as e:
        logger.error(f"redis_unavailable: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

def require_api_key(x_api_key: Optional[str] = Header(None), redis_client: redis.Redis = Depends(get_redis)):
    if settings.ENV != "prod":
        return True
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    if not hashlib.sha256(x_api_key.encode()).hexdigest() == hashlib.sha256(settings.API_KEY.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

def rate_limit(request: Request, redis_client: redis.Redis = Depends(get_redis)):
    if settings.ENV != "prod":
        return
    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:{client_ip}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 60)
        if count > settings.RATE_LIMIT_PER_MIN:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except redis.exceptions.RedisError:
        pass

def check_guardrail(prompt: str):
    if not prompt:
        return
    low = prompt.lower()
    for w in BLOCKED_WORDS:
        if w in low:
            logger.warning(f"guardrail_blocked: {w}")
            raise HTTPException(status_code=400, detail=f"Blocked: guardrail triggered - {w}")

def check_backpressure(redis_client: redis.Redis = Depends(get_redis)) -> int:
    try:
        qlen = redis_client.llen("celery")
        if qlen > settings.MAX_QUEUE_LEN:
            logger.warning(f"backpressure_active qlen={qlen}")
            raise HTTPException(status_code=429, detail=f"Queue full ({qlen}) - backpressure active")
        return qlen
    except redis.exceptions.ConnectionError:
        return 0

def get_idempotency_key(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).strip().lower()
    h = hashlib.sha256(raw.encode()).hexdigest()
    return f"idempotency:v2:{h}"

@app.get("/health")
def health(redis_client: redis.Redis = Depends(get_redis)):
    try:
        redis_client.ping()
        qlen = redis_client.llen("celery")
        return {"status": "ok", "env": settings.ENV, "queue_len": qlen, "version": "1.0.0"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(e)})

def create_job_internal(payload: Dict[str, Any], redis_client: redis.Redis) -> Dict[str, Any]:
    effective_prompt = payload.get("prompt") or payload.get("query") or str(payload)
    check_guardrail(effective_prompt)
    qlen = check_backpressure(redis_client)
    cache_key = get_idempotency_key(payload)
    existing = redis_client.get(cache_key)
    if existing:
        logger.info(f"idempotency_hit key={cache_key}")
        return json.loads(existing)
    job_id = str(uuid.uuid4())
    data = {"job_id": job_id, "payload": payload, "request_id": job_id, "created_at": int(time.time())}
    try:
        celery_app.send_task("app.worker.process_job", args=[data], queue="celery", retry=True)
    except Exception as e:
        logger.error(f"celery_enqueue_failed job_id={job_id} error={e}")
        raise HTTPException(status_code=503, detail="Worker queue unavailable")
    redis_client.set(f"job:{job_id}", json.dumps({"status": "queued", "job_id": job_id, "request_id": job_id}), ex=3600)
    response = {"job_id": job_id, "status": "queued", "queue_len": qlen, "request_id": job_id}
    redis_client.set(cache_key, json.dumps(response), ex=settings.IDEMPOTENCY_TTL)
    logger.info(f"job_created job_id={job_id} qlen={qlen}")
    return response

@app.post("/ingest", dependencies=[Depends(rate_limit)])
def ingest(payload: IngestRequest, auth: bool = Depends(require_api_key), redis_client: redis.Redis = Depends(get_redis)):
    return create_job_internal(payload.model_dump(), redis_client)

@app.post("/jobs", dependencies=[Depends(rate_limit)])
def create_jobs(payload: IngestRequest, auth: bool = Depends(require_api_key), redis_client: redis.Redis = Depends(get_redis)):
    return create_job_internal(payload.model_dump(), redis_client)

@app.post("/search", dependencies=[Depends(rate_limit)])
def search(payload: SearchRequest, auth: bool = Depends(require_api_key), redis_client: redis.Redis = Depends(get_redis)):
    check_guardrail(payload.query)
    check_backpressure(redis_client)
    cache_key = get_idempotency_key(payload.model_dump())
    existing = redis_client.get(cache_key)
    if existing:
        cached = json.loads(existing)
        return {"results": [], "query": payload.query, "score_threshold": payload.score_threshold, "cached": True, "request_id": cached.get("request_id")}
    return {"results": [], "query": payload.query, "score_threshold": payload.score_threshold, "top_k": payload.top_k, "request_id": str(uuid.uuid4())}

@app.get("/jobs/{job_id}")
def get_job(job_id: str, auth: bool = Depends(require_api_key), redis_client: redis.Redis = Depends(get_redis)):
    if not job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id")
    val = redis_client.get(f"job:{job_id}")
    if not val:
        return {"status": "not_found", "job_id": job_id}
    return json.loads(val)