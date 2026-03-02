#!/bin/bash
# ChromaDB Docker Manager
# Simple script to manage ChromaDB Docker container

set -e

CONTAINER_NAME="chromadb"
PORT="8000"
DATA_DIR="./chroma_data"
IMAGE="chromadb/chroma:latest"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   ChromaDB Docker Manager${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

# Ask user for permission before taking a step.
# Reads directly from /dev/tty so it always works even after
# subprocesses (like colima start) have consumed stdin.
ask_permission() {
    local message="$1"
    echo ""
    echo -e "${YELLOW}Permission required:${NC} $message"
    echo -n "  Proceed? (y/N): "
    read -n 1 -r REPLY < /dev/tty
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        return 0
    else
        print_warning "Skipped."
        return 1
    fi
}

# ─────────────────────────────────────────────
# macOS / Colima helpers
# ─────────────────────────────────────────────

is_macos() {
    [[ "$(uname -s)" == "Darwin" ]]
}

colima_installed() {
    command -v colima &> /dev/null
}

colima_running() {
    # Use the socket file as the single source of truth — it exists if and
    # only if Colima is actually up and Docker can connect to it.
    # Avoids running `colima status` which can produce output that disrupts stdin.
    local socket="${HOME}/.colima/default/docker.sock"
    [[ -S "$socket" ]]
}

brew_installed() {
    command -v brew &> /dev/null
}

install_homebrew() {
    print_info "Homebrew is required to install Colima."
    if ask_permission "Install Homebrew (https://brew.sh)"; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        print_status "Homebrew installed."
    else
        print_error "Homebrew is required to install Colima. Cannot continue."
        exit 1
    fi
}

install_colima() {
    print_info "Colima is not installed. Colima is a lightweight Docker runtime for macOS."
    if ask_permission "Install Colima via Homebrew (brew install colima docker)"; then
        if ! brew_installed; then
            install_homebrew
        fi
        brew install colima docker
        print_status "Colima and Docker CLI installed."
    else
        print_error "Colima is required to run Docker on macOS without Docker Desktop. Cannot continue."
        exit 1
    fi
}

_try_colima_delete_restart() {
    # Called with an optional --vm-type argument, e.g. "--vm-type qemu"
    local extra_args="$*"
    local cmd="colima start${extra_args:+ $extra_args}"

    print_warning "This will delete the existing Colima VM and recreate it."
    echo "   Docker containers and images are NOT stored in the VM directory"
    echo "   and will not be lost."
    echo ""
    # Use || true so set -e does not abort the script when user answers N
    ask_permission "Run: colima delete && ${cmd}" || return 1

    echo ""
    print_info "Deleting existing Colima VM..."
    colima delete --force 2>/dev/null || colima delete

    print_info "Starting fresh Colima VM (${cmd})..."
    # Word-splitting is intentional here: $extra_args may contain "--vm-type qemu"
    # which must be passed as two separate arguments, not one quoted string.
    # shellcheck disable=SC2086
    if colima start $extra_args; then
        print_status "Colima started successfully."
        return 0
    else
        print_error "Colima still failed to start after recreating the VM."
        return 1
    fi
}

diagnose_colima_failure() {
    print_warning "Running diagnostics to identify the problem..."
    echo ""

    local lima_log="${HOME}/.colima/_lima/colima/ha.stderr.log"

    # ── 1. Lima stderr log (most specific failure reason) ─────────────────
    if [ -f "$lima_log" ]; then
        echo -e "${CYAN}── Lima boot log (last 20 lines) ──────────────────────────${NC}"
        tail -20 "$lima_log"
        echo ""
    fi

    # ── 2. Locked disk (most common cause of the VZ "exit status 1" error) ─
    local _locked_disk_checked=0
    if [ -f "$lima_log" ] && grep -q "in use by instance" "$lima_log"; then
        _locked_disk_checked=1
        print_error "Detected: VM disk is locked by a previous crashed Colima process."
        echo "   The fix is to delete and recreate the VM."
        echo ""
        _try_colima_delete_restart || true
        if colima_running; then return 0; fi
        echo ""
    fi

    # ── 3. macOS virtualisation support ───────────────────────────────────
    if is_macos; then
        local vz_ok
        vz_ok=$(sysctl -n kern.hv_support 2>/dev/null || echo "0")
        if [ "$vz_ok" = "1" ]; then
            print_status "Hypervisor framework is supported on this Mac."
        else
            print_error "Hypervisor framework is NOT available (kern.hv_support=0)."
            echo "   This Mac may not support hardware virtualisation."
            echo "   Try running Colima with QEMU instead of VZ:"
            echo "     colima delete && colima start --vm-type qemu"
        fi
        echo ""
    fi

    # ── 4. VZ driver — offer QEMU fallback (skip if locked-disk already handled) ─
    if [ "$_locked_disk_checked" -eq 0 ] && colima list 2>/dev/null | grep -q "vz"; then
        print_info "Your Colima instance is configured to use the VZ driver."
        echo "   If VZ keeps crashing, try the QEMU driver instead."
        echo ""
        _try_colima_delete_restart "--vm-type qemu" || true
        if colima_running; then return 0; fi
        echo ""
    fi

    # ── 5. Stale VM directory (fallback — skip if a more specific cause was found) ─
    local colima_dir="${HOME}/.colima/default"
    if [ "$_locked_disk_checked" -eq 0 ] && [ -d "$colima_dir" ]; then
        print_info "Existing Colima VM directory: ${colima_dir}"
        echo "   Recreating the VM often fixes corrupt state."
        echo ""
        _try_colima_delete_restart || true
        if colima_running; then return 0; fi
        echo ""
    fi

    # ── 6. Disk space ─────────────────────────────────────────────────────
    local free_gb
    free_gb=$(df -g / 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$free_gb" ] && [ "$free_gb" -lt 5 ]; then
        print_warning "Low disk space: only ${free_gb} GB free on /."
        echo "   Colima needs at least 5 GB free to create a VM disk."
        echo ""
    fi

    # ── Summary (reached only if all auto-fix attempts were skipped/failed) ─
    echo -e "${YELLOW}── Manual fixes to try (in order) ─────────────────────────${NC}"
    echo "  1. Recreate the VM:       colima delete && colima start"
    echo "  2. Switch to QEMU driver: colima delete && colima start --vm-type qemu"
    echo "  3. Full Lima log:         cat ${lima_log}"
    echo "  4. Colima GitHub issues:  https://github.com/abiosoft/colima/issues"
    echo ""
}

start_colima() {
    print_info "Colima is installed but not running. The Docker daemon needs Colima to be active."
    if ! ask_permission "Start Colima (colima start)"; then
        print_error "Colima must be running for Docker to work. Cannot continue."
        exit 1
    fi

    if colima start; then
        print_status "Colima started."
        echo "Waiting for Colima to be ready..."
        sleep 3
    else
        echo ""
        print_error "Colima failed to start."
        # diagnose_colima_failure returns 0 if an auto-fix succeeded
        diagnose_colima_failure || true
        if ! colima_running; then
            exit 1
        fi
        print_status "Colima is now running after auto-fix."
    fi
}

# Full check: install Colima if missing, start it if stopped.
# Only called for commands that actively need the Docker daemon (start, logs).
ensure_docker_runtime() {
    if ! is_macos; then
        return
    fi

    print_info "macOS detected. Checking Docker runtime (Colima)..."
    echo ""

    if ! colima_installed; then
        print_warning "Colima is not installed."
        install_colima
    else
        print_status "Colima is installed."
    fi

    if ! colima_running; then
        print_warning "Colima is not running."
        start_colima
    else
        print_status "Colima is already running."
    fi

    echo ""
}


# ─────────────────────────────────────────────
# Docker helpers
# ─────────────────────────────────────────────

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker CLI is not installed."
        if is_macos; then
            echo "It should have been installed with Colima. Try: brew install docker"
        else
            echo "Install Docker: https://docs.docker.com/get-docker/"
        fi
        exit 1
    fi
    print_status "Docker is installed."
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"
}

container_running() {
    docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"
}

# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────

start_container() {
    echo "Starting ChromaDB container..."

    if container_running; then
        print_warning "Container is already running."
        show_status
        return
    fi

    if container_exists; then
        print_info "Container exists but is stopped."
        if ask_permission "Start the existing '${CONTAINER_NAME}' container"; then
            docker start "${CONTAINER_NAME}"
            print_status "Container started."
        else
            return
        fi
    else
        print_info "No existing container found. A new one will be created."
        print_info "  Image:      ${IMAGE}"
        print_info "  Port:       ${PORT}"
        print_info "  Data dir:   $(pwd)/${DATA_DIR}"
        if ask_permission "Create and start a new ChromaDB container with the settings above"; then
            docker run -d \
                --name "${CONTAINER_NAME}" \
                -p "${PORT}:8000" \
                -v "$(pwd)/${DATA_DIR}:/chroma/chroma" \
                "${IMAGE}"
            print_status "Container created and started."
        else
            return
        fi
    fi

    echo ""
    echo "Waiting for server to be ready..."
    sleep 3

    if curl -s "http://localhost:${PORT}/api/v2/heartbeat" > /dev/null 2>&1; then
        print_status "Server is ready!"
        echo ""
        echo "  Access ChromaDB at: http://localhost:${PORT}"
        echo "  Data directory:     ${DATA_DIR}"
    else
        print_warning "Server may still be starting up..."
        echo "  Check logs with: $0 logs"
    fi
}

stop_container() {
    echo "Stopping ChromaDB container..."

    if ! container_running; then
        print_warning "Container is not running."
        return
    fi

    if ask_permission "Stop the '${CONTAINER_NAME}' container"; then
        docker stop "${CONTAINER_NAME}"
        print_status "Container stopped."
    fi
}

restart_container() {
    echo "Restarting ChromaDB container..."

    if container_exists; then
        if ask_permission "Restart the '${CONTAINER_NAME}' container"; then
            docker restart "${CONTAINER_NAME}"
            print_status "Container restarted."

            echo "Waiting for server..."
            sleep 3

            if curl -s "http://localhost:${PORT}/api/v2/heartbeat" > /dev/null 2>&1; then
                print_status "Server is ready!"
            fi
        fi
    else
        print_error "Container does not exist."
        echo "Run: $0 start"
    fi
}

show_status() {
    echo "Container Status:"
    echo "----------------"

    if container_running; then
        print_status "Container is running."
        echo ""
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo ""

        if curl -s "http://localhost:${PORT}/api/v2/heartbeat" > /dev/null 2>&1; then
            print_status "Server is responding."
            echo "  URL: http://localhost:${PORT}"
        else
            print_warning "Server is not responding."
        fi
    elif container_exists; then
        print_warning "Container exists but is stopped."
        echo "  Run: $0 start"
    else
        print_warning "Container does not exist."
        echo "  Run: $0 start"
    fi

    echo ""
    echo "  Data directory: ${DATA_DIR}"
    if [ -d "${DATA_DIR}" ]; then
        local SIZE
        SIZE=$(du -sh "${DATA_DIR}" 2>/dev/null | cut -f1)
        echo "  Data size: ${SIZE}"
    fi

    if is_macos && colima_installed; then
        echo ""
        if colima_running; then
            print_status "Colima is running."
        else
            print_warning "Colima is not running. Start it with: colima start"
        fi
    fi
}

show_logs() {
    if ! container_exists; then
        print_error "Container does not exist."
        exit 1
    fi

    echo "Showing logs (press Ctrl+C to exit)..."
    echo ""
    docker logs -f "${CONTAINER_NAME}"
}

remove_container() {
    echo "Removing ChromaDB container..."

    if container_running; then
        if ask_permission "Stop the running '${CONTAINER_NAME}' container first"; then
            docker stop "${CONTAINER_NAME}"
            print_status "Container stopped."
        else
            print_error "Cannot remove a running container without stopping it first."
            return
        fi
    fi

    if container_exists; then
        if ask_permission "Remove the '${CONTAINER_NAME}' container"; then
            docker rm "${CONTAINER_NAME}"
            print_status "Container removed."
        else
            return
        fi
    else
        print_warning "Container does not exist."
    fi

    echo ""
    if [ -d "${DATA_DIR}" ]; then
        print_info "Data directory found: ${DATA_DIR} ($(du -sh "${DATA_DIR}" 2>/dev/null | cut -f1))"
        if ask_permission "Also delete the data directory '${DATA_DIR}' (this is permanent)"; then
            rm -rf "${DATA_DIR}"
            print_status "Data directory removed."
        else
            print_status "Data directory preserved."
        fi
    fi
}

pull_image() {
    ask_permission "Pull the latest ChromaDB image ('${IMAGE}') from Docker Hub" || return
    docker pull "${IMAGE}"
    print_status "Image updated."

    if container_running; then
        echo ""
        print_warning "Container is still running with the old image."
        if ask_permission "Stop, remove, and recreate the container with the new image"; then
            docker stop "${CONTAINER_NAME}"
            docker rm "${CONTAINER_NAME}"
            start_container
        fi
    fi
}

show_help() {
    cat << EOF
ChromaDB Docker Manager

Usage: $0 [command]

Commands:
  start       Start ChromaDB container (creates if needed)
  stop        Stop ChromaDB container
  restart     Restart ChromaDB container
  status      Show container and server status
  logs        Show container logs (follow mode)
  remove      Remove container (asks about data)
  update      Pull latest image and restart
  help        Show this help message

Examples:
  $0 start          # Start the server
  $0 status         # Check if it's running
  $0 logs           # View server logs
  $0 stop           # Stop the server

After starting, connect from Python using httpx:
  import httpx
  BASE = "http://localhost:${PORT}/api/v2/tenants/default_tenant/databases/default_database"
  r = httpx.get("http://localhost:${PORT}/api/v2/heartbeat")
  r.raise_for_status()

Data is stored in: ${DATA_DIR}

macOS note:
  This script automatically checks for and manages Colima,
  a lightweight Docker runtime for macOS. You will be asked
  before Colima is installed or started.
EOF
}

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

main() {
    case "${1:-help}" in
        start)
            print_header
            ensure_docker_runtime
            check_docker
            echo ""
            start_container
            ;;
        logs)
            ensure_docker_runtime
            check_docker
            echo ""
            show_logs
            ;;
        stop)
            print_header
            check_docker
            echo ""
            stop_container
            ;;
        restart)
            print_header
            check_docker
            echo ""
            restart_container
            ;;
        status)
            print_header
            check_docker
            echo ""
            show_status
            ;;
        remove|rm)
            print_header
            check_docker
            echo ""
            remove_container
            ;;
        update|pull)
            print_header
            check_docker
            echo ""
            pull_image
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac

    echo ""
}

main "$@"
