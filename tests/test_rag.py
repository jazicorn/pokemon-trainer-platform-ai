"""Tests for RAG components."""

import pytest

from rag.pokeapi_fetcher import extract_pokemon_info
from rag.vector_store import get_simple_embedding, PokemonVectorStore


class TestExtractPokemonInfo:
    """Tests for Pokemon info extraction."""

    def test_extracts_basic_info(self):
        pokemon_data = {
            "name": "pikachu",
            "id": 25,
            "types": [{"type": {"name": "electric"}}],
            "stats": [{"stat": {"name": "hp"}, "base_stat": 35}],
            "abilities": [{"ability": {"name": "static"}}],
            "height": 4,
            "weight": 60,
            "base_experience": 112,
        }

        result = extract_pokemon_info(pokemon_data, None)

        assert result["name"] == "pikachu"
        assert result["id"] == 25
        assert result["types"] == ["electric"]
        assert result["stats"] == {"hp": 35}
        assert result["abilities"] == ["static"]

    def test_extracts_species_info(self):
        pokemon_data = {
            "name": "mewtwo",
            "id": 150,
            "types": [{"type": {"name": "psychic"}}],
            "stats": [],
            "abilities": [],
            "height": 20,
            "weight": 1220,
        }
        species_data = {
            "is_legendary": True,
            "is_mythical": False,
            "generation": {"name": "generation-i"},
            "flavor_text_entries": [
                {"flavor_text": "Test description", "language": {"name": "en"}}
            ],
        }

        result = extract_pokemon_info(pokemon_data, species_data)

        assert result["is_legendary"] is True
        assert result["is_mythical"] is False
        assert result["description"] == "Test description"


class TestEmbedding:
    """Tests for embedding functions."""

    def test_simple_embedding_returns_list(self):
        result = get_simple_embedding("test text")
        assert isinstance(result, list)
        assert len(result) == 48  # sha384 produces 48 bytes

    def test_simple_embedding_deterministic(self):
        result1 = get_simple_embedding("test text")
        result2 = get_simple_embedding("test text")
        assert result1 == result2

    def test_simple_embedding_different_for_different_text(self):
        result1 = get_simple_embedding("pikachu")
        result2 = get_simple_embedding("charizard")
        assert result1 != result2

    def test_simple_embedding_values_normalized(self):
        result = get_simple_embedding("test")
        assert all(0 <= v <= 1 for v in result)


# --- Docker Helper Module (extract to src/testing/docker_helper.py) ---

def get_docker_start_command(
    platform: str, choice: str = "1"
) -> tuple[list[str], str]:
    """Get the command to start Docker based on platform.

    Args:
        platform: sys.platform value ('darwin', 'win32', 'linux')
        choice: For Linux, '1' for systemctl, '2' for Docker Desktop

    Returns:
        Tuple of (command_list, description)
    """
    if platform == "darwin":
        return (["open", "-a", "Docker"], "Starting Docker Desktop...")
    elif platform == "win32":
        return (["cmd", "/c", "start", "Docker Desktop"], "Starting Docker Desktop...")
    else:  # Linux
        if choice == "1":
            return (["sudo", "systemctl", "start", "docker"], "Starting Docker service...")
        elif choice == "2":
            return (
                ["systemctl", "--user", "start", "docker-desktop"],
                "Starting Docker Desktop...",
            )
        else:
            return ([], "Skipping...")


def get_chromadb_docker_command() -> list[str]:
    """Get the command to start ChromaDB container."""
    return [
        "docker", "run", "-d",
        "--name", "chromadb-test",
        "-p", "8000:8000",
        "-e", "ANONYMIZED_TELEMETRY=false",
        "chromadb/chroma:latest",
    ]


