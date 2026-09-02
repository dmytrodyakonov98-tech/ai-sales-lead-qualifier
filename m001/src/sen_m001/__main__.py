"""Launch the localhost M001-B001 application."""

from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

from .cas import ContentAddressedStore
from .database import Database
from .service import LeadQualifierService
from .web import create_server


def build_service(data_directory: Path) -> LeadQualifierService:
    """Build the durable application from an owner-selected data directory."""

    data_directory = Path(data_directory)
    database = Database(data_directory / "factory.db")
    database.initialize()
    return LeadQualifierService(
        database,
        ContentAddressedStore(data_directory / "cas"),
    )


def _default_data_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.cwd()
    return base / "SENFactoryM001"


def main() -> None:
    parser = argparse.ArgumentParser(description="SEN Factory M001-B001")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_default_data_directory(),
        help="owner-controlled durable data directory",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()

    service = build_service(arguments.data_dir)
    server = create_server(service, port=arguments.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if not arguments.no_browser:
        webbrowser.open(url)
    print(f"SEN Factory M001-B001 is running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.database.close()


if __name__ == "__main__":
    main()
