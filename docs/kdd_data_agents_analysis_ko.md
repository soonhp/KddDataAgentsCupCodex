# KDD Cup 2026 Data Agents 대회 분석 및 최고 성과 실행 계획

작성일: 2026-05-19  
대상: <https://dataagent.top/>, <https://dataagent.top/rules>, <https://github.com/HKUSTDial/kddcup2026-data-agents-starter-kit>

## 1. 대회 목표와 문제 정의

KDD Cup 2026 Data Agents는 자연어 데이터 분석 질문을 받고, task별 `context/`에 제공된 CSV, JSON, SQLite DB, Markdown 문서, knowledge guide를 탐색해 최종 `prediction.csv`를 생성하는 자율 데이터 에이전트 대회다.

핵심 역량은 다음이다.

1. 파일/스키마/문서 자동 탐색
2. 질문 의도와 출력 shape 추론
3. SQL/Python/문서 검색 도구 사용
4. 계산·조인·필터링·집계 수행
5. 결과 정규화 및 검증
6. 제한된 오프라인 Docker 환경에서 안정 실행

## 2. 공식 규칙 핵심

- 제출물은 Docker image archive만 허용된다.
- 평가 컨테이너는 `/input` read-only, `/output`과 `/logs` writeable 환경에서 실행된다.
- 컨테이너는 `/input/task_<id>`를 순회해 `/output/task_<id>/prediction.csv`를 생성해야 한다.
- 외부 인터넷은 차단된다.
- 모델 호출은 평가 시스템이 주입하는 `MODEL_API_URL`, `MODEL_API_KEY`, `MODEL_NAME`을 사용해야 한다.
- 공식 평가 primary solver LLM은 Qwen3.5-35B-A3B로 제한된다.
- 평가 리소스는 16 vCPU, 64GB RAM, GPU 없음이며 A-board 2시간, B-board 12시간 total runtime budget을 고려해야 한다.
- Docker image는 `linux/amd64` 호환, archive 10GB 이하, `docker save`로 생성해야 한다.

로컬에는 Codex 기준으로 다음 파일에 규칙을 반영했다.

- `AGENTS.md`
- `.codex/KDD_DATA_AGENTS_RULES.md`

## 3. 평가 방식과 최적화 포인트

공식 metric은 column-level content matching이다.

- 컬럼명 무시
- 행 순서 무시
- 각 컬럼 값을 정렬한 signature로 gold와 비교
- `Recall = Matched Columns / Gold Columns`
- extra unmatched columns는 penalty
- 숫자는 2자리 반올림 정규화, 문자열은 case-sensitive

따라서 전략은 명확하다.

- 정답 컬럼 누락을 최우선으로 줄인다.
- 하지만 불필요한 extra column은 penalty를 유발하므로 answer shape classifier로 출력 컬럼 수를 제한한다.
- 숫자, 날짜, 문자열 formatting postprocessor를 반드시 둔다.
- 컬럼명은 점수에는 영향이 없지만 trace/debug를 위해 의미 있게 유지한다.

## 4. Starter-kit 실행 결과와 인사이트

공식 starter-kit를 `/tmp/kddcup2026-data-agents-starter-kit`에 clone하여 확인했다.

### 구조

- `src/data_agent_baseline/agents/`: ReAct loop, prompt, OpenAI-compatible model adapter
- `src/data_agent_baseline/tools/`: context 파일 탐색, CSV/JSON/doc preview, SQLite read-only SQL, Python execution, answer tool
- `src/data_agent_baseline/benchmark/`: public dataset loader
- `src/data_agent_baseline/run/runner.py`: task/benchmark 실행, artifact 저장
- `configs/react_baseline.example.yaml`: dataset/model/run 설정

### 실행 확인

- `uv`가 없어 `python3 -m pip install --user uv`로 설치했다.
- `uv sync` 성공.
- demo dataset 없이 `status` 실행 시 dataset missing 확인.
- Google Drive demo dataset을 다운로드하여 `data/public` symlink 후 `status`/`inspect-task` 성공.
- public demo task 수: 50개
  - easy 15
  - medium 23
  - hard 11
  - extreme 1
- API key가 없는 상태로 `run-task task_11`을 실행하면 OpenAI-compatible 호출에서 401로 실패하며 prediction은 생성되지 않는다. 즉 실제 평가 환경에서는 env var 기반 config/adapter 변경이 필수다.

### Starter-kit 한계