class TestDockerHelpers:
    """Tests for Docker helper functions."""

    def test_macos_docker_command(self):
        cmd, desc = get_docker_start_command("darwin")
        assert cmd == ["open", "-a", "Docker"]
        assert "Docker Desktop" in desc

    def test_windows_docker_command(self):
        cmd, desc = get_docker_start_command("win32")
        assert "start" in cmd
        assert "Docker Desktop" in cmd
        assert "Docker Desktop" in desc

    def test_linux_systemctl_command(self):
        cmd, desc = get_docker_start_command("linux", "1")
        assert cmd == ["sudo", "systemctl", "start", "docker"]
        assert "service" in desc.lower()

    def test_linux_docker_desktop_command(self):
        cmd, desc = get_docker_start_command("linux", "2")
        assert "docker-desktop" in cmd
        assert "Docker Desktop" in desc

    def test_linux_skip_returns_empty(self):
        cmd, desc = get_docker_start_command("linux", "3")
        assert cmd == []
        assert "skip" in desc.lower()

    def test_chromadb_command_has_required_flags(self):
        cmd = get_chromadb_docker_command()
        assert "docker" in cmd
        assert "run" in cmd
        assert "-d" in cmd
        assert "8000:8000" in cmd
        assert "chromadb/chroma:latest" in cmd


# --- End Docker Helper Module ---


