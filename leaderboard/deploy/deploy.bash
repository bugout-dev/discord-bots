#!/usr/bin/env bash

# Deployment script

# Colors
C_RESET='\033[0m'
C_RED='\033[1;31m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'

# Logs
PREFIX_INFO="${C_GREEN}[INFO]${C_RESET} [$(date +%d-%m\ %T)]"
PREFIX_WARN="${C_YELLOW}[WARN]${C_RESET} [$(date +%d-%m\ %T)]"
PREFIX_CRIT="${C_RED}[CRIT]${C_RESET} [$(date +%d-%m\ %T)]"

# Main
APP_DIR="${APP_DIR:-/home/ubuntu/discord-bots/leaderboard}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
PYTHON_ENV_DIR="${PYTHON_ENV_DIR:-/home/ubuntu/discord-bots-leaderboard-env}"
PYTHON="${PYTHON_ENV_DIR}/bin/python"
PIP="${PYTHON_ENV_DIR}/bin/pip"
SCRIPT_DIR="$(realpath $(dirname $0))"
SECRETS_DIR="${SECRETS_DIR:-/home/ubuntu/discord-bots-leaderboard-secrets}"
PARAMETERS_ENV_PATH="${SECRETS_DIR}/app.env"
USER_SYSTEMD_DIR="${USER_SYSTEMD_DIR:-/home/ubuntu/.config/systemd/user}"

# Discord bots leaderboard service files
DISCORD_BOTS_LEADERBOARD_SERVICE_FILE="discord-bots-leaderboard.service"
DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE="discord-bots-leaderboard-api.service"

set -eu

echo
echo
echo -e "${PREFIX_INFO} Upgrading Python pip and setuptools"
"${PIP}" install --upgrade pip setuptools

echo
echo
echo -e "${PREFIX_INFO} Installing Python dependencies"
"${PIP}" install -e "${APP_DIR}/[api]"

echo
echo
echo -e "${PREFIX_INFO} Add instance local IP and AWS region to parameters"
echo "AWS_LOCAL_IPV4=$(ec2metadata --local-ipv4)" > "${PARAMETERS_ENV_PATH}"
echo "AWS_REGION=${AWS_DEFAULT_REGION}" >> "${PARAMETERS_ENV_PATH}"

echo
echo
echo -e "${PREFIX_INFO} Retrieving deployment parameters"
LEADERBOARD_DISCORD_BOT_TOKEN=$(HOME=/home/ubuntu AWS_DEFAULT_REGION=us-east-1 aws ssm get-parameter --query "Parameter.Value" --output text --name LEADERBOARD_DISCORD_BOT_TOKEN)
echo "LEADERBOARD_DISCORD_BOT_TOKEN=${LEADERBOARD_DISCORD_BOT_TOKEN}" >> "${PARAMETERS_ENV_PATH}"

MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN=$(HOME=/home/ubuntu AWS_DEFAULT_REGION=us-east-1 aws ssm get-parameter --query "Parameter.Value" --output text --with-decryption --name MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN)
echo "MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN=${MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN}" >> "${PARAMETERS_ENV_PATH}"

MOONSTREAM_APPLICATION_ID=$(HOME=/home/ubuntu AWS_DEFAULT_REGION=us-east-1 aws ssm get-parameter --query "Parameter.Value" --output text --name MOONSTREAM_APPLICATION_ID)
echo "MOONSTREAM_APPLICATION_ID=${MOONSTREAM_APPLICATION_ID}" >> "${PARAMETERS_ENV_PATH}"

LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS=$(HOME=/home/ubuntu AWS_DEFAULT_REGION=us-east-1 aws ssm get-parameter --query "Parameter.Value" --output text --name LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS)
echo "LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS=${LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS}" >> "${PARAMETERS_ENV_PATH}"

echo
echo
echo -e "${PREFIX_INFO} Prepare user systemd directory"
if [ ! -d "${USER_SYSTEMD_DIR}" ]; then
  mkdir -p "${USER_SYSTEMD_DIR}"
  echo -e "${PREFIX_WARN} Created new user systemd directory"
fi

echo
echo
echo -e "${PREFIX_INFO} Replacing existing Discord leaderboard bot service definition with ${DISCORD_BOTS_LEADERBOARD_SERVICE_FILE}"
chmod 644 "${SCRIPT_DIR}/${DISCORD_BOTS_LEADERBOARD_SERVICE_FILE}"
cp "${SCRIPT_DIR}/${DISCORD_BOTS_LEADERBOARD_SERVICE_FILE}" "${USER_SYSTEMD_DIR}/${DISCORD_BOTS_LEADERBOARD_SERVICE_FILE}"
XDG_RUNTIME_DIR="/run/user/1000" systemctl --user daemon-reload
XDG_RUNTIME_DIR="/run/user/1000" systemctl --user restart --no-block "${DISCORD_BOTS_LEADERBOARD_SERVICE_FILE}"

echo
echo
echo -e "${PREFIX_INFO} Replacing existing Discord leaderboard bot API service definition with ${DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE}"
chmod 644 "${SCRIPT_DIR}/${DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE}"
cp "${SCRIPT_DIR}/${DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE}" "${USER_SYSTEMD_DIR}/${DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE}"
XDG_RUNTIME_DIR="/run/user/1000" systemctl --user daemon-reload
XDG_RUNTIME_DIR="/run/user/1000" systemctl --user restart --no-block "${DISCORD_BOTS_LEADERBOARD_API_SERVICE_FILE}"
