"""Job Application Tracker - the main Flask app.

Every page in the app is set up in this file:
    /                Dashboard (statistics overview)
"""

import json
import os
import re
from datetime import date, datetime

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from database import execute, query_all, query_one

app = Flask(__name__)
# Flask needs a secret key to show flash messages (the green "saved" banners).
# This one is fine for running locally; set SECRET_KEY if the app ever goes online.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-key")

JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]
INTERVIEW_TYPES = ["Phone", "Video", "Technical", "On-site", "Other"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Helpers that all the add/edit forms share
# ---------------------------------------------------------------------------

def clean(form, field):
    """Grab a form field, trim the spaces, and turn an empty box into None."""
    value = form.get(field, "").strip()
    return value or None


def check_length(errors, label, value, max_length):
    """Catch text that's too long for its database column before MySQL does."""
    if value and len(value) > max_length:
        errors.append(f"{label} must be {max_length} characters or fewer.")


def check_url(errors, label, value):
    """Links have to start with http:// or https:// so they actually open."""
    if value and not value.lower().startswith(("http://", "https://")):
        errors.append(f"{label} must start with http:// or https://.")


def parse_date(errors, label, value, required=False):
    """Turn '2026-11-01' into a real date. A bad (or missing required) date adds an error."""
    if not value:
        if required:
            errors.append(f"{label} is required.")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{label} must be a valid date (YYYY-MM-DD).")
        return None


def parse_salary(errors, label, value):
    """Salaries are whole numbers only: no $ signs, commas or decimals."""
    if not value:
        return None
    if not value.isdigit():
        errors.append(f"{label} must be a whole number with no symbols or commas.")
        return None
    return int(value)


def parse_json(value, default):
    """MySQL can hand JSON columns back as text or bytes, so normalize them here."""
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value


def parse_skills(text):
    """Turn 'Python, SQL,  flask' into ['Python', 'SQL', 'flask'].

    Empty pieces and repeats are skipped, so 'python, Python' only counts once.
    """
    skills = []
    seen = set()
    for piece in (text or "").split(","):
        skill = " ".join(piece.split())  # 'REST   APIs' becomes 'REST APIs'
        if skill and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(skill)
    return skills


def job_skills(job):
    """Pull the list of skills out of a job's requirements column."""
    requirements = parse_json(job.get("requirements"), [])
    if isinstance(requirements, dict):  # in case it was saved as {"skills": [...]}
        requirements = requirements.get("skills", [])
    if not isinstance(requirements, list):
        return []
    return [str(skill) for skill in requirements]


def company_exists(company_id):
    return query_one("SELECT company_id FROM companies WHERE company_id = %s",
                     (company_id,)) is not None


def get_or_404(sql, record_id):
    """Look up one row by id, or show the "not found" page if it's gone."""
    row = query_one(sql, (record_id,))
    if row is None:
        abort(404)
    return row


def company_choices():
    return query_all("SELECT company_id, company_name FROM companies ORDER BY company_name")


def job_choices():
    return query_all(
        """SELECT j.job_id, j.job_title, c.company_name
           FROM jobs j JOIN companies c ON c.company_id = j.company_id
           ORDER BY c.company_name, j.job_title"""
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    counts = query_one(
        """SELECT (SELECT COUNT(*) FROM companies)    AS companies,
                  (SELECT COUNT(*) FROM jobs)         AS jobs,
                  (SELECT COUNT(*) FROM applications) AS applications,
                  (SELECT COUNT(*) FROM contacts)     AS contacts"""
    )
    return render_template("dashboard.html", counts=counts)


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", title="Page not found",
                           message="That page or record does not exist. It may have been deleted."), 404


@app.errorhandler(mysql.connector.Error)
def database_error(error):
    app.logger.error("Database error: %s", error)
    return render_template(
        "error.html", title="Database problem",
        message="The app could not reach the database. Check that MySQL is running, that "
                "schema.sql has been loaded, and that DB_USER / DB_PASSWORD are set correctly."), 500


if __name__ == "__main__":
    app.run(debug=True)
