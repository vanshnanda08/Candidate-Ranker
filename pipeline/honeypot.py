"""
Detects honeypot candidates — profiles with subtly impossible or
inconsistent data. Ranking too many (>10 in top 100) = disqualification.
"""

from datetime import date, datetime


def _parse_year(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


RULE_MESSAGES = {
    "impossible_experience": "Impossible years of experience vs graduation year",
    "assessment_proficiency_mismatch": "Multiple expert skill claims with assessment scores below 25/100",
    "assessment_proficiency_mismatch_mild": "Expert skill claim with an assessment score below 25/100",
    "unverified_complete_profile": "Profile >90% complete but email, phone and LinkedIn are unverified",
    "multiple_overlapping_jobs": "Three or more overlaps between consecutive career records",
    "endorsement_connection_mismatch": "More than 500 endorsements with fewer than 10 connections",
    "future_start_date": "Career start date is after the scoring date",
    "future_graduation": "Graduation year is more than one year after the scoring year",
    "inverted_education_dates": "Graduation year is before the education start year",
}


def evaluate_honeypot(candidate: dict, as_of: date | None = None) -> tuple[float, list[str]]:
    """
    Evaluate each penalty rule once and return its multiplier and readable flags.
    Callers may omit as_of to retain the local-date default.
    """
    today = as_of if as_of is not None else date.today()
    flags = []
    profile = candidate["profile"]
    career = candidate.get("career_history", [])
    edu = candidate.get("education", [])
    signals = candidate["redrob_signals"]
    skills = candidate.get("skills", [])

    current_year = today.year

    # --- Check 1: Experience vs graduation year ---
    if edu:
        latest_grad = max(
            (_parse_year(e.get("end_year")) or 0) for e in edu
        )
        if latest_grad > 0:
            max_possible_yoe = current_year - latest_grad
            claimed_yoe = profile.get("years_of_experience", 0)
            if claimed_yoe > max_possible_yoe + 2:
                flags.append(("impossible_experience", 0.05))

    # --- Check 2: Skill proficiency vs assessment score mismatch ---
    assessment_scores = signals.get("skill_assessment_scores", {})
    expert_skills = [s["name"] for s in skills if s["proficiency"] == "expert"]
    mismatches = 0
    for skill_name in expert_skills:
        for assessed_name, score in assessment_scores.items():
            if skill_name.lower() in assessed_name.lower() or assessed_name.lower() in skill_name.lower():
                if score < 25:  # claims expert, scored below 25/100
                    mismatches += 1
    if mismatches >= 2:
        flags.append(("assessment_proficiency_mismatch", 0.3))
    elif mismatches == 1:
        flags.append(("assessment_proficiency_mismatch_mild", 0.7))

    # --- Check 3: Very high completeness but nothing verified ---
    completeness = signals.get("profile_completeness_score", 0)
    verified_email = signals.get("verified_email", False)
    verified_phone = signals.get("verified_phone", False)
    linkedin = signals.get("linkedin_connected", False)
    if completeness > 90 and not verified_email and not verified_phone and not linkedin:
        flags.append(("unverified_complete_profile", 0.4))

    # --- Check 4: Overlapping career dates ---
    date_ranges = []
    for job in career:
        try:
            start = datetime.strptime(job["start_date"], "%Y-%m-%d").date()
            end_str = job.get("end_date")
            end = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else today
            date_ranges.append((start, end))
        except (ValueError, TypeError):
            continue

    date_ranges.sort()
    overlap_count = 0
    for i in range(len(date_ranges) - 1):
        if date_ranges[i][1] > date_ranges[i + 1][0]:
            overlap_count += 1
    if overlap_count >= 3:
        flags.append(("multiple_overlapping_jobs", 0.3))

    # --- Check 5: Implausibly high endorsements with zero connections ---
    endorsements = signals.get("endorsements_received", 0)
    connections = signals.get("connection_count", 0)
    if endorsements > 500 and connections < 10:
        flags.append(("endorsement_connection_mismatch", 0.3))

    # --- Check 6: Career history dates in the future ---
    for job in career:
        try:
            start = datetime.strptime(job["start_date"], "%Y-%m-%d").date()
            if start > today:
                flags.append(("future_start_date", 0.1))
                break
        except (ValueError, TypeError):
            continue

    # --- Check 7: Impossible graduation year ---
    for e in edu:
        grad_year = _parse_year(e.get("end_year"))
        start_year = _parse_year(e.get("start_year"))
        if grad_year and grad_year > current_year + 1:
            flags.append(("future_graduation", 0.2))
            break
        if start_year and grad_year and grad_year < start_year:
            flags.append(("inverted_education_dates", 0.2))
            break

    # --- Apply penalties multiplicatively ---
    penalty = 1.0
    for flag_name, multiplier in flags:
        penalty *= multiplier

    return max(penalty, 0.01), [RULE_MESSAGES[name] for name, _ in flags]


def honeypot_penalty(candidate: dict, as_of: date | None = None) -> float:
    """Compatibility wrapper for the Streamlit prototype and existing callers."""
    return evaluate_honeypot(candidate, as_of)[0]


def is_honeypot(candidate: dict, threshold: float = 0.2, as_of: date | None = None) -> bool:
    return honeypot_penalty(candidate, as_of) < threshold


def honeypot_flags(candidate: dict, as_of: date | None = None) -> list[str]:
    """Readable explanations from the same evaluation used for penalties."""
    return evaluate_honeypot(candidate, as_of)[1]
