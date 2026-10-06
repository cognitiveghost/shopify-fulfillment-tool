"""Generate packing lists and stock exports, off the GUI thread.

The Results screen's Generate Reports runs `generate_reports` on a Worker
(AUDIT-09-O2): the window stays usable while the files are written, and the
toasts arrive when they are done. Nothing here touches Qt; each report's
result comes back as a `ReportOutcome` that the GUI thread turns into a
toast or an error.

Every job works on a snapshot taken on the GUI thread at the click (the
frame, the tag categories, the session id), so an edit made while reports
generate never reaches a file half-way through.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import barcode_processor, core, packing_lists, report_filters, stock_export

logger = logging.getLogger(__name__)


@dataclass
class ReportOutcome:
    """What happened to one report of a batch."""

    name: str
    report_type: str
    output_file: str | None = None
    # Set by a "separate" packaging write-off, which saves a second file.
    packaging_file: str | None = None
    # An empty packing list: its old files were removed (AUDIT-04-3).
    removed_empty: bool = False
    failed: bool = False
    # The file another program holds open, when that is why it failed.
    locked_file: str | None = None


def packing_list_json(df: pd.DataFrame, session_id: str) -> dict:
    """The packing list JSON for Packing Tool.

    Its orders come from core.build_packing_orders, so they carry the same
    canonical fields as analysis_data.json.
    """
    orders_data = core.build_packing_orders(df)
    return {
        "session_id": session_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "total_orders": len(orders_data),
        "total_items": int(df["Quantity"].sum()) if "Quantity" in df.columns else len(df),
        "orders": orders_data,
    }


def _output_file(report_type: str, report_name: str, report_config: dict, output_dir: Path) -> str:
    base_filename = report_config.get("output_filename", "")
    if not base_filename:
        base_filename = f"{report_name}.xlsx" if report_type == "packing_lists" else f"{report_name}.xls"

    # Ensure correct extension
    if report_type == "packing_lists":
        if not base_filename.endswith(".xlsx"):
            base_filename = base_filename.replace(".xls", ".xlsx")
    elif not base_filename.endswith(".xls"):
        base_filename = base_filename + ".xls"
    return str(output_dir / base_filename)


def generate_report(
    report_config: dict,
    session_path,
    analysis_df: pd.DataFrame,
    tag_categories: dict,
    session_id: str,
) -> ReportOutcome:
    """Write one report's files; `report_config["report_type"]` picks the kind.

    Never raises: a file another program holds open gives `failed` with
    `locked_file`, any other error is logged and gives `failed`.
    """
    report_type = report_config.get("report_type")
    report_name = report_config.get("name", "Unknown")
    logger.info(f"Generating {report_type}: {report_name}")

    try:
        if report_type == "packing_lists":
            output_dir = Path(session_path) / "packing_lists"
        elif report_type == "stock_exports":
            output_dir = Path(session_path) / "stock_exports"
        else:
            raise ValueError(f"Unknown report type: {report_type}")
        output_dir.mkdir(parents=True, exist_ok=True)

        filters = report_config.get("filters", [])
        output_file = _output_file(report_type, report_name, report_config, output_dir)
        if report_type == "stock_exports":
            # Stamps the name, moving earlier versions to old/
            output_file = stock_export.prepare_export_path(output_file)

        outcome = ReportOutcome(report_name, report_type, output_file=output_file)

        if report_type == "packing_lists":
            # Label PDFs from before could label orders this list no longer
            # holds (AUDIT-04-12). First, so a PDF held open in a viewer
            # stops the run before the XLSX and JSON can diverge.
            barcode_processor.invalidate_label_pdfs(session_path, Path(output_file).stem)

            # The module applies the filters itself.
            written = packing_lists.create_packing_list(
                analysis_df=analysis_df,
                output_file=output_file,
                report_name=report_name,
                filters=filters,
                exclude_skus=report_config.get("exclude_skus"),
                columns=report_config.get("columns"),
            )

            json_path = str(Path(output_file).with_suffix(".json"))
            if not written:
                # An empty list must not leave the last run's files behind
                # for the packers to pick up (AUDIT-04-3)
                Path(output_file).unlink(missing_ok=True)
                Path(json_path).unlink(missing_ok=True)
                outcome.removed_empty = True
            else:
                logger.info(f"Packing list XLSX created: {output_file}")
                try:
                    filtered_df = report_filters.apply_report_filters(
                        report_filters.fulfillable_only(analysis_df), filters
                    )
                    # Same exclusion as the XLSX (AUDIT-04-4)
                    json_df = report_filters.exclude_skus(
                        filtered_df, report_config.get("exclude_skus")
                    )
                    # ponytail: written in place; atomic writes are AUDIT-09-O5 (#370)
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(packing_list_json(json_df, session_id), f, ensure_ascii=False, indent=2)
                    logger.info(f"Packing list JSON created: {json_path}")
                except Exception:
                    logger.exception("Failed to create JSON")
                    # Don't fail the whole report if JSON fails

        else:
            outcome.packaging_file = stock_export.create_stock_export(
                analysis_df=analysis_df,
                output_file=output_file,
                report_name=report_name,
                filters=filters,
                writeoff_mode=report_config.get("writeoff_mode", "off"),
                tag_categories=tag_categories,
            )
            logger.info(f"Stock export created: {output_file}")

        logger.info(f"Report generated: {output_file}")
        return outcome

    except PermissionError as e:
        logger.exception(f"Failed to generate report '{report_name}'")
        locked = Path(e.filename).name if e.filename else "The file"
        return ReportOutcome(report_name, report_type, failed=True, locked_file=locked)
    except Exception:
        logger.exception(f"Failed to generate report '{report_name}'")
        return ReportOutcome(report_name, report_type, failed=True)


def generate_reports(
    batch: list[dict],
    session_path,
    analysis_df: pd.DataFrame,
    tag_categories: dict,
    session_id: str,
    session_manager=None,
) -> list[ReportOutcome]:
    """One outcome per config, in batch order; one failure never stops the others.

    When a packing list was generated and `session_manager` is given, the
    session's packing list statistics are updated once at the end.
    """
    outcomes = []
    for report_config in batch:
        try:
            outcome = generate_report(
                report_config, session_path, analysis_df, tag_categories, session_id
            )
        except Exception:
            logger.exception(f"Failed to generate {report_config.get('name')}")
            outcome = ReportOutcome(
                report_config.get("name", "Unknown"), report_config.get("report_type"), failed=True
            )
        outcomes.append(outcome)

    if session_manager is not None and any(
        o.report_type == "packing_lists" and not o.failed for o in outcomes
    ):
        _update_packing_list_statistics(session_manager, session_path)
    return outcomes


def _update_packing_list_statistics(session_manager, session_path) -> None:
    """Record the session's packing lists in session_info's statistics."""
    try:
        packing_lists_dir = Path(session_path) / "packing_lists"
        if not packing_lists_dir.exists():
            return
        names = sorted(f.stem for f in packing_lists_dir.glob("*.json"))
        session_info = session_manager.get_session_info(str(session_path))
        if not session_info:
            return
        statistics = session_info.get("statistics", {})
        statistics["packing_lists_count"] = len(names)
        statistics["packing_lists"] = names
        session_manager.update_session_info(str(session_path), {"statistics": statistics})
        logger.info(f"Updated session statistics: {len(names)} packing lists")
    except Exception as e:
        # Don't fail the report if statistics update fails
        logger.warning(f"Failed to update session statistics: {e}")
