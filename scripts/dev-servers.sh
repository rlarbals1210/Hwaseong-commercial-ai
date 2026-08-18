#!/bin/bash
# 개발 서버(FastAPI 8000 / Vite 5174) 일괄 기동·종료 스크립트.
# Automator Quick Action(단축키 Cmd+Shift+D / Cmd+Opt+Shift+D)에서 호출된다.
# GUI에서 실행될 때는 로그인 셸 환경변수가 없으므로 PATH·nvm을 여기서 직접 세팅한다.

set -uo pipefail
export LANG=en_US.UTF-8

PROJECT_DIR="/Users/gimgyumin/Developer/화성시-AI공모전/hwaseong-commercial-ai"
LOG_DIR="$PROJECT_DIR/.dev"
BACKEND_PORT=8000
FRONTEND_PORT=5174

BACKEND_PATTERN="uvicorn backend.main:app"
FRONTEND_PATTERN="$PROJECT_DIR/frontend"

notify() {
  /usr/bin/osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1
}

# 자식 프로세스부터 역순으로 종료. uvicorn --reload와 npm run dev는
# 각각 reloader/vite 자식을 두기 때문에 부모만 죽이면 포트가 안 풀린다.
kill_tree() {
  local pid=$1
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null
}

pids_on_port() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null
}

# 자기 자신과 조상 프로세스 목록. 단축키(Automator)로 실행되면 호출 셸의
# argv에 프로젝트 경로가 들어가 pgrep -f 패턴에 자기 자신이 걸리므로 제외한다.
SELF_PIDS=""
build_self_pids() {
  local pid=$$
  while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
    SELF_PIDS="$SELF_PIDS $pid"
    pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  done
}
build_self_pids

is_self() {
  case " $SELF_PIDS " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

stop_servers() {
  local found=0 pid

  for pid in $(pgrep -f "$BACKEND_PATTERN" 2>/dev/null); do
    is_self "$pid" && continue
    kill_tree "$pid"; found=1
  done

  # vite/npm은 명령어 문자열이 제각각이라 프로젝트 경로로 매칭한다.
  for pid in $(pgrep -f "$FRONTEND_PATTERN" 2>/dev/null); do
    is_self "$pid" && continue
    kill_tree "$pid"; found=1
  done

  # 위 패턴에서 새는 프로세스 대비: 실제 리스닝 중인 PID를 포트로 직접 회수
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(pids_on_port "$port"); do
      is_self "$pid" && continue
      kill_tree "$pid"; found=1
    done
  done

  local waited=0
  while [ "$waited" -lt 10 ]; do
    [ -z "$(pids_on_port "$BACKEND_PORT")$(pids_on_port "$FRONTEND_PORT")" ] && break
    sleep 0.5
    waited=$((waited + 1))
  done

  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(pids_on_port "$port"); do
      kill -KILL "$pid" 2>/dev/null
    done
  done

  rm -f "$LOG_DIR/backend.pid" "$LOG_DIR/frontend.pid"

  if [ "$found" = 1 ]; then
    notify "개발 서버 종료" "FastAPI(:$BACKEND_PORT) · Vite(:$FRONTEND_PORT) 내렸습니다"
  else
    notify "개발 서버 종료" "실행 중인 서버가 없었습니다"
  fi
}

start_servers() {
  mkdir -p "$LOG_DIR"

  # 중복 기동 방지: 이미 떠 있으면 먼저 정리하고 새로 띄운다
  if [ -n "$(pids_on_port "$BACKEND_PORT")$(pids_on_port "$FRONTEND_PORT")" ]; then
    stop_servers
  fi

  cd "$PROJECT_DIR" || { notify "개발 서버 기동 실패" "프로젝트 경로를 찾을 수 없습니다"; exit 1; }

  if [ ! -x "$PROJECT_DIR/.venv/bin/uvicorn" ]; then
    notify "개발 서버 기동 실패" ".venv/bin/uvicorn 없음 (pip install -r requirements.txt)"
    exit 1
  fi

  nohup "$PROJECT_DIR/.venv/bin/uvicorn" backend.main:app --reload --port "$BACKEND_PORT" \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$LOG_DIR/backend.pid"

  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1

  if ! command -v npm >/dev/null 2>&1; then
    notify "개발 서버 기동 실패" "npm을 찾을 수 없습니다 (nvm 로드 실패)"
    exit 1
  fi

  cd "$PROJECT_DIR/frontend" || exit 1
  nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$LOG_DIR/frontend.pid"

  # 포트가 실제로 열렸는지 확인 후 알림 (기동 실패를 조용히 넘기지 않기 위함)
  local waited=0 backend_up="" frontend_up=""
  while [ "$waited" -lt 40 ]; do
    backend_up=$(pids_on_port "$BACKEND_PORT")
    frontend_up=$(pids_on_port "$FRONTEND_PORT")
    [ -n "$backend_up" ] && [ -n "$frontend_up" ] && break
    sleep 0.5
    waited=$((waited + 1))
  done

  if [ -n "$backend_up" ] && [ -n "$frontend_up" ]; then
    notify "개발 서버 기동 완료" "API :$BACKEND_PORT · 웹 http://localhost:$FRONTEND_PORT"
  else
    local failed=""
    [ -z "$backend_up" ] && failed="backend"
    [ -z "$frontend_up" ] && failed="${failed:+$failed, }frontend"
    notify "개발 서버 일부 실패" "$failed 미기동 — .dev/*.log 확인"
  fi
}

status_servers() {
  local b f
  b=$(pids_on_port "$BACKEND_PORT"); f=$(pids_on_port "$FRONTEND_PORT")
  echo "backend  :$BACKEND_PORT  ${b:-(중지됨)}"
  echo "frontend :$FRONTEND_PORT ${f:-(중지됨)}"
}

case "${1:-start}" in
  start)  start_servers ;;
  stop)   stop_servers ;;
  status) status_servers ;;
  *) echo "usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
