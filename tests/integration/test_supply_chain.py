from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aria.security.supply_chain.creds_scan import (
    DEFAULT_PATTERNS,
    Pattern,
    format_creds_report_human,
    scan_files,
    scan_text,
)
from aria.security.supply_chain.sbom import (
    SbomBuildError,
    generate_cyclonedx_sbom,
    summarise_sbom,
)
from aria.security.supply_chain.vuln_gate import (
    PipAuditError,
    VulnReport,
    Vulnerability,
    format_vuln_report_human,
    parse_pip_audit_output,
    run_pip_audit,
)


class TestSbom:
    def test_missing_binary(self, tmp_path: Path):
        with patch(
            "aria.security.supply_chain.sbom.shutil.which", return_value=None,
        ):
            with pytest.raises(SbomBuildError, match="not on PATH"):
                generate_cyclonedx_sbom(output_path=tmp_path / "out.json")

    def test_summarise_missing_file(self, tmp_path: Path):
        with pytest.raises(SbomBuildError, match="not found"):
            summarise_sbom(tmp_path / "nope.json")

    def test_summarise_basic(self, tmp_path: Path):
        sbom = tmp_path / "sbom.json"
        sbom.write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "components": [
                {"name": "numpy", "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
                {"name": "scipy", "licenses": [{"license": {"id": "BSD-3-Clause"}}]},
                {"name": "anthropic"},
            ],
        }))
        summary = summarise_sbom(sbom)
        assert summary["n_components"] == 3
        assert summary["by_license"]["BSD-3-Clause"] == 2
        assert summary["by_license"]["UNKNOWN"] == 1


class TestVulnGate:
    def test_parse_clean_report(self):
        payload = {"dependencies": [
            {"name": "numpy", "version": "1.26.0", "vulns": []},
            {"name": "scipy", "version": "1.12.0", "vulns": []},
        ]}
        report = parse_pip_audit_output(payload)
        assert report.n_total == 0
        assert report.n_dependencies_scanned == 2

    def test_parse_with_vulns(self):
        payload = {"dependencies": [
            {
                "name": "requests",
                "version": "2.20.0",
                "vulns": [
                    {
                        "id": "GHSA-x84v-xcm2-53pg",
                        "aliases": ["CVE-2018-18074"],
                        "description": "Critical RCE in requests library",
                        "fix_versions": ["2.20.1"],
                    },
                    {
                        "id": "PYSEC-2023-1",
                        "aliases": ["CVE-2023-9999"],
                        "description": "Denial of service via malformed header",
                        "fix_versions": [],
                    },
                ],
            },
        ]}
        report = parse_pip_audit_output(payload)
        assert report.n_total == 2
        severities = {vuln.severity for vuln in report.vulnerabilities}
        assert "CRITICAL" in severities
        assert "MEDIUM" in severities

    def test_filter_severity(self):
        payload = {"dependencies": [
            {"name": "x", "version": "1", "vulns": [
                {"id": "A", "description": "CRITICAL flaw", "aliases": [],
                 "fix_versions": []},
                {"id": "B", "description": "low impact", "aliases": [],
                 "fix_versions": []},
            ]},
        ]}
        report = parse_pip_audit_output(payload)
        assert len(report.filter_severity({"CRITICAL"})) == 1
        assert len(report.filter_severity({"LOW"})) == 1

    def test_skipped_recorded(self):
        payload = {"dependencies": [
            {"name": "private-pkg", "skip_reason": "dependency not found on PyPI"},
            {"name": "numpy", "version": "1.26.0", "vulns": []},
        ]}
        report = parse_pip_audit_output(payload)
        assert len(report.skipped) == 1
        assert report.n_dependencies_scanned == 2

    def test_run_missing_binary(self):
        with patch(
            "aria.security.supply_chain.vuln_gate.shutil.which", return_value=None,
        ):
            with pytest.raises(PipAuditError, match="not on PATH"):
                run_pip_audit()

    def test_run_returns_clean_when_stdout_empty(self):
        with patch(
            "aria.security.supply_chain.vuln_gate.shutil.which",
            return_value="/fake/pip-audit",
        ), patch(
            "aria.security.supply_chain.vuln_gate.subprocess.run",
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr="",
            )
            report = run_pip_audit()
            assert report.n_total == 0

    def test_run_propagates_exit_other_than_0_or_1(self):
        with patch(
            "aria.security.supply_chain.vuln_gate.shutil.which",
            return_value="/fake/pip-audit",
        ), patch(
            "aria.security.supply_chain.vuln_gate.subprocess.run",
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=2, stdout="", stderr="boom",
            )
            with pytest.raises(PipAuditError, match="exit 2"):
                run_pip_audit()

    def test_format_human_clean(self):
        report = VulnReport()
        text = format_vuln_report_human(report)
        assert "clean" in text

    def test_format_human_with_findings(self):
        vuln = Vulnerability(
            package="requests", installed_version="2.20.0",
            vuln_id="GHSA-x", aliases=("CVE-2018-1",),
            fix_versions=("2.20.1",), description="rce",
            severity="CRITICAL",
        )
        report = VulnReport(
            vulnerabilities=(vuln,), n_dependencies_scanned=42,
        )
        text = format_vuln_report_human(report)
        assert "CRITICAL" in text
        assert "requests" in text
        assert "2.20.1" in text


