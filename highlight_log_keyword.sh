#!/bin/zsh

highlight_log() {
  local colors=("\033[1;32m" "\033[1;34m" "\033[1;33m" "\033[1;31m" "\033[1;36m" "\033[1;35m")
  local reset="\033[0m"

  awk_command='{'

  # Generate gsub commands for each parameter and assign different colors
  local i=0
  for word in "$@"; do
    color=${colors[i % ${#colors[@]}]}
    awk_command+="gsub(/$word/, \"$color&$reset\"); "
    ((i++))
  done

  awk_command+='print}'

  # Run the awk command on the input file
  awk "$awk_command"
}

highlight_log "$@"
