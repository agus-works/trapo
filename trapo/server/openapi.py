from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from trapo.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write the Trapo FastAPI OpenAPI schema."
    )
    parser.add_argument(
        "--output",
        default="web/openapi/trapo.openapi.json",
        help="Path for the generated OpenAPI JSON file.",
    )
    args = parser.parse_args()
    output_path = Path(args.output)
    os.environ["TRAPO_OTEL_ENABLED"] = "false"
    app = create_app("trapo.openapi.duckdb")
    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