- 모델 설정을 YAML의 `agent.api_key/api_base/model`에서 읽는다. 공식 규칙에 맞게 환경변수 우선 로딩으로 바꿔야 한다.
- output이 `artifacts/runs/...` 중심이다. 공식 제출용 wrapper는 `/input -> /output` contract를 직접 만족해야 한다.
- ReAct prompt와 도구가 최소형이다. schema profiling, doc retrieval, verification, scoring replica가 없다.
- Python execution은 강력하지만 sandbox/timeout/메모리 guard와 출력 postprocess가 부족하다.
- long-context Hard/Extreme에는 단순 `read_doc` preview만으로 부족하다.

## 5. Demo 데이터셋 분석

다운로드한 Phase 1 demo package는 압축 458MB, 해제 후 약 1.7GB였다.

### 전체 분포

| 항목 | 값 |
|---|---:|
| task 수 | 50 |
| easy | 15 |
| medium | 23 |
| hard | 11 |
| extreme | 1 |
| Markdown 파일 | 64 |
| CSV 파일 | 40 |
| JSON 파일 | 37 |
| DB 파일 | 27 |
| gold 1컬럼 task | 40 |
| gold 2컬럼 task | 7 |
| gold 3컬럼 task | 3 |

대부분은 1컬럼 scalar/list 답이며, 일부가 2~3컬럼 table이다. 출력 shape 추론 정확도가 점수에 크게 영향을 준다.

### 대표 task 관찰

- `task_11` easy: JSON Patient/Examination + knowledge. thrombosis severity 조건을 조인해 ID/SEX/Diagnosis 3컬럼 출력.
- `task_38` easy: 61MB CSV/JSON. 특정 client의 cash withdrawal transaction id 140개 출력. 대용량 structured scan 필요.
- `task_250` medium: 402MB context. posts JSON, postHistory CSV, users DB. 특정 user display name과 answer count 기준 max post id 탐색.
- `task_330` hard: 279MB Match CSV + League.md. League 문서에서 “Belgium Jupiler League” registry code를 찾아 Match CSV 필터링.
- `task_418` extreme: Patient/Laboratory 장문 doc만 제공. creatinine abnormal 조건과 나이 계산을 문서에서 추출해야 함.
- `task_420` hard: cards DB + legalities.md. DB와 문서 semantic을 결합해 commander/legal/content warning percentage 계산.

### 인사이트

1. 공개 demo는 “LLM만으로 읽기”보다 deterministic parsing이 매우 중요하다.
2. `knowledge.md`는 스키마/컬럼 의미를 제공하므로 모든 task의 첫 번째 근거로 사용해야 한다.
3. Medium의 대용량 DB/JSON/CSV는 SQL/Pandas/Polars 기반으로 처리해야 한다.
4. Hard/Extreme은 문서에 registry code, field mapping, 예외 조건이 숨어 있어 retrieval이 필수다.
5. gold 대부분이 1컬럼이므로 extra column penalty를 피하는 column pruning이 중요하다.

## 6. 최고 성과를 위한 권장 아키텍처

```text
CompetitionRunner
 ├─ RuleCompliantIO
 │   ├─ /input scan
 │   ├─ /output/task_<id>/prediction.csv progressive write
 │   └─ /logs/runtime.log
 ├─ ContextProfiler
 │   ├─ file inventory
 │   ├─ CSV/JSON schema, row count, samples, candidate keys
 │   ├─ SQLite schema, row count, indexes, samples
 │   └─ Markdown headings, entity/keyword/chunk index
 ├─ Planner
 │   ├─ difficulty-aware routing
 │   ├─ answer shape prediction
 │   └─ source selection
 ├─ Solver Policies
 │   ├─ Python-first solver
 │   ├─ SQL-first solver
 │   ├─ Doc/RAG-first solver
 │   └─ fallback direct solver
 ├─ Verifier/Repair
 │   ├─ SQL/Python execution validation
 │   ├─ semantic condition checklist
 │   ├─ independent recomputation where possible
 │   └─ output linter
 └─ Postprocessor
     ├─ numeric/date/string normalization
     ├─ null handling
     └─ metric-aware column pruning
```

## 7. 난이도별 접근법

### Easy

- LLM 호출 전 CSV/JSON schema와 sample을 deterministic하게 수집한다.
- pandas/polars code 생성 후 실행한다.
- 단순 filter/count/list 문제는 template solver로 LLM 의존도를 낮춘다.

### Medium

- SQLite가 있으면 SQL-first로 시작한다.
- DB/CSV/JSON 간 join key 후보를 profiler가 찾는다.
- SQL 실패 시 schema + error + sample rows로 repair loop를 1~2회 수행한다.
- 대용량 파일은 pandas보다 DuckDB/Polars lazy scan을 우선한다.

