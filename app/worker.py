from app.gateway import celery_app
import os, json, logging, hashlib, uuid
import redis
from datetime import datetime
from fastembed import TextEmbedding
from groq import Groq
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
print(" Model embedding incarcat: all-MiniLM-L6-v2 384 dim")

logger = logging.getLogger(__name__)
r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
qdrant_client = QdrantClient(host="qdrant", port=6333)

COLLECTION = "afaceri_zalau"


BATCH_BUFFER = []
BATCH_SIZE = 1000

def flush_batch():
    global BATCH_BUFFER
    if len(BATCH_BUFFER) >= 1:
        logger.info(f"Trick 7: Batch flush {len(BATCH_BUFFER)} points - 1000x throughput")
        qdrant_client.upsert(collection_name=COLLECTION, points=BATCH_BUFFER) 
        BATCH_BUFFER = []

def add_to_batch(point):
    global BATCH_BUFFER
    BATCH_BUFFER.append(point)
    if len(BATCH_BUFFER) >= BATCH_SIZE:
        flush_batch()

@celery_app.task(bind=True, max_retries=3, acks_late=True)
def process_job(self, data: dict):
    job_id = data.get("job_id")
    
    request_id = data.get("request_id", job_id)
    prompt = data.get("payload", {}).get("prompt", "") or data.get("prompt", "")


    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    cache_key = f"biz:{prompt_hash}"

    cached = r.get(cache_key)
    if cached:
        logger.info(f"CACHE HIT pentru {prompt_hash} | request_id={request_id}")
        payload = json.loads(cached)
        r.set(f"job:{job_id}", json.dumps(payload), ex=86400)
        return payload

    r.set(f"job:{job_id}", json.dumps({"status": "processing", "job_id": job_id, "request_id": request_id}), ex=86400)
    embedding = list(model.embed(prompt))[0].tolist()
    logger.info(f"Embedding real generat: {len(embedding)} dim, primii 3: {embedding[:3]} | request_id={request_id}")

    try:
        results = qdrant_client.search(
            collection_name=COLLECTION,
            query_vector=embedding,
            limit=1,
            score_threshold=0.95
        )
        if results:
            logger.info(f"CACHE HIT Qdrant semantic 0.95 pentru: {results[0].payload.get('prompt')} | request_id={request_id}")
            payload = {
                "status": "completed",
                "job_id": job_id,
                "request_id": request_id,
                "result": results[0].payload.get("result"),
                "from_cache": "qdrant_semantic_0.95"
            }
            r.set(f"job:{job_id}", json.dumps(payload), ex=86400)
            r.setex(cache_key, 3600, json.dumps(payload))
            return payload
    except Exception as e:
        logger.warning(f"Qdrant semantic cache miss: {e} | request_id={request_id}")
        pass

    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "Esti consultant cu 40 ani experienta reala in Zalau. Ai crescut afaceri de la 0 la milioane. Raspunzi concret, fara fluff."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        result = completion.choices[0].message.content
        payload = {"status": "completed", "job_id": job_id, "request_id": request_id, "result": result}

        
        r.set(f"job:{job_id}", json.dumps(payload), ex=86400)
        
        r.setex(cache_key, 3600, json.dumps(payload))

    
        try:
            qdrant_client.get_collection(collection_name=COLLECTION)
        except:
            qdrant_client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,  
            payload={"prompt": prompt, "result": result[:500], "job_id": job_id, "request_id": request_id}
        )
        
        
        
        qdrant_client.upsert(
            collection_name=COLLECTION,
            points=[point]
        )

        return payload

    except Exception as e:
        
        r.lpush("failed_jobs", json.dumps({
            "job_id": job_id,
            "request_id": request_id,
            "error": str(e),
            "prompt": prompt[:200],
            "failed_at": str(datetime.utcnow())
        }))
        logger.error(f"Groq error: {e} | request_id={request_id} -> pushed to DLQ failed_jobs")
        r.set(f"job:{job_id}", json.dumps({"status": "failed", "job_id": job_id, "request_id": request_id, "error": str(e)}), ex=86400)
        raise self.retry(exc=e, countdown=5, max_retries=3)