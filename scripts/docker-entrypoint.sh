#!/bin/sh
set -eu

APP_USER="appuser"
DEFAULT_ACTIVITY_LOG_PATH="logs/catalog_activity.log"

is_truthy() {
    value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
    case "$value" in
        1|true|yes|on) return 0 ;;
    esac
    return 1
}

prepare_activity_log_path() {
    log_path="${ACTIVITY_LOG_FILE_PATH:-$DEFAULT_ACTIVITY_LOG_PATH}"
    [ -n "$log_path" ] || return 0

    case "$log_path" in
        /*) absolute_log_path="$log_path" ;;
        *) absolute_log_path="/app/$log_path" ;;
    esac

    log_dir="$(dirname "$absolute_log_path")"

    mkdir -p "$log_dir" || {
        echo "WARN: cannot create activity log directory: $log_dir" >&2
        return 0
    }
    touch "$absolute_log_path" || {
        echo "WARN: cannot create activity log file: $absolute_log_path" >&2
        return 0
    }

    if [ "$(id -u)" -eq 0 ]; then
        chown "$APP_USER:$APP_USER" "$log_dir" "$absolute_log_path" 2>/dev/null || \
            echo "WARN: cannot chown activity log path to $APP_USER: $absolute_log_path" >&2
    fi
}

drop_privileges_and_exec() {
    if [ "$(id -u)" -eq 0 ]; then
        if command -v runuser >/dev/null 2>&1; then
            exec runuser -u "$APP_USER" -- "$@"
        fi
        echo "ERROR: runuser is required to drop privileges from root to $APP_USER" >&2
        exit 1
    fi
    exec "$@"
}

if is_truthy "${ACTIVITY_LOG_ENABLED:-true}"; then
    prepare_activity_log_path
fi

drop_privileges_and_exec "$@"
