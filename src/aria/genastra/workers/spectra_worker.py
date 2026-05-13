"""Spectra analysis worker — Redis Streams consumer.

Consumes jobs from the ``spectra`` stream and runs:
  1. JWST MAST data fetch (via circuit breaker)
  2. Bayesian nested sampling (dynesty) — evidence integral Z per molecule
  3. Bayes factor computation with uncertainty (dynesty logzerr)
  4. Combinatorial biosignature scoring (O₂+CH₄ incompatibility boost)
  5. Thermodynamic disequilibrium metric (Gibbs free energy)
  6. Stores results to PostgreSQL

Redis stream: ``spectra:jobs``
Result stream: ``spectra:results``

Each job payload:
  {
    "job_id": "<uuid>",
    "tenant_id": "<uuid>",
    "observation_id": "<str>",          # MAST observation ID (e.g. "jw01366")
    "target_molecules": ["H2O", "CH4", "CO2", "O3", "N2O", "DMS"],
    "options": {
      "prior_type": "empirical",        # "empirical" | "uninformative" | "pessimistic"
      "prior_sensitivity": false,        # run all 3 prior types
      "n_live": 200,                    # dynesty live points
      "combinatorial": true             # compute joint Bayes factors
    }
  }
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from aria.genastra.workers.base import BaseWorker

logger = structlog.get_logger()

# Detection claim threshold: log10(K) > 3.2 required
DETECTION_THRESHOLD = 3.2


class SpectraWorker(BaseWorker):
    """Processes JWST spectral biosignature detection jobs from Redis Streams."""

    stream_name = "spectra:jobs"
    group_name = "spectra-workers"
    consumer_prefix = "spec-"

    async def process_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run full spectral biosignature pipeline for one observation.

        Args:
            job_id: Unique job identifier (UUID string).
            payload: Job parameters from Redis stream message.

        Returns:
            Result dict written back to ``spectra:results`` stream.
        """
        tenant_id = payload["tenant_id"]
        observation_id = payload["observation_id"]
        target_molecules = payload.get("target_molecules", ["H2O", "CH4", "CO2", "O3"])
        options = payload.get("options", {})
        prior_type = options.get("prior_type", "empirical")
        n_live = int(options.get("n_live", 200))
        run_combinatorial = options.get("combinatorial", True)

        log = logger.bind(
            job_id=job_id,
            tenant_id=tenant_id,
            observation_id=observation_id,
        )
        log.info("spectra_job_start", molecules=target_molecules)
        await self._update_status(job_id, "running", "Fetching JWST spectrum from MAST")

        # ── Step 1: Fetch JWST spectrum ───────────────────────────────────────
        from aria.genastra.spectra.mast_client import MastClient
        async with MastClient() as client:
            spectrum = await client.get_transmission_spectrum(observation_id)

        wavelengths_um = spectrum["wavelengths"]
        flux = spectrum["flux"]
        flux_err = spectrum["flux_err"]
        log.info("spectrum_fetched", n_points=len(wavelengths_um))

        # ── Step 2: Bayesian detection per molecule ───────────────────────────
        from aria.genastra.spectra.bayesian import detect_molecule

        results = []
        for mol in target_molecules:
            await self._update_status(
                job_id, "running",
                f"Bayesian nested sampling: {mol} ({target_molecules.index(mol)+1}/{len(target_molecules)})"
            )
            log.info("molecule_analysis_start", molecule=mol, prior=prior_type)

            try:
                result = detect_molecule(
                    wavelengths_um=wavelengths_um,
                    flux=flux,
                    flux_err=flux_err,
                    molecule=mol,
                    prior_type=prior_type,
                    n_live=n_live,
                )
                results.append(result)
                log.info(
                    "molecule_analysis_done",
                    molecule=mol,
                    log10_bf=result.log10_bayes_factor,
                    significance=result.significance.value,
                    reliable=result.significance_reliable,
                )
            except Exception as e:
                log.warning("molecule_analysis_failed", molecule=mol, error=str(e))

        # ── Step 3: Prior sensitivity (optional) ─────────────────────────────
        sensitivity_results: dict[str, Any] = {}
        if options.get("prior_sensitivity", False):
            await self._update_status(job_id, "running", "Running prior sensitivity analysis")
            from aria.genastra.spectra.bayesian import detect_molecule

            for prior in ["empirical", "uninformative", "pessimistic"]:
                if prior == prior_type:
                    continue
                prior_results = []
                for mol in target_molecules:
                    try:
                        r = detect_molecule(wavelengths_um, flux, flux_err, mol,
                                            prior_type=prior, n_live=max(n_live // 2, 50))
                        prior_results.append({
                            "molecule": mol,
                            "log10_bf": r.log10_bayes_factor,
                            "significance": r.significance.value,
                        })
                    except Exception:  # noqa: S110, BLE001
                        pass
                sensitivity_results[prior] = prior_results

        # ── Step 4: Combinatorial biosignature scoring ────────────────────────
        combo: dict[str, Any] = {}
        if run_combinatorial and len(results) >= 2:
            await self._update_status(job_id, "running", "Computing combinatorial biosignature score")
            from aria.genastra.spectra.bayesian import compute_combinatorial_biosignature

            # Include thermodynamic disequilibrium context
            # Estimate rough mixing ratios from posterior abundances
            diseq_ratios = {
                r.molecule: float(r.posterior_abundance)
                for r in results
                if r.posterior_abundance is not None
            }
            combo = compute_combinatorial_biosignature(
                results,
                temperature_k=280.0,      # fiducial exoplanet temperature
                mixing_ratios=diseq_ratios if len(diseq_ratios) >= 2 else None,
            )
            log.info(
                "combinatorial_done",
                n_pairs=len(combo.get("incompatible_pairs", [])),
                overall=combo.get("overall_assessment", ""),
            )

        # ── Step 5: Compile result ────────────────────────────────────────────
        detections = [
            {
                "molecule": r.molecule,
                "log10_bayes_factor": r.log10_bayes_factor,
                "log10_bayes_factor_err": r.log10_bayes_factor_err,
                "significance": r.significance.value,
                "significance_reliable": r.significance_reliable,
                "posterior_abundance": r.posterior_abundance,
                "abundance_ci": [r.abundance_ci_lower, r.abundance_ci_upper],
                "false_positive_prob": r.false_positive_prob,
                "mutual_information_bits": r.mutual_information_bits,
                "claimed": r.log10_bayes_factor >= DETECTION_THRESHOLD and r.significance_reliable,
            }
            for r in results
        ]

        n_claimed = sum(1 for d in detections if d["claimed"])
        log.info("spectra_job_done", n_detections_claimed=n_claimed)

        return {
            "job_id": job_id,
            "observation_id": observation_id,
            "n_molecules_tested": len(target_molecules),
            "n_claimed_detections": n_claimed,
            "detections": detections,
            "combinatorial": combo,
            "prior_sensitivity": sensitivity_results,
            "prior_used": prior_type,
            "disclaimer": (
                "Detection claims require log10(K) > 3.2 AND significance_reliable=True. "
                "Prior sensitivity analysis recommended for any claimed detection."
            ),
        }


async def main() -> None:
    """Entry point for standalone worker process."""
    worker = SpectraWorker()
    logger.info("spectra_worker_starting")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
