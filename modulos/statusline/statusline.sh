#!/bin/bash
input=$(cat)

RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

rgb() { printf "\033[38;2;%d;%d;%dm" "$1" "$2" "$3"; }

MODEL=$(echo "$input" | jq -r '.model.display_name // "unknown"')
CTX_PCT=$(echo "$input" | jq -r '(.context_window.used_percentage // 0) | floor')
COST=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
DURATION_MS=$(echo "$input" | jq -r '.cost.total_duration_ms // 0')
LINES_ADDED=$(echo "$input" | jq -r '.cost.total_lines_added // 0')
LINES_REMOVED=$(echo "$input" | jq -r '.cost.total_lines_removed // 0')
GIT_BRANCH=$(echo "$input" | jq -r '.workspace.git_branch // ""')
GIT_REPO=$(echo "$input" | jq -r '.workspace.git_repo_name // ""')

# Limites del plan. Ausentes hasta la primera respuesta de la API, y en planes sin suscripcion.
FIVE_PCT=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
FIVE_RESET=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
WEEK_PCT=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
WEEK_RESET=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

# Verde por debajo del 50%, ambar hasta el 80%, rojo a partir de ahi.
pct_color() {
  if [ "$1" -ge 80 ]; then rgb 255 85 85
  elif [ "$1" -ge 50 ]; then rgb 255 190 60
  else rgb 110 220 130
  fi
}

# Barra compacta de 8 caracteres para los limites del plan.
minibar() {
  local p=$1 w=8 i filled out
  filled=$(( p * w / 100 ))
  [ "$filled" -gt "$w" ] && filled=$w
  out="$(pct_color "$p")"
  for i in $(seq 0 $((w - 1))); do
    if [ "$i" -lt "$filled" ]; then out="${out}█"; else out="${out}${DIM}░"; fi
  done
  printf "%b" "${out}${RESET}"
}

# Tiempo que queda hasta que la ventana se reinicie.
fmt_left() {
  local diff h m
  diff=$(( $1 - $(date +%s) ))
  [ "$diff" -lt 0 ] && diff=0
  h=$(( diff / 3600 ))
  m=$(( (diff % 3600) / 60 ))
  if [ "$h" -ge 24 ]; then printf "%dd%dh" "$(( h / 24 ))" "$(( h % 24 ))"
  elif [ "$h" -gt 0 ]; then printf "%dh%02dm" "$h" "$m"
  else printf "%dm" "$m"
  fi
}

# Context emoji
if [ "$CTX_PCT" -ge 90 ]; then
  CTX_EMOJI="🚨"
elif [ "$CTX_PCT" -ge 70 ]; then
  CTX_EMOJI="🔥"
elif [ "$CTX_PCT" -ge 20 ]; then
  CTX_EMOJI="⚡"
else
  CTX_EMOJI="🟢"
fi

# RGB gradient bar (20 chars wide)
BAR_WIDTH=20
FILLED=$(( CTX_PCT * BAR_WIDTH / 100 ))
BAR=""
for i in $(seq 0 $((BAR_WIDTH - 1))); do
  ratio=$(( i * 100 / (BAR_WIDTH - 1) ))
  if [ $ratio -le 50 ]; then
    R=$(( ratio * 510 / 100 ))
    G=255
  else
    R=255
    G=$(( (100 - ratio) * 510 / 100 ))
  fi
  if [ $i -lt $FILLED ]; then
    BAR="${BAR}$(rgb $R $G 0)█"
  else
    BAR="${BAR}${DIM}░"
  fi
done
BAR="${BAR}${RESET}"

# Format cost
COST_FMT=$(printf "%.3f" "$COST")

# Format duration (skip zero units)
DURATION_S=$((DURATION_MS / 1000))
DAYS=$((DURATION_S / 86400))
HOURS=$(( (DURATION_S % 86400) / 3600 ))
MINUTES=$(( (DURATION_S % 3600) / 60 ))
SECONDS=$((DURATION_S % 60))
DURATION_FMT=""
[ $DAYS -gt 0 ]    && DURATION_FMT="${DAYS}d "
[ $HOURS -gt 0 ]   && DURATION_FMT="${DURATION_FMT}${HOURS}h "
[ $MINUTES -gt 0 ] && DURATION_FMT="${DURATION_FMT}${MINUTES}m "
DURATION_FMT="${DURATION_FMT}${SECONDS}s"

# Build output
OUT=""

# Repo + branch
if [ -n "$GIT_REPO" ]; then
  OUT="${OUT}$(rgb 255 215 0)${BOLD}${GIT_REPO}${RESET} "
fi
if [ -n "$GIT_BRANCH" ]; then
  OUT="${OUT}$(rgb 0 210 220)🌿 ${GIT_BRANCH}${RESET} · "
fi

# Context bar
OUT="${OUT}${CTX_EMOJI} ${BAR} ${DIM}${CTX_PCT}%${RESET} · "

# Cost
OUT="${OUT}$(rgb 255 215 0)\$${COST_FMT}${RESET}"

# Lines added/removed (only if non-zero)
if [ "$LINES_ADDED" -gt 0 ] || [ "$LINES_REMOVED" -gt 0 ]; then
  OUT="${OUT} · $(rgb 100 220 100)+${LINES_ADDED}${RESET} $(rgb 255 100 100)-${LINES_REMOVED}${RESET}"
fi

# Model
OUT="${OUT} · 🤖 $(rgb 200 120 220)${MODEL}${RESET}"

# Duration
OUT="${OUT} · ${DIM}${DURATION_FMT}${RESET}"

printf "%b" "$OUT"

# Segunda linea: consumo de la suscripcion. Se omite entera si la API no lo manda.
if [ -n "$FIVE_PCT" ] || [ -n "$WEEK_PCT" ]; then
  LIM=""
  if [ -n "$FIVE_PCT" ]; then
    F=$(printf "%.0f" "$FIVE_PCT")
    LIM="${LIM}⏳ ${DIM}5h${RESET} $(minibar "$F") $(pct_color "$F")${F}%${RESET}"
    [ -n "$FIVE_RESET" ] && LIM="${LIM} ${DIM}↻ $(fmt_left "$FIVE_RESET")${RESET}"
  fi
  if [ -n "$WEEK_PCT" ]; then
    W=$(printf "%.0f" "$WEEK_PCT")
    [ -n "$LIM" ] && LIM="${LIM} ${DIM}·${RESET} "
    LIM="${LIM}📅 ${DIM}7d${RESET} $(minibar "$W") $(pct_color "$W")${W}%${RESET}"
    [ -n "$WEEK_RESET" ] && LIM="${LIM} ${DIM}↻ $(fmt_left "$WEEK_RESET")${RESET}"
  fi
  printf "\n%b" "$LIM"
fi
