"""
FlowFix — Step 2 Analysis

Public interface.

Usage
-----
from flowfix.step1_intake import run_intake
from flowfix.step2_analysis import run_analysis

intake_result = run_intake(error_text="422 Unprocessable Entity", blueprint_text=...)
analysis_result = run_analysis(intake_result.normalized_problem)

analysis_result.analysis          # WorkflowAnalysis — pass to Step 3
analysis_result.validation         # Step2ValidationResult
analysis_result.ready_for_step3    # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step2_analysis.analyzer.analyzer import analyze
from flowfix.step2_analysis.validation.validator import validate, Step2ValidationResult


@dataclass
class AnalysisResult:
    analysis: WorkflowAnalysis
    validation: Step2ValidationResult

    @property
    def ready_for_step3(self) -> bool:
        return self.validation.valid


def run_analysis(problem: NormalizedProblem) -> AnalysisResult:
    """
    Run Step 2 analysis pipeline.

    Parameters
    ----------
    problem : NormalizedProblem
        Output of Step 1 run_intake().

    Returns
    -------
    AnalysisResult
        Contains WorkflowAnalysis and validation status.
    """
    analysis = analyze(problem)
    validation = validate(analysis)
    return AnalysisResult(analysis=analysis, validation=validation)
