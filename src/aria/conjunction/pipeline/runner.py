"""
End-to-end conjunction prediction pipeline.

Full flow:
  1. Ingest catalog (TLEs)
  2. Screen (Smart Sieve — 3-stage cascade)
  3. Find TCA for each candidate pair
  4. Compute collision probability (Pc)
  5. Classify risk (GREEN/YELLOW/RED)
  6. Generate CDMs for YELLOW/RED events
  7. Plan maneuvers for RED events

This is the main entry point for running conjunction assessment.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from aria.conjunction.conjunction.close_approach import build_close_approaches_batch
from aria.conjunction.conjunction.tca_finder import TCAFinder
from aria.conjunction.core.types import CloseApproach, RiskLevel, SpaceObject
from aria.conjunction.maneuver.planning import ManeuverPlan, ManeuverPlanner
from aria.conjunction.pipeline.alerts import Alert, AlertClassifier
from aria.conjunction.pipeline.cdm_writer import CDMWriter
from aria.conjunction.probability.pc_calculator import PcCalculator
from aria.conjunction.screening.screener import SmartSieveScreener

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a full conjunction assessment run."""

    # Inputs
    catalog_size: int
    screening_window_hours: float
    run_start: datetime = field(default_factory=datetime.utcnow)

    # Screening
    total_pairs_checked: int = 0
    pairs_after_stage1: int = 0
    pairs_after_stage2: int = 0
    candidates: int = 0

    # Assessment
    close_approaches: list[CloseApproach] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    cdms: list[str] = field(default_factory=list)
    maneuver_plans: list[ManeuverPlan] = field(default_factory=list)

    # Timing
    run_end: datetime | None = None
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        """Human-readable summary of the pipeline run."""
        red = sum(1 for a in self.alerts if a.risk_level == RiskLevel.RED)
        yellow = sum(1 for a in self.alerts if a.risk_level == RiskLevel.YELLOW)
        return (
            f"Conjunction Assessment Report\n"
            f"{'=' * 50}\n"
            f"Catalog: {self.catalog_size} objects\n"
            f"Window: {self.screening_window_hours}h\n"
            f"Total pairs: {self.total_pairs_checked:,}\n"
            f"After screening: {self.candidates} candidates\n"
            f"Close approaches: {len(self.close_approaches)}\n"
            f"Alerts: {red} RED, {yellow} YELLOW\n"
            f"CDMs generated: {len(self.cdms)}\n"
            f"Maneuver plans: {len(self.maneuver_plans)}\n"
            f"Elapsed: {self.elapsed_seconds:.1f}s\n"
        )


class ConjunctionPipeline:
    """Full conjunction assessment pipeline."""

    def __init__(
        self,
        screener: SmartSieveScreener | None = None,
        tca_finder: TCAFinder | None = None,
        pc_calculator: PcCalculator | None = None,
        alert_classifier: AlertClassifier | None = None,
        cdm_writer: CDMWriter | None = None,
        maneuver_planner: ManeuverPlanner | None = None,
        max_workers: int | None = None,
    ):
        self.screener = screener or SmartSieveScreener()
        self.tca_finder = tca_finder or TCAFinder()
        self.pc_calculator = pc_calculator or PcCalculator()
        self.alert_classifier = alert_classifier or AlertClassifier()
        self.cdm_writer = cdm_writer or CDMWriter()
        self.maneuver_planner = maneuver_planner or ManeuverPlanner()
        self.max_workers = max_workers  # None = os.cpu_count()

    def run(
        self,
        objects: list[SpaceObject],
        window_hours: float = 72.0,
        start_epoch: datetime | None = None,
    ) -> PipelineResult:
        """Execute the full conjunction assessment pipeline.

        Args:
            objects: List of SpaceObjects (from catalog)
            window_hours: Forward prediction window (hours)
            start_epoch: Start of prediction window (default: now)

        Returns:
            PipelineResult with all assessment data
        """
        if start_epoch is None:
            start_epoch = datetime.utcnow()

        result = PipelineResult(
            catalog_size=len(objects),
            screening_window_hours=window_hours,
            run_start=start_epoch,
        )

        n = len(objects)
        result.total_pairs_checked = n * (n - 1) // 2

        logger.info(
            f"Pipeline start: {n} objects, {result.total_pairs_checked:,} pairs, "
            f"{window_hours}h window"
        )

        # Step 1: Screen
        candidates = self.screener.screen(objects, start_epoch)
        result.candidates = len(candidates)

        if not candidates:
            logger.info("No conjunction candidates found")
            result.run_end = datetime.utcnow()
            result.elapsed_seconds = (result.run_end - result.run_start).total_seconds()
            return result

        # Step 2: Build close approaches (TCA refinement + miss distance)
        # Parallelized: each candidate pair is independent
        logger.info(f"Building close approaches for {len(candidates)} candidates "
                     f"(max_workers={self.max_workers})")
        approaches = self._parallel_build_approaches(objects, candidates)
        result.close_approaches = approaches

        # Step 3: Compute Pc for each approach (parallelized)
        for approach in approaches:
            self.pc_calculator.calculate(approach)

        # Step 4: Classify alerts
        result.alerts = self.alert_classifier.classify(approaches, start_epoch)

        # Step 5: Generate CDMs for YELLOW and RED
        alerting_approaches = [a.approach for a in result.alerts]
        result.cdms = self.cdm_writer.write_many(alerting_approaches)

        # Step 6: Plan maneuvers for RED
        red_approaches = [
            a.approach for a in result.alerts if a.risk_level == RiskLevel.RED
        ]
        result.maneuver_plans = self.maneuver_planner.plan_batch(red_approaches, start_epoch)

        # Done
        result.run_end = datetime.utcnow()
        result.elapsed_seconds = (result.run_end - result.run_start).total_seconds()

        logger.info(f"Pipeline complete in {result.elapsed_seconds:.1f}s")
        logger.info(result.summary())

        return result

    def _parallel_build_approaches(
        self,
        objects: list[SpaceObject],
        candidates: list[tuple[int, int, datetime]],
    ) -> list[CloseApproach]:
        """Build close approaches with thread-parallel TCA refinement."""
        from aria.conjunction.conjunction.close_approach import build_close_approach

        if len(candidates) <= 4 or self.max_workers == 1:
            return build_close_approaches_batch(objects, candidates, self.tca_finder)

        approaches = []

        def _process_candidate(args):
            i, j, approx_tca = args
            return build_close_approach(
                objects[i], objects[j], approx_tca, self.tca_finder
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_process_candidate, c): c for c in candidates
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        approaches.append(result)
                except Exception as e:
                    logger.warning(f"TCA refinement failed: {e}")

        return approaches
