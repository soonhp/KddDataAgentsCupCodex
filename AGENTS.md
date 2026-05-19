# AGENTS.md — KDD Cup 2026 Data Agents 운영 지침

이 저장소에서 작업하는 모든 Codex agent는 아래 지침을 우선 적용한다.  
공식 규칙 원문: <https://dataagent.top/rules> (확인일: 2026-05-19). 공식 Rules와 이 문서가 충돌하면 공식 Rules 최신본이 우선한다.

## 1. 대회 목표

- 목표는 KDD Cup 2026 Data Agents 대회에서 복잡한 데이터 분석 task를 자율적으로 해결하는 offline data agent를 구현하는 것이다.
- 각 task는 `/input/task_<id>/task.json`과 `/input/task_<id>/context/`로 제공된다.
- agent는 CSV, JSON, SQLite DB, Markdown 문서, `knowledge.md`를 분석해 `/output/task_<id>/prediction.csv`를 생성해야 한다.

## 2. 반드시 지켜야 할 공식 규칙

- `/input`은 read-only로 취급하고 절대 쓰지 않는다.
- 각 `/input/task_<id>`에 대해 `/output/task_<id>/prediction.csv`를 생성한다.
- task 결과는 완료 즉시 progressive write한다.
- `/output`과 `/logs`만 writeable로 가정한다.
- 출력 CSV는 UTF-8 표준 CSV이며 header row를 포함한다.
- `/output` 아래 불필요한 중첩 directory를 만들지 않는다.
- 모델 설정은 `MODEL_API_URL`, `MODEL_API_KEY`, `MODEL_NAME` 환경변수에서 읽는다.
- 공식 평가 중 primary solver LLM은 Qwen3.5-35B-A3B만 사용한다.
- 외부 인터넷, 외부 LLM API, 내부 사설 서비스 호출에 의존하지 않는다.
- 모든 runtime dependency는 Docker image에 포함한다.
- `/logs/runtime.log` 등 crash/debug 가능한 로그를 남긴다. 단, API key 등 secret은 기록하지 않는다.
- Docker image는 `linux/amd64` 호환이어야 한다.
- 컨테이너는 추가 인자 없이 `docker run`으로 실행 가능해야 한다.
- archive는 `docker save`로 만들고 `docker export`를 사용하지 않는다.
- archive 크기는 10GB 이하로 유지한다.

## 3. 평가 방식 최적화 지침

- 채점은 column-level content matching 중심이다.
- 컬럼명과 행 순서는 무시된다.
- extra unmatched columns는 penalty를 받는다.
- 정답 컬럼 recall을 높이되, 불필요한 후보 컬럼 추가를 피한다.
- 숫자는 최소 소수점 2자리 이상 충분한 precision으로 출력한다.
- 날짜는 가능한 ISO `YYYY-MM-DD` 형식으로 출력한다.
- 문자열은 case-sensitive이므로 원본 표기와 공백을 보존한다.
- null은 빈 문자열로 출력한다.

## 4. 구현 우선순위

1. 공식 규칙 compliant runner 구현: `/input`, `/output`, `/logs`, env var model config.
2. scoring replica와 output linter 구현.
3. ContextProfiler 구현: file inventory, CSV/JSON schema, SQLite schema/statistics, Markdown chunk index.
4. Solver routing 구현: Easy/Python-first, Medium/SQL-first, Hard/Doc-RAG-first, Extreme/retrieval-first.
5. Verifier/repair loop 구현: SQL error, empty result, wrong shape, formatting 문제 자동 복구.
6. Dockerfile, amd64 build, offline smoke test 구현.
7. public demo regression suite와 failure taxonomy 유지.

## 5. 코드 작업 원칙

- public demo task에 hardcode하지 않는다.
- hidden test context 구조를 고정 가정하지 않는다.
- `context/` 내 파일 존재 여부를 매 task 동적으로 탐색한다.
- 대용량 CSV/JSON은 streaming, DuckDB, Polars lazy scan 등 메모리 안전한 방식을 우선한다.
- Markdown 장문은 전체 prompt 투입보다 chunking/retrieval/summary를 우선한다.
- 모든 변경에는 실행 방법과 검증 결과를 문서화한다.
- PR/merge 자동화는 사용자가 명시적으로 요청하기 전에는 수행하지 않는다.