### Hard

- knowledge guide와 doc headings를 먼저 검색한다.
- 문서에서 league id, status mapping, abnormal threshold, entity alias 등 semantic bridge를 추출한다.
- 추출된 bridge를 structured query에 넣어 계산한다.
- 문서 전체를 prompt에 넣지 말고 chunk retrieval을 사용한다.

### Extreme

- 전체 문서 독해를 금지한다.
- entity/field keyword 기반 검색 → 후보 chunk → structured extraction → 계산 순서로 처리한다.
- 장문 markdown이 사실상 table narrative인 경우 regex/LLM extraction hybrid를 사용한다.

## 8. 구현 우선순위

1. 공식 규칙 compliant runner: `/input`, `/output`, `/logs`, env var model config, Dockerfile.
2. scoring replica와 output linter: public gold로 로컬 점수 계산.
3. ContextProfiler: 모든 파일 타입에 대한 schema/statistics/sample/chunk index.
4. SQL/Python deterministic execution 강화: DuckDB/Polars/SQLite, 대용량 처리.
5. Planner + solver policy routing: Easy/Python, Medium/SQL, Hard/Doc-RAG.
6. Verifier/repair loop: empty result, SQL error, wrong shape, formatting 문제 자동 복구.
7. 실험 대시보드: difficulty별 score, failure category, runtime, token/tool usage.
8. Docker amd64 smoke test와 offline dependency 검증.

## 9. 데이터 사이언티스트 팀 운영 계획

가상의 기업 참가팀은 다음 squad로 구성한다.

### Agent Platform Lead

- ReAct/tool loop, runner, timeout, logging, Docker compliance 담당
- `/input -> /output` contract와 progressive write 보장

### Data/SQL Lead

- CSV/JSON/SQLite profiler
- Text-to-SQL prompt, SQL repair, join-key discovery
- 대용량 structured processing 최적화

### Retrieval/Document Lead

- Markdown chunking, heading/entity index, BM25/embedding retrieval
- Hard/Extreme 문서 조건 추출
- long-context memory 전략

### Evaluation Lead

- scoring replica, output linter, regression suite
- public demo failure taxonomy
- submission checklist와 versioning

### Reviewer/Release Captain

- rules compliance review
- Docker build/save 검증
- PR review/merge 승인
- 최종 제출 운영

## 10. 에이전트 간 협업/PR 운영안

Slack 소통은 요구사항에서 제외한다. 자율 agent 팀은 GitHub issue/branch/PR 중심으로 운영한다.

1. GitHub issue/branch 단위로 작업을 쪼갠다.
2. 각 agent는 독립 branch에서 구현하고 public demo subset으로 검증한다.
3. PR에는 다음을 반드시 포함한다.
   - 변경 목적
   - 관련 규칙 영향
   - 실행 명령
   - public demo score/runtime 변화
   - 실패 task 변화
4. merge 조건
   - lint/test 통과
   - output contract smoke test 통과
   - public demo regression 없음 또는 명확한 trade-off 승인
   - reviewer 1명 이상 승인

현재 세션에서는 사용자의 GitHub 쓰기 권한과 팀 repository branch 정책을 확인하지 않았으므로 실제 PR 생성, 리뷰 요청, merge는 수행하지 않았다. 다음 단계에서 원하면 GitHub workflow로 issue/PR 템플릿과 review checklist를 구성할 수 있다.

## 11. 다음 액션 체크리스트

- [ ] starter-kit 코드를 이 repo에 vendor/import하거나 submodule로 연결
- [ ] env var 기반 config loader 구현
- [ ] 공식 runner entrypoint 구현
- [ ] Dockerfile 및 amd64 build script 작성
- [ ] demo dataset 기반 scoring replica 구현
- [ ] ContextProfiler v1 구현
- [ ] output linter/postprocessor 구현
- [ ] public demo baseline score 측정
- [ ] failure taxonomy 문서화
- [ ] GitHub issue/PR 템플릿과 review checklist 구성

## 12. 결론

최고 성과의 핵심은 “LLM에게 모든 것을 맡기지 않는 것”이다. LLM은 계획, SQL/코드 생성, 애매한 문서 의미 해석에 집중시키고, 파일 탐색·스키마 추출·계산 실행·결과 정규화·검증은 deterministic 시스템으로 감싸야 한다. 공개 demo 분석상 Medium/Hard가 성능 차이를 만들 가능성이 높으므로, SQL-first structured solver와 doc retrieval bridge를 우선 개발하는 것이 가장 ROI가 높다.