class TestCredsScan:
    def test_aws_access_key_detected(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
        findings = scan_text(file_path="config.env", text=text)
        names = {finding.pattern_name for finding in findings}
        assert "aws-access-key-id" in names
        finding = next(f for f in findings if f.pattern_name == "aws-access-key-id")
        assert finding.severity == "CRITICAL"
        assert "AKIA" in finding.matched_text
        assert "***" in finding.redacted_excerpt()

    def test_github_pat_detected(self):
        text = "TOKEN=ghp_" + ("a" * 36) + "\n"
        findings = scan_text(file_path="x.txt", text=text)
        assert any(f.pattern_name == "github-pat" for f in findings)

    def test_google_api_key_detected(self):
        text = 'GEMINI_API_KEY=AIza' + 'a' * 35 + '\n'
        findings = scan_text(file_path="x.txt", text=text)
        assert any(f.pattern_name == "google-api-key" for f in findings)

    def test_anthropic_key_detected(self):
        text = "key = 'sk-ant-" + "a" * 50 + "'\n"
        findings = scan_text(file_path="x.txt", text=text)
        assert any(f.pattern_name == "anthropic-api-key" for f in findings)

    def test_ssh_private_key_block_detected(self):
        text = "-----BEGIN OPENSSH PRIVATE KEY-----\nblob\n"
        findings = scan_text(file_path="id_rsa", text=text)
        assert any(f.pattern_name == "ssh-private-key-block" for f in findings)

    def test_jwt_detected(self):
        jwt = "eyJabc123abc456.eyJabc123abcXYZ456.signature123abcDEF"
        findings = scan_text(file_path="x.txt", text=jwt, detect_entropy=False)
        assert any(f.pattern_name == "jwt-token" for f in findings)

    def test_clean_text_no_findings(self):
        findings = scan_text(
            file_path="x.txt",
            text="def f():\n    return 42\nprint('hello world')\n",
        )
        assert findings == ()

    def test_high_entropy_optional(self):
        text = "secret = 'abcDEF123_-/+0123456789xyzABCDEFG'\n"
        findings_with = scan_text(file_path="x.txt", text=text)
        findings_without = scan_text(
            file_path="x.txt", text=text, detect_entropy=False,
        )
        assert any(
            finding.pattern_name == "high-entropy-string"
            for finding in findings_with
        ) or any(
            finding.pattern_name in ("generic-bearer-header",)
            for finding in findings_with
        )
        names_without = {finding.pattern_name for finding in findings_without}
        assert "high-entropy-string" not in names_without

    def test_redacted_excerpt_redacts_match(self):
        text = "API_KEY=AKIAIOSFODNN7EXAMPLE\n"
        findings = scan_text(file_path="x.txt", text=text)
        finding = next(f for f in findings if f.pattern_name == "aws-access-key-id")
        excerpt = finding.redacted_excerpt()
        assert "AKIAIOSFODNN7EXAMPLE" not in excerpt
        assert "***" in excerpt

    def test_scan_files_skips_binaries(self, tmp_path: Path):
        binary = tmp_path / "blob.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        plain = tmp_path / "leaks.env"
        plain.write_text("AWS=AKIAIOSFODNN7EXAMPLE\n")
        report = scan_files([tmp_path])
        assert report.files_scanned == 1
        assert report.n_findings >= 1

    def test_scan_files_skips_oversized(self, tmp_path: Path):
        big = tmp_path / "huge.txt"
        big.write_text("x" * 5000)
        report = scan_files([tmp_path], max_bytes=1000)
        assert report.files_scanned == 0
        assert any("too large" in entry for entry in report.skipped)

    def test_scan_files_recursive(self, tmp_path: Path):
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "f.env").write_text("PAT=ghp_" + "a" * 36 + "\n")
        (tmp_path / "g.env").write_text("OK=clean\n")
        report = scan_files([tmp_path])
        assert report.files_scanned == 2
        assert any(
            finding.pattern_name == "github-pat"
            for finding in report.findings
        )

    def test_skip_dirs_excluded(self, tmp_path: Path):
        ignored = tmp_path / "node_modules"
        ignored.mkdir()
        (ignored / "leak.env").write_text("AKIAIOSFODNN7EXAMPLE\n")
        included = tmp_path / "src"
        included.mkdir()
        (included / "ok.txt").write_text("hello world\n")
        report = scan_files([tmp_path])
        assert all("node_modules" not in finding.file_path for finding in report.findings)

    def test_format_human_clean(self):
        report = scan_files([Path(".")], patterns=())
        text = format_creds_report_human(report)
        assert "no leaks" in text or "Findings:" in text

    def test_custom_pattern(self):
        custom = Pattern(
            name="my-token", regex=re.compile(r"\bMYAPP_[A-Z0-9]{10}\b"),
            severity="HIGH",
        )
        findings = scan_text(
            file_path="x.txt", text="x = MYAPP_ABCDEF1234\n",
            patterns=(custom,), detect_entropy=False,
        )
        assert len(findings) == 1
        assert findings[0].pattern_name == "my-token"


class TestRedactionPreservesUtility:
    def test_short_token_collapsed(self):
        from aria.security.supply_chain.creds_scan import _redact
        assert _redact("abc") == "***"

    def test_long_token_partially_revealed(self):
        from aria.security.supply_chain.creds_scan import _redact
        result = _redact("AKIAIOSFODNN7EXAMPLE")
        assert "AKIA" in result
        assert "PLE" in result
        assert "IOSFODNN" not in result
