# KDD Cup 2026 Data Agents 운영 규칙

Source of truth: <https://dataagent.top/rules> (확인일: 2026-05-19). 공식 Rules와 다른 문서가 충돌하면 Rules 최신본을 우선한다.

## 반드시 지켜야 할 규칙 (MUST)

- 컨테이너는 추가 인자 없이 `docker run`으로 실행되어야 하며 `/input/task_<id>` 전체를 순회한다.
- 각 task 결과는 `/output/task_<id>/prediction.csv`에 즉시 저장한다. 완료 task는 timeout/OOM이 나도 채점될 수 있으므로 progressive write를 기본으로 한다.
- `/input`은 read-only로 취급하고 절대 쓰지 않는다. `/output`, `/logs`만 쓴다.
- 출력 CSV는 UTF-8 표준 CSV이며 header row를 포함한다. `/output` 아래 불필요한 중첩 디렉터리를 만들지 않는다.
- 모델 설정은 평가 시스템이 주입하는 `MODEL_API_URL`, `MODEL_API_KEY`, `MODEL_NAME` 환경변수에서 읽는다.
- 공식 평가 중 primary solver LLM은 Qwen3.5-35B-A3B만 사용한다. 다른 LLM을 컨테이너 내부에서 primary reasoning/generation engine으로 실행하지 않는다.
- 외부 인터넷, 외부 LLM API, 내부 사설 서비스 호출에 의존하지 않는다. 모든 의존성은 Docker image에 포함한다.
- `/logs/runtime.log` 등 task별 crash/debug 로그를 남긴다. 단, 민감한 API key를 로그에 남기지 않는다.
- 평가 리소스 budget을 지킨다: 16 vCPU, 64GB RAM, GPU 없음, A-board 총 2시간, B-board 총 12시간.
- Docker image는 `linux/amd64` 호환이어야 한다.
- 이미지명은 `<team_id>:v<N>`, archive명은 `<team_id>_v<N>.tar.gz`를 따른다.
- archive는 `docker save`로 만들고 `docker export`를 사용하지 않는다.
- archive 크기는 10GB 이하로 유지한다.
- 제출은 등록된 팀 리더 이메일에서만 보낸다.
- Google Drive 공유 권한은 “Anyone with the link can view”로 설정하고 평가 완료 전 삭제/수정하지 않는다.
- 같은 Docker image/solution을 다른 팀과 공유하거나 다른 팀명으로 중복 제출하지 않는다.

## 권장 규칙 (SHOULD)

- 컬럼명/행순서는 채점에 영향이 없지만 디버깅을 위해 의미 있는 컬럼명을 사용한다.
- 불필요한 extra columns를 줄여 redundancy penalty를 피한다.
- 숫자는 최소 소수점 2자리 이상 충분한 precision으로 출력하고, 채점 정규화가 2자리 반올림임을 고려한다.
- 날짜는 ISO `YYYY-MM-DD`, datetime은 가능한 ISO 형식으로 출력한다.
- 문자열은 case-sensitive이므로 원본 표기와 공백을 보존한다.
- null은 빈 문자열로 출력한다.
- task별 `context/` 구조를 고정 가정하지 말고 `csv/`, `db/`, `json/`, `doc/`, `knowledge.md` 존재 여부를 동적으로 탐지한다.
- Hard/Extreme long-context 대응을 위해 retrieval, chunking, hierarchical summarization, memory 전략을 포함한다.
- 제출 전 로컬에서 `/input`, `/output`, `/logs` mount를 흉내 낸 end-to-end smoke test를 수행한다.
- 제출 버전, 실험 로그, run id, config hash, git commit, public demo score를 체계적으로 관리한다.

## 평가 최적화 메모

- 채점은 column content matching 중심이다. 컬럼명과 행 순서는 무시된다.
- `Recall = Matched Columns / Gold Columns`, extra unmatched columns는 penalty를 받는다.
- 따라서 정답 컬럼 누락을 줄이되, 무분별한 후보 컬럼 추가는 금지한다.
