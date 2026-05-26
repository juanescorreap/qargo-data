import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(Path(__file__).parents[1] / ".env")

from ingestion.loader import FileBasedLoader
from ingestion.sources.csv import LS2CSVIngester, PAR2CSVIngester

DATA_DIR = Path(__file__).parents[1] / "data"

INGESTERS = [
    PAR2CSVIngester(),
    LS2CSVIngester(),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Qargo Data Ingestion")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignorar historial de archivos procesados y recargar todo.",
    )
    parser.add_argument(
        "--source",
        help="Nombre de la fuente a cargar (par2, ls2). Por defecto carga todas.",
    )
    args = parser.parse_args()

    engine = create_engine(os.environ["SUPABASE_DB_URL"])
    loader = FileBasedLoader(engine, DATA_DIR)

    ingesters = INGESTERS
    if args.source:
        ingesters = [i for i in INGESTERS if i.source_name == args.source]
        if not ingesters:
            available = [i.source_name for i in INGESTERS]
            raise SystemExit(
                f"Source '{args.source}' no encontrado. Disponibles: {available}"
            )

    total = 0
    for ingester in ingesters:
        total += loader.load(ingester, full_refresh=args.full_refresh)

    print(f"\nTotal general: {total} filas cargadas.")


if __name__ == "__main__":
    main()