class TestPokemonVectorStore:
    """Tests for PokemonVectorStore.

    Environment variables for testing different platforms:
        TEST_DOCKER_PLATFORM: Force platform ('darwin', 'win32', 'linux')
        TEST_DOCKER_DRY_RUN: If set, print commands without executing

    Examples:
        # Test Linux systemctl flow on macOS (dry run):
        TEST_DOCKER_PLATFORM=linux TEST_DOCKER_DRY_RUN=1 uv run pytest ... -v -s

        # Test Linux Docker Desktop flow:
        TEST_DOCKER_PLATFORM=linux uv run pytest ... -v -s
        # Then choose option 2 when prompted
    """

    @pytest.fixture
    def sample_pokemon(self):
        return [
            {
                "name": "testmon",
                "types": ["fire", "flying"],
                "stats": {"hp": 100, "attack": 80},
                "abilities": ["blaze"],
                "is_legendary": False,
                "is_mythical": False,
            }
        ]

    @pytest.fixture
    def ensure_chromadb(self):
        """Ensure ChromaDB is running, with interactive prompts."""
        import os
        import subprocess
        import sys
        import time

        from memory.database import is_chromadb_running

        # Allow forcing platform for testing
        forced_platform = os.environ.get("TEST_DOCKER_PLATFORM")
        dry_run = os.environ.get("TEST_DOCKER_DRY_RUN")
        platform = forced_platform or sys.platform

        def print_status(msg: str, end: str = "\n") -> None:
            """Print status message."""
            print(f"    ℹ️  {msg}", end=end, flush=True)

        def print_header() -> None:
            """Print a nice header for the Docker setup."""
            print("\n")
            print("    ╭─────────────────────────────────────────╮")
            print("    │     🧪 ChromaDB Test Environment        │")
            print("    ╰─────────────────────────────────────────╯")
            print()

        def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
            """Run command or print in dry-run mode."""
            if dry_run:
                print(f"\n    🧪 Would run: {' '.join(cmd)}")
                # Return fake success
                return subprocess.CompletedProcess(cmd, 0)
            return subprocess.run(cmd, **kwargs)

        def print_progress(seconds: int) -> bool:
            """Show progress while waiting, return True if ready."""
            if dry_run:
                print("\n    🧪 Would wait for ChromaDB...")
                return True
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            for i in range(seconds * 2):
                if is_chromadb_running():
                    print(" ✅")
                    return True
                sym = spinner[i % len(spinner)]
                print(f"\r    {sym} Waiting for ChromaDB...", end="", flush=True)
                time.sleep(0.5)
            print(" ❌")
            return False

        def wait_for_docker(seconds: int) -> bool:
            """Wait for Docker to be ready."""
            if dry_run:
                print("\n    🧪 Would wait for Docker...")
                return True
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            for i in range(seconds * 2):
                try:
                    result = subprocess.run(
                        ["docker", "info"],
                        capture_output=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        print(" ✅")
                        return True
                except subprocess.TimeoutExpired:
                    pass  # Docker still starting up
                sym = spinner[i % len(spinner)]
                print(f"\r    {sym} Waiting for Docker...", end="", flush=True)
                time.sleep(0.5)
            print(" ❌")
            return False

        def prompt_user(message: str) -> bool:
            """Prompt user for yes/no, default yes. Auto-yes in CI."""
            print_status(f"{message} [Y/n] ", end="")
            try:
                response = input().strip().lower()
                return response == "" or response == "y"
            except EOFError:
                print("(auto: yes)")
                return True

        def start_docker_if_needed() -> bool:
            """Start Docker if not running. Returns True if Docker is ready."""
            # In dry run, simulate Docker not running
            if not dry_run:
                try:
                    result = subprocess.run(
                        ["docker", "info"],
                        capture_output=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        return True
                except FileNotFoundError:
                    print_status("❌ Docker is not installed")
                    print_status("Install from https://docker.com")
                    return False
                except subprocess.TimeoutExpired:
                    pass  # Docker may be starting

            print_status("⚠️  Docker is not running")

            # Get platform-specific command
            if platform == "linux":
                print("\n")
                print("    ╭─────────────────────────────────────────╮")
                print("    │       🐳 Docker Startup Options         │")
                print("    ├─────────────────────────────────────────┤")
                print("    │  [1] 🔧 Start Docker service (systemctl)│")
                print("    │  [2] 🖥️  Start Docker Desktop            │")
                print("    │  [3] ⏭️  Skip this test                  │")
                print("    ╰─────────────────────────────────────────╯")
                print("\n    Enter choice [1/2/3]: ", end="", flush=True)
                try:
                    choice = input().strip() or "1"
                except EOFError:
                    print("1 (auto)")
                    choice = "1"
            else:
                if not prompt_user("Would you like to start Docker Desktop?"):
                    return False
                choice = "1"

            cmd, desc = get_docker_start_command(platform, choice)
            if not cmd:
                return False

            print_status(desc)
            try:
                run_command(cmd, check=True, timeout=30)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass  # May return before Docker is ready

            print_status("Waiting for Docker to start (may take a minute)...")
            return wait_for_docker(60)

        # Check if already running (skip in dry run to test the flow)
        if not dry_run and is_chromadb_running():
            return True

        print_header()

        if forced_platform:
            print(f"    🧪 Testing with forced platform: {platform}")
        if dry_run:
            print("    🧪 Dry run mode - commands will be printed, not executed")
            print()

        print_status("ChromaDB is not running")

        # Ensure Docker is running
        if not start_docker_if_needed():
            pytest.skip("Docker not available")

        # Ask user if they want to start ChromaDB
        if not prompt_user("Would you like to start ChromaDB?"):
            pytest.skip("User declined to start ChromaDB")

        # Try to start existing container first
        print_status("Checking for existing ChromaDB container...")
        result = run_command(
            ["docker", "start", "chromadb-test"],
            capture_output=True,
            timeout=10,
        )

        if result.returncode == 0:
            print_status("Starting existing container...")
            if print_progress(15):
                return True

        # Container doesn't exist, create it
        print_status("Creating new ChromaDB container...")
        print_status("(This may take a moment if pulling the image)")

        try:
            run_command(
                get_chromadb_docker_command(),
                check=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            print_status(f"❌ Failed to create container: {e}")
            pytest.skip("Failed to start ChromaDB container")
        except subprocess.TimeoutExpired:
            print_status("❌ Docker command timed out")
            pytest.skip("Docker command timed out")

        print_status("Container created, waiting for ChromaDB to be ready...")
        if print_progress(20):
            return True

        print_status("❌ ChromaDB failed to start in time")
        pytest.skip("ChromaDB failed to start")

    def test_create_document_text(self, sample_pokemon, ensure_chromadb):
        store = PokemonVectorStore(collection_name="test_pokemon")
        try:
            doc = store._create_document_text(sample_pokemon[0])
            assert "testmon" in doc
            assert "fire" in doc
            assert "flying" in doc
            assert "hp: 100" in doc
        finally:
            try:
                store.delete_collection()
            except Exception:
                pass
            store.close()

    def test_add_and_query_pokemon(self, sample_pokemon, ensure_chromadb):
        store = PokemonVectorStore(collection_name="test_pokemon_query")
        try:
            store.add_pokemon(sample_pokemon)
            results = store.query("fire type pokemon", n_results=1)
            assert len(results) >= 1
            assert "testmon" in results[0]["document"]
        finally:
            try:
                store.delete_collection()
            except Exception:
                pass
            store.close()
            