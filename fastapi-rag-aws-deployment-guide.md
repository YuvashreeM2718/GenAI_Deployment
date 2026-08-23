# Deploying a FastAPI RAG Application to AWS — Complete Guide

Migrating an existing FastAPI RAG project from local infrastructure (local PostgreSQL, Cohere embeddings, Qdrant, local disk storage) to fully cloud-native AWS services (RDS, S3, Bedrock Knowledge Base, Groq), then deploying it to ECS Fargate with a CI/CD pipeline via GitHub Actions.

This document assumes you already have a working FastAPI application with auth, document upload, and chat endpoints, currently running against local infrastructure — the goal here is purely the migration and deployment, not building the API itself. Written to be followed by anyone with such a project, not tied to any one codebase's exact file layout.

**One thing worth knowing up front:** the GitHub Actions section (Part J) fills in a piece that's genuinely easy to miss — a `task-definition.json` file the workflow needs but doesn't create for you. That gap is called out specifically in Part J rather than left for you to discover the hard way.

---

## Contents

- [Deploying a FastAPI RAG Application to AWS — Complete Guide](#deploying-a-fastapi-rag-application-to-aws--complete-guide)
  - [Contents](#contents)
  - [1. What's changing, and why](#1-whats-changing-and-why)
  - [2. Prerequisites](#2-prerequisites)
  - [Part A — Environment configuration](#part-a--environment-configuration)
  - [Part B — AWS RDS (PostgreSQL)](#part-b--aws-rds-postgresql)
  - [Part C — S3 bucket](#part-c--s3-bucket)
  - [Part D — Bedrock Knowledge Base](#part-d--bedrock-knowledge-base)
  - [Part E — IAM access keys](#part-e--iam-access-keys)
  - [Part F — Database migration](#part-f--database-migration)
  - [Part G — AWS client helper](#part-g--aws-client-helper)
  - [Part H — S3 upload logic](#part-h--s3-upload-logic)
  - [Part I — RAG logic with per-user filtering](#part-i--rag-logic-with-per-user-filtering)
  - [Part J — Update your routers](#part-j--update-your-routers)
  - [Part K — Local test](#part-k--local-test)
  - [Part L — Dockerfile](#part-l--dockerfile)
  - [Part M — Build, tag, push to ECR](#part-m--build-tag-push-to-ecr)
  - [Part N — ECS cluster, task, and service](#part-n--ecs-cluster-task-and-service)
  - [Troubleshooting](#troubleshooting)
  - [Part O — GitHub Actions CI/CD](#part-o--github-actions-cicd)
  - [Checklist](#checklist)

---

## 1. What's changing, and why

| Was (local) | Becomes (AWS) | Why |
|---|---|---|
| Local PostgreSQL | **RDS (PostgreSQL)** | Managed, durable, reachable from your deployed app |
| Cohere embeddings + Qdrant vector DB | **Bedrock Knowledge Base** (S3 data source + Titan embeddings) | One managed service replaces two — no embedding calls or vector DB to run yourself |
| Local disk storage for uploads | **S3 bucket** | Local disk doesn't exist once your app runs in a container on ECS |
| Your LLM provider | **Groq** | Free-tier API, kept separate from AWS — you can swap this for Bedrock's own models later with no other changes |

Everything downstream of "where documents and answers come from" changes; your auth flow, database schema for users, and general API shape stay the same.

## 2. Prerequisites

- An AWS account, IAM user (not root), and the AWS CLI configured.
- A Groq API key — [console.groq.com](https://console.groq.com).
- Docker installed locally.
- A GitHub repository for this project, on a branch you're comfortable deploying from.
- `pip install langchain-aws langchain-groq boto3` added to your existing dependencies.

---

## Part A — Environment configuration

New `.env` variables this migration needs:

```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=
S3_PREFIX=documents
KB_ID=
TOP_K=4
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
DATABASE_URL=
MAX_UPLOAD_MB=50
```

Leave the values blank for now — you'll fill each one in as you create the corresponding resource in the parts below. Your existing JWT/auth settings (`SECRET_KEY`, `ALGORITHM`, etc.) stay exactly as they are.

**Remove** anything specific to the infrastructure you're replacing: Qdrant URL/API key, Cohere API key/model, any reranker model config, local `DATA_DIR`/`UPLOAD_DIR`, and any embedding-repo or namespace settings tied to your old vector pipeline — none of it is used once Bedrock Knowledge Base is in place.

Update your settings/config module to match — a `pydantic-settings`-style config works well here:

```python
# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aws_region: str
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    s3_bucket: str
    s3_prefix: str = "documents"

    kb_id: str
    top_k: int = 4

    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"

    database_url: str
    max_upload_mb: int = 50

    # existing auth settings — unchanged
    secret_key: str
    algorithm: str = "HS256"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`aws_access_key_id`/`aws_secret_access_key` are deliberately optional — Part G explains why: you'll need them locally, but not once this runs inside AWS.

---

## Part B — AWS RDS (PostgreSQL)

RDS console → **Create database**.

- **Choose a database creation method: Standard create** (not "Easy create") — full control over the config rather than accepting AWS's defaults blindly.
- **Engine**: PostgreSQL, whatever recent engine version is offered by default.
- **Templates**: **Sandbox** — the current low-cost tier for this kind of testing/small deployment (a straight replacement for what used to be labeled "Free tier").
- **Availability**: **Single DB instance** — no standby replica, which is what keeps this cheap. Fine for this project; a real production system with uptime requirements would use Multi-AZ instead.
- **Settings**: give it a DB instance identifier (e.g. `rag-api-db`). Username: `postgres`. **Credentials management: self-managed** — set your own master password.

  **Password gotcha, confirmed the hard way in the class this document is based on:** RDS rejects master passwords containing `@` (and a few other special characters, like `/` and `"`). Use a password without them — this isn't a typo in the console, it's a real constraint.

- **Instance configuration**: `db.t4g.micro` — this is the instance class actually offered under the Sandbox template.
- **Storage**: 20 GB is the minimum and is fine to start. **Disable storage autoscaling** — no reason to risk surprise cost growth on a project at this stage.
- **Connectivity**:
  - **Don't connect to an EC2 compute resource** — you don't need this database bound to a specific EC2 instance.
  - VPC: default. Subnet group: default.
  - **Public access: Yes** — required if you want to reach this database from outside AWS (your local machine, for running migrations before everything is containerized). You can lock this down later.
  - **VPC security group**: choose an existing one you can edit (or create a new one) — you'll open port 5432 on it next.
- **Additional configuration**: leave the port at the default `5432` unless you have a specific reason to change it. Monitoring: **Standard**, 7-day retention (free tier).
- **Create database.**

**Open the port on the security group** — this step is easy to skip and the database will otherwise be completely unreachable:

EC2 console → **Security Groups** → select the one you attached to this RDS instance → **Edit inbound rules** → **Add rule**:
- Type: **Custom TCP**
- Port: **5432**
- Source: **My IP** (safer) or **Anywhere (0.0.0.0/0)** if you need broader access while testing — tighten this before this is anything resembling production.
- **Save rules.**

**Once the database is available**, get its endpoint from the RDS console (Connectivity & security tab) and build your `DATABASE_URL`:

```
postgresql+asyncpg://postgres:<your-password>@<rds-endpoint>:5432/postgres
```

Test the connection before moving on — a minimal script confirms this quickly:

```python
# db_connect_test.py
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host="<rds-endpoint>",
        port=5432,
        user="postgres",
        password="<your-password>",
        database="postgres",
    )
    print("Connection successful")
    await conn.close()

asyncio.run(main())
```

A wrong password fails fast and clearly here — confirm this works before assuming any later failure is something more complicated.

---

## Part C — S3 bucket

S3 console → **Create bucket**.
- Name it something globally unique (bucket names are unique across *all* of AWS, not just your account) — e.g. `<yourcompany>-rag-documents-<random-suffix>`.
- Leave the rest default (Block Public Access **on**).
- **Create bucket**, then create a folder inside it matching your `S3_PREFIX` (e.g. `documents`).

## Part D — Bedrock Knowledge Base

If you've built a Bedrock Knowledge Base before, this is the same process — S3 as the data source, Titan embeddings, S3 Vectors (or OpenSearch Serverless) as the vector store.

Bedrock console → **Knowledge Bases** → **Create** → **Knowledge base with vector store**.
- Data source: **Amazon S3**, browse to your bucket and the folder from Part C.
- **Parsing strategy**: the **default Bedrock parser** is the right choice for plain text-based PDFs — cheaper and sufficient unless your documents are image-heavy, in which case a foundation-model parser (e.g. Amazon Nova) does better at the cost of more spend per document.
- **Embeddings model**: **Titan Text Embeddings**.
- **Vector store**: **Quick create**, **S3 Vectors** — the lower-cost option for a project at this scale (see the earlier RAG guide in this conversation for the fuller cost comparison against OpenSearch Serverless, if you want it).
- Create, wait for provisioning, then note the **Knowledge Base ID** for your `.env`.

## Part E — IAM access keys

IAM console → **Users** → your user → **Security credentials** → **Access keys** → **Create access key** → **Command Line Interface (CLI)** → confirm → **Create**. Save the Access Key ID and Secret Access Key immediately — the secret is shown only once.

Put both into your `.env` for now — Part N revisits whether these belong in your deployed environment at all.

---

## Part F — Database migration

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install langchain-aws boto3
```

**Update your document model** to match what the new pipeline actually needs — drop columns tied to the old local-storage/vector pipeline, add one for the S3 location:

```python
# Before: id, user_id, file_name, path, page_number, status, ...
# After:
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String, nullable=False)
    s3_key = Column(String, nullable=False)
```

Generate and apply the migration:

```bash
alembic revision --autogenerate -m "replace local storage fields with s3_key"
alembic upgrade head
```

Confirm in a DB client (or the RDS console's query editor, if available) that the `documents` table now matches — old columns gone, `s3_key` present.

---

## Part G — AWS client helper

```python
# app/aws.py
import boto3
from app.config import get_settings

settings = get_settings()


def make_client(service_name: str):
    """
    Create a boto3 client. Locally, explicit keys from .env are used.
    Once this runs inside AWS (ECS with a task role attached), boto3
    finds credentials automatically via the role — no keys needed,
    and none should be present in that environment at all.
    """
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return boto3.client(
            service_name,
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    return boto3.client(service_name, region_name=settings.aws_region)
```

This one function is what lets the exact same code run locally (with explicit keys) and in ECS (via a task role, no keys at all) — see the security note in Part N about which of these you actually want in production.

## Part H — S3 upload logic

```python
# app/s3.py
import json
from app.aws import make_client
from app.config import get_settings

settings = get_settings()
s3_client = make_client("s3")


def build_key(user_id: int, file_name: str) -> str:
    return f"{settings.s3_prefix}/user{user_id}/{file_name}"


def upload_file(user_id: int, file_name: str, content: bytes, content_type: str) -> str:
    key = build_key(user_id, file_name)

    s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )

    # A .metadata.json sidecar file is how Bedrock Knowledge Base picks up
    # per-object metadata for filtering — this is what makes per-user
    # document isolation possible in Part I.
    metadata = {
        "metadataAttributes": {
            "user_id": {
                "value": {"type": "NUMBER", "numberValue": user_id},
                "includeForEmbedding": False,
            }
        }
    }
    s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=f"{key}.metadata.json",
        Body=json.dumps(metadata).encode(),
        ContentType="application/json",
    )

    return key
```

Every uploaded file gets tagged with the uploading user's ID via this metadata sidecar — this is the mechanism Part I's retriever filter relies on to make sure one user's questions only ever search their own documents, not everyone's.

## Part I — RAG logic with per-user filtering

```python
# app/rag.py
from langchain_aws.retrievers import AmazonKnowledgeBasesRetriever
from langchain_groq import ChatGroq

from app.aws import make_client
from app.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = (
    "Answer the question using only the provided context from the user's "
    "documents. If the answer is not available in the context, say you "
    "could not find it."
)


def get_retriever(user_id: int) -> AmazonKnowledgeBasesRetriever:
    return AmazonKnowledgeBasesRetriever(
        knowledge_base_id=settings.kb_id,
        client=make_client("bedrock-agent-runtime"),
        retrieval_config={
            "vectorSearchConfiguration": {
                "numberOfResults": settings.top_k,
                "filter": {"equals": {"key": "user_id", "value": user_id}},
            }
        },
    )


def get_llm() -> ChatGroq:
    return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key)


async def generate(query: str, user_id: int) -> str:
    retriever = get_retriever(user_id)
    docs = await retriever.ainvoke(query)

    if not docs:
        return "I could not find that in your documents."

    context = "\n\n".join(doc.page_content for doc in docs)

    llm = get_llm()
    response = await llm.ainvoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {query}\n\nContext: {context}"},
    ])

    return response.content
```

The `filter` in `retrieval_config` is doing the multi-tenant isolation — it restricts retrieval to only the chunks whose `.metadata.json` `user_id` matches the requesting user, so this one Knowledge Base safely serves every user without their documents ever mixing.

## Part J — Update your routers

**Upload endpoint** — strip out everything related to local storage and your old ingestion pipeline; the entire body becomes a size/type check plus one call:

```python
from app.s3 import upload_file

@router.post("/documents/upload")
async def upload_document(file: UploadFile, user=Depends(get_current_user), db=Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    settings = get_settings()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is larger than {settings.max_upload_mb}MB.",
        )

    existing = find_by_hash(db, content, user.id)  # keep your existing dedup logic if you have it
    if existing:
        return existing

    key = upload_file(user.id, file.filename, content, file.content_type)

    document = Document(user_id=user.id, file_name=file.filename, s3_key=key)
    db.add(document)
    db.commit()
    return {"id": document.id}
```

**Chat endpoint** — one call replaces whatever your old retrieval+generation logic was:

```python
from app.rag import generate

@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    answer = await generate(request.query, user.id)
    return {"answer": answer}
```

**After uploading, sync the Knowledge Base** — either manually (Bedrock console → your KB → Data source → **Sync**) or via an automatic S3-event-driven pipeline. Setting up true auto-sync (EventBridge → SQS → Lambda calling `StartIngestionJob`) is a substantial topic on its own — covered in depth in the RAG-specific guide earlier in this conversation, if you want that automation; this document assumes manual sync for now, which is a completely reasonable starting point.

---

## Part K — Local test

Run your app normally (`uvicorn app.main:app --reload`), and walk through the full flow once before touching Docker:
1. Register and log in.
2. Upload a PDF — confirm it lands in S3 under `documents/user<id>/`, with a matching `.metadata.json` sidecar.
3. Sync the Knowledge Base (manual click, per Part J).
4. Ask a question about that document's content and confirm you get a grounded answer.

Catching problems here, with a normal Python traceback in your terminal, is far faster than debugging the same issue once it's wrapped in a container running on ECS.

## Part L — Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations/ ./migrations/
COPY app/ ./app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Two things worth calling out: `--host 0.0.0.0` is required — `127.0.0.1` (the default) only accepts connections from inside the container itself, which makes the app unreachable from outside. And **never `COPY` your `.env` file into the image** — secrets baked into an image layer are effectively public to anyone who can pull it. Environment variables get supplied at container-run time instead (locally via `--env-file`, in ECS via the task definition in Part N).

Test the built image locally before pushing anywhere:

```bash
docker build -t rag-api .
docker run -p 8000:8000 --env-file .env rag-api
curl http://localhost:8000/health
```

## Part M — Build, tag, push to ECR

ECR console → **Create repository** (e.g. `rag-api`) → open it → **View push commands** — use the exact commands it generates for your account/region rather than retyping generic ones:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build -t rag-api .
docker tag rag-api:latest <account-id>.dkr.ecr.<region>.amazonaws.com/rag-api:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/rag-api:latest
```

## Part N — ECS cluster, task, and service

**Cluster.** ECS console → **Create cluster** → name it (e.g. `rag-api-cluster`) → infrastructure: **AWS Fargate** (serverless — no EC2 instances to manage).

**Task definition.** **Create new task definition**.
- Family: e.g. `rag-api-task`. Launch type: **AWS Fargate**.
- Container: name it (e.g. `rag-api-container`), image URI from Part M, container port **8000**.
- **Environment variables**: enter every value from your `.env` here — `AWS_REGION`, `S3_BUCKET`, `KB_ID`, `GROQ_API_KEY`, `DATABASE_URL`, etc.

  **Security note worth acting on, not just reading:** you *can* also put `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` here — it works, and is the simplest path to get running. But it's not the best practice, and Part G's `make_client()` was written specifically to make the better option free: attach an **ECS Task Role** (a separate IAM role, distinct from the task *execution* role) with permissions for S3, Bedrock, etc., and **omit both AWS key variables entirely**. `make_client()` then falls through to boto3's automatic credential discovery, which finds the task role with zero code changes and zero secrets sitting in your task definition. Worth doing before this handles anything resembling real user data.

- **Health check**: command `CMD-SHELL, curl -f http://localhost:8000/health || exit 1`, matching the Dockerfile.
- Create.

**Service.** From the cluster → **Create service** using the task definition above.
- Service name (e.g. `rag-api-service`).
- **Load balancing**: Application Load Balancer — container port 8000. Create a new ALB, a listener on port **80**, and a target group forwarding to port **8000** with health check path **`/health`**.
- Leave auto-scaling off for now.
- Create, and wait for the task to reach a running state.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| RDS rejects your password | Remove `@`, `/`, or `"` from it — RDS master passwords can't contain these |
| Can't connect to RDS from your machine | Security group isn't allowing your IP on port 5432 — see Part B |
| `docker run` works locally but ECS task shows unhealthy target, despite the container itself running fine and responding to direct `curl` | This exact situation came up in the class this document is based on and wasn't fully resolved live — worth checking, in order: (1) the ECS task's security group allows inbound traffic **from the ALB's security group** specifically on port 8000, not just "anywhere"; (2) the target group's health check grace period is long enough to cover your container's actual startup time (migrations running via `alembic upgrade head` before Uvicorn even starts can take longer than a short default grace period allows); (3) the health check path/port in the target group exactly matches what the container serves. If none of these resolve it, the next step is reading the actual ECS task logs in CloudWatch rather than inferring from the target group's summary status alone |
| GitHub Actions fails with "task definition file does not exist" | See Part O — this needs a `task-definition.json` file the default template doesn't create for you |
| App works locally, fails in the container with a missing package | A dependency got installed manually during a local session and never added to `requirements.txt` — diff your active virtual environment's installed packages against the file |

---

## Part O — GitHub Actions CI/CD

**This is the part that was left incomplete in the class this document is based on** — the workflow was configured, but failed with "task definition file does not exist" because that file was never created. Here's the complete version, gap filled in.

**Step 1 — Export your task definition as JSON.** You already built this task definition by hand in the ECS console (Part N) — rather than hand-writing a second copy, export the real one: ECS console → your task definition → the specific revision → **JSON** tab → copy its full contents into a new file at your repo root:

```
task-definition.json
```

**Step 2 — GitHub repository secrets.** Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret** — add:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

**Step 3 — The workflow file**, at `.github/workflows/aws.yml` (note the exact path — `workflows`, not a typo of it):

```yaml
name: Deploy to Amazon ECS

on:
  push:
    branches: [main]   # set this to whichever branch you deploy from

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: rag-api
  ECS_SERVICE: rag-api-service
  ECS_CLUSTER: rag-api-cluster
  ECS_TASK_DEFINITION: task-definition.json
  CONTAINER_NAME: rag-api-container

permissions:
  contents: read

jobs:
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push image to Amazon ECR
        id: build-image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          echo "image=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_OUTPUT

      - name: Fill in the new image ID in the Amazon ECS task definition
        id: task-def
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: ${{ env.ECS_TASK_DEFINITION }}
          container-name: ${{ env.CONTAINER_NAME }}
          image: ${{ steps.build-image.outputs.image }}

      - name: Deploy Amazon ECS task definition
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.task-def.outputs.task-definition }}
          service: ${{ env.ECS_SERVICE }}
          cluster: ${{ env.ECS_CLUSTER }}
          wait-for-service-stability: true
```

Two details worth understanding, not just copying: `amazon-ecs-render-task-definition` takes your exported `task-definition.json` and swaps in the freshly-built image URI — it doesn't deploy anything by itself, just produces an updated task definition. `amazon-ecs-deploy-task-definition` is the step that actually registers that updated definition and tells your ECS service to roll out to it, then (because of `wait-for-service-stability: true`) waits and reports failure if the new tasks never become healthy — which means a bad deploy shows up as a failed GitHub Actions run instead of a silently broken production service.

Commit `task-definition.json` and `.github/workflows/aws.yml`, push to the branch configured in the workflow's `on.push.branches`, and check the **Actions** tab for the run.

---

## Checklist

- [ ] RDS reachable from your local machine, migrations applied, `documents` table matches the new schema
- [ ] S3 bucket created, a test upload lands under the correct prefix with a matching `.metadata.json`
- [ ] Bedrock Knowledge Base created and synced at least once
- [ ] Local end-to-end test passes: upload → sync → ask a question → grounded answer
- [ ] Docker image builds, runs locally with `--env-file`, and passes its own health check
- [ ] Image pushed to ECR
- [ ] ECS cluster, task definition, and service created; task reaches a running, healthy state behind the ALB
- [ ] Considered (ideally adopted) an ECS Task Role instead of AWS keys as environment variables
- [ ] `task-definition.json` exported and committed
- [ ] GitHub secrets set, workflow file committed, a push triggers a successful automated deploy
