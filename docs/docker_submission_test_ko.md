# Docker 제출 이미지 빌드/테스트 결과

작성일: 2026-05-19

## 생성된 제출 구성

- `Dockerfile`
- `.dockerignore`
- `src/data_agent_baseline/submission.py`
- `scripts/build_submission_image.sh`
- `scripts/save_submission_image.sh`
- `README.md`의 Competition Docker Submission 섹션

## 이미지 빌드

```bash
TEAM_ID=kdddataagents VERSION=v1 ./scripts/build_submission_image.sh
```

결과:

- 이미지명: `kdddataagents:v1`
- platform: `linux/amd64`
- entrypoint: `dabench-submit`
- image size: 약 `251 MB`

## Smoke test: `/input -> /output` contract

Public demo input 전체 50개 task를 mount하여 smoke mode로 실행했다.

```bash
docker run --rm --platform linux/amd64 \
  -e DABENCH_SMOKE_MODE=1 \
  -e DABENCH_MAX_WORKERS=4 \
  -v /tmp/kdd_dataset/extracted/public/input:/input:ro \
  -v /tmp/dabench_docker_output_all:/output \
  -v /tmp/dabench_docker_logs_all:/logs \
  kdddataagents:v1
```

결과:

- `prediction.csv` 생성 개수: 50
- `/logs/summary.json` 기준 `task_count`: 50
- `/logs/summary.json` 기준 `succeeded_task_count`: 50
- `smoke_mode`: true

주의: smoke mode는 모델 호출 없이 header-only fallback prediction을 생성해 제출 IO contract만 검증한다. 점수 검증용이 아니다.

## Model env integration test

Host에서 OpenAI-compatible stub server를 띄우고 컨테이너가 공식 env var를 읽어 모델 호출을 수행하는지 검증했다.

```bash
docker run --rm --platform linux/amd64 \
  --add-host host.docker.internal:host-gateway \
  -e MODEL_API_URL=http://host.docker.internal:18080/v1 \
  -e MODEL_API_KEY=stub-key \
  -e MODEL_NAME=stub-model \
  -e DABENCH_TASK_LIMIT=1 \
  -e DABENCH_MAX_WORKERS=1 \
  -v /tmp/kdd_dataset/extracted/public/input:/input:ro \
  -v /tmp/dabench_docker_model_output:/output \
  -v /tmp/dabench_docker_model_logs:/logs \
  kdddataagents:v1
```

결과:

- `model_env_ready`: true
- `smoke_mode`: false
- `succeeded_task_count`: 1 / 1
- 생성 prediction:

```csv
stub
ok
```

## Archive 생성

```bash
TEAM_ID=kdddataagents VERSION=v1 ./scripts/save_submission_image.sh
```

결과:

- archive: `kdddataagents_v1.tar.gz`
- 크기: 약 `238 MB`
- 생성 방식: `docker save | gzip`
- `gzip -t kdddataagents_v1.tar.gz`: OK

## 제출 전 남은 주의사항

- `TEAM_ID`는 실제 대회 team id로 바꿔야 한다.
- 현재 solver는 starter-kit ReAct baseline이며, 성능용 profiler/retrieval/verifier는 아직 구현되지 않았다.
- 공식 평가에서는 `MODEL_API_URL`, `MODEL_API_KEY`, `MODEL_NAME`이 주입되어야 한다.
- `DABENCH_SMOKE_MODE=1`은 제출 이미지 검증용이며 실제 제출 실행에서는 사용하지 않는다.

## HF Inference Providers 연결 테스트 결과

전용 GPU/vLLM endpoint가 없으므로 1차 대안으로 Hugging Face router를 확인했다.

실행 스크립트:

```bash
python scripts/test_hf_provider_qwen.py --model Qwen/Qwen3.5-35B-A3B
```

현재 로컬에는 Hugging Face 로그인 토큰은 있었지만, Inference Providers 호출 권한이 없어 다음 오류가 발생했다.

```text
status 403
This authentication method does not have sufficient permissions to call Inference Providers on behalf of user soonhpx
```

조치:

1. Hugging Face token settings에서 `Make calls to Inference Providers` 권한이 있는 fine-grained token을 생성한다.
2. 아래처럼 환경변수로 설정한다.

```bash
export HF_TOKEN=hf_...
python scripts/test_hf_provider_qwen.py --model Qwen/Qwen3.5-35B-A3B
```

성공하면 제출 Docker를 아래처럼 public demo subset에 대해 실행한다.

```bash
docker run --rm --platform linux/amd64 \
  -e MODEL_API_URL=https://router.huggingface.co/v1 \
  -e MODEL_API_KEY=$HF_TOKEN \
  -e MODEL_NAME=Qwen/Qwen3.5-35B-A3B \
  -e DABENCH_TASK_LIMIT=3 \
  -v /tmp/kdd_dataset/extracted/public/input:/input:ro \
  -v /tmp/dabench_hf_output:/output \
  -v /tmp/dabench_hf_logs:/logs \
  kdddataagents:v1
```

## 2026-05-19 HF Qwen 실제 연결 재시도

권한 있는 `HF_TOKEN` 주입 후 `Qwen/Qwen3.5-35B-A3B`에 대한 단순 router 호출은 성공했다.

```bash
python3 scripts/test_hf_provider_qwen.py --model Qwen/Qwen3.5-35B-A3B
```

결과 요약:

- HTTP 200
- returned model: `qwen/qwen3.5-35b-a3b`
- assistant content: `{"ok":true}`

이후 동일 endpoint를 제출 Docker에 연결해 public demo `task_11` 1개를 실행했다.

```bash
docker run --rm --platform linux/amd64 \
  -e MODEL_API_URL=https://router.huggingface.co/v1 \
  -e MODEL_API_KEY=$HF_TOKEN \
  -e MODEL_NAME=Qwen/Qwen3.5-35B-A3B \
  -e DABENCH_TASK_LIMIT=1 \
  -e DABENCH_MAX_WORKERS=1 \
  -e DABENCH_AGENT_MAX_STEPS=8 \
  -e DABENCH_TASK_TIMEOUT_SECONDS=900 \
  -e DABENCH_GOLD_DIR=/gold \
  -v /tmp/kdd_dataset/extracted/public/input:/input:ro \
  -v /tmp/kdd_dataset/extracted/public/output:/gold:ro \
  -v /tmp/dabench_hf_qwen_task1_output:/output \
  -v /tmp/dabench_hf_qwen_task1_logs:/logs \
  kdddataagents:v1
```

결과:

- 첫 2회의 chat completions request는 HTTP 200
- 세 번째 request에서 HTTP 402 발생
- 오류: monthly included credits depleted
- task result: failed, fallback `prediction.csv` 생성
- local score: 0.0

추가 과금 호출을 막기 위해 이후 Qwen task 실행은 중단했다.

개선 반영:

- model call exception을 ReAct loop 내부에서 기록하도록 개선: model/API 실패도 `trace.json`에 step으로 남김

예시:

```bash
-e ```

다음 Qwen 테스트를 계속하려면 HF Inference Providers prepaid credits 또는 Pro/Team credits가 필요하다.
