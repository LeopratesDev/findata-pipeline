"""Ponto de entrada do pipeline.

Fluxo: coleta -> validacao -> persistencia -> relatorio -> resumo no
terminal -> codigo de saida (0 ok; 1 se houve erro de coleta ou falha
inesperada). O logging e configurado por variavel de ambiente.

``run_pipeline`` recebe o cliente e o banco ja construidos, para que a
orquestracao seja testavel de ponta a ponta sem rede nem CLI.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Optional, Sequence

from . import config
from .database import Database, WriteStats
from .reporter import ExecutionReport, SeriesOutcome
from .scraper import ScraperError, SgsClient
from .validator import utc_now_iso, validate_records

logger = logging.getLogger("findata_pipeline.main")


def configure_logging(level: Optional[str] = None) -> None:
    logging.basicConfig(
        level=getattr(logging, (level or config.LOG_LEVEL).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def run_pipeline(
    client: SgsClient,
    db: Database,
    series_ids: Optional[Sequence[str]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> ExecutionReport:
    """Executa o pipeline para as series indicadas e devolve o relatorio."""
    series_ids = list(series_ids) if series_ids else list(config.SERIES.keys())
    started_at = utc_now_iso()
    collected_at = started_at
    run_id = db.start_run(config.SOURCE, started_at)

    report = ExecutionReport(source=config.SOURCE, started_at=started_at, finished_at="")
    agg = WriteStats()
    total_extracted = total_valid = total_rejected = 0

    for sid in series_ids:
        series = config.SERIES[sid]
        outcome = SeriesOutcome(series_id=sid)
        try:
            raw = client.fetch_series(series, start=start, end=end)
        except ScraperError as exc:
            message = f"{sid}: coleta falhou: {exc}"
            logger.error(message)
            report.errors.append(message)
            report.outcomes.append(outcome)  # contagens zeradas para a serie
            continue

        result = validate_records(raw, series, collected_at=collected_at)
        stats = db.insert_observations(result.valid)
        db.insert_rejections(run_id, result.rejected, collected_at)

        outcome.extracted = len(raw)
        outcome.valid = len(result.valid)
        outcome.rejected = len(result.rejected)
        outcome.inserted = stats.inserted
        outcome.duplicates = stats.duplicates
        outcome.revisions = stats.revisions
        report.outcomes.append(outcome)

        total_extracted += outcome.extracted
        total_valid += outcome.valid
        total_rejected += outcome.rejected
        agg.inserted += stats.inserted
        agg.duplicates += stats.duplicates
        agg.revisions += stats.revisions

    report.finished_at = utc_now_iso()
    status = "done" if not report.errors else "completed_with_errors"
    db.finish_run(
        run_id, report.finished_at,
        extracted=total_extracted, valid=total_valid, rejected=total_rejected,
        stats=agg, status=status,
    )
    return report


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FinData Pipeline - coleta de indicadores do BCB/SGS")
    parser.add_argument("--db", default=config.DB_PATH, help="caminho do SQLite")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="formato do relatorio")
    parser.add_argument("--days", type=int, default=180, help="janela de coleta em dias (padrao 180)")
    parser.add_argument("--series", action="append", choices=list(config.SERIES.keys()),
                        help="serie a coletar (repetivel); padrao = todas")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    configure_logging()

    end = date.today()
    start = end - timedelta(days=args.days)

    db = Database(args.db)
    db.initialize()
    try:
        report = run_pipeline(SgsClient(), db, series_ids=args.series, start=start, end=end)
        report_path = report.save(str(config.PROJECT_ROOT / "reports"), fmt=args.format)
        print(report.to_terminal())
        print(f"Relatorio: {report_path}")
        return 1 if report.errors else 0
    except Exception as exc:  # falha inesperada -> codigo de saida != 0
        logger.exception("falha inesperada na execucao: %s", exc)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
