#!/bin/bash
# Indicador de limites: vigila cuanto queda de la suscripcion.
#
# Lee por stdin el JSON que Claude Code pasa a la linea de estado y escribe una
# linea con un ojo y las dos ventanas del plan. No hace red ni lee credenciales:
# todo sale del campo rate_limits que ya viene en el stdin.
#
# Se usa como widget "custom-command" de ccstatusline (commandPath +
# preserveColors), o suelto como statusLine.command.
#
# RENDIMIENTO: arrancar un proceso en Windows cuesta 50-150 ms, asi que esto usa
# UN solo proceso externo (jq) y ni un fork mas: sin seq, sin date, sin $(...).
# Una version con varios jq y subshells en los bucles se come facilmente los 3 s
# de timeout de ccstatusline y la linea sale como [Timeout].

IFS= read -r -d '' input

# Un unico jq para los cuatro valores.
read -r F5 R5 W7 R7 <<< "$(jq -r '[(.rate_limits.five_hour.used_percentage // "-" | if type=="number" then (.|round) else . end),
                                   (.rate_limits.five_hour.resets_at // "-"),
                                   (.rate_limits.seven_day.used_percentage // "-" | if type=="number" then (.|round) else . end),
                                   (.rate_limits.seven_day.resets_at // "-")] | @tsv' <<< "$input")"

# 49m devuelve el fondo al del terminal. Hace falta porque en modo powerline
# ccstatusline pinta un fondo de color detras de esta linea, y el semaforo del
# indicador (verde/ambar/rojo) sobre un azul claro no se lee. La linea 1 son
# bloques de color; esta linea es su propia cosa, sobre el fondo de siempre.
NOBG=$'\033[49m'
RESET=$'\033[0m'
DIM=$'\033[2m'
GREEN=$'\033[38;2;110;220;130m'
AMBER=$'\033[38;2;255;190;60m'
RED=$'\033[38;2;255;85;85m'

# Asigna a C el color del semaforo. Sin subshell, a proposito.
set_color() {
  if   [ "$1" -ge 80 ]; then C=$RED
  elif [ "$1" -ge 50 ]; then C=$AMBER
  else                       C=$GREEN
  fi
}

# Deja en BAR una barra de 8 caracteres. Un porcentaje distinto de cero siempre
# pinta al menos un bloque: una barra vacia miente.
make_bar() {
  local p=$1 filled i
  filled=$(( p * 8 / 100 ))
  [ "$filled" -gt 8 ] && filled=8
  [ "$filled" -eq 0 ] && [ "$p" -gt 0 ] && filled=1
  BAR=""
  i=0
  while [ "$i" -lt 8 ]; do
    if [ "$i" -lt "$filled" ]; then BAR="${BAR}█"; else BAR="${BAR}${DIM}░"; fi
    i=$(( i + 1 ))
  done
}

# Deja en LEFT "1h23m @ 14:20". El countdown orienta; la hora absoluta sigue
# siendo cierta cuando la linea lleva media hora sin redibujarse. printf %()T es
# un builtin de bash: no cuesta un proceso como date.
make_reset() {
  local target=$1 fmt=$2 diff h m
  diff=$(( target - EPOCHSECONDS ))
  [ "$diff" -lt 0 ] && diff=0
  h=$(( diff / 3600 )); m=$(( (diff % 3600) / 60 ))
  if   [ "$h" -ge 24 ]; then printf -v LEFT "%dd%dh" "$(( h / 24 ))" "$(( h % 24 ))"
  elif [ "$h" -gt 0 ];  then printf -v LEFT "%dh%02dm" "$h" "$m"
  else                       printf -v LEFT "%dm" "$m"
  fi
  printf -v AT "%($fmt)T" "$target"
  LEFT="${LEFT} @ ${AT}"
}

# El indicador vigila la peor de las dos ventanas.
WORST=""
[ "$F5" != "-" ] && WORST=$F5
[ "$W7" != "-" ] && { [ -z "$WORST" ] || [ "$W7" -gt "$WORST" ]; } && WORST=$W7

if [ -z "$WORST" ]; then
  OUT="${DIM}( - )${RESET}"
else
  set_color "$WORST"
  if   [ "$WORST" -ge 100 ]; then G="x"
  elif [ "$WORST" -ge 80 ];  then G="!"
  elif [ "$WORST" -ge 50 ];  then G="O"
  else                            G="o"
  fi
  OUT="${C}( ${G} )${RESET}"
fi

if [ "$F5" != "-" ]; then
  set_color "$F5"; make_bar "$F5"
  OUT="${OUT}  ${DIM}5h${RESET} ${C}${BAR}${RESET} ${C}${F5}%${RESET}"
  if [ "$R5" != "-" ]; then make_reset "$R5" "%H:%M"; OUT="${OUT} ${DIM}${LEFT}${RESET}"; fi
fi

if [ "$W7" != "-" ]; then
  set_color "$W7"; make_bar "$W7"
  OUT="${OUT}   ${DIM}7d${RESET} ${C}${BAR}${RESET} ${C}${W7}%${RESET}"
  if [ "$R7" != "-" ]; then make_reset "$R7" "%d/%m %H:%M"; OUT="${OUT} ${DIM}${LEFT}${RESET}"; fi
fi

printf "%s" "${NOBG}${OUT}${NOBG}"
