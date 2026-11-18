import json
import os
import re
from datetime import date, datetime

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from database import execute, query_all, query_one

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-key")

JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]
INTERVIEW_TYPES = ["Phone", "Video", "Technical", "On-site", "Other"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean(form, field):
    value = form.get(field, "").strip()
    return value or None


def check_length(errors, label, value, max_length):
    if value and len(value) > max_length:
        errors.append(f"{label} must be {max_length} characters or fewer.")


def check_url(errors, label, value):
    if value and not value.lower().startswith(("http://", "https://")):
        errors.append(f"{label} must start with http:// or https://.")


def parse_date(errors, label, value, required=False):
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
    if not value:
        return None
    if not value.isdigit():
        errors.append(f"{label} must be a whole number with no symbols or commas.")
        return None
    return int(value)


def parse_json(value, default):
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
    skills = []
    seen = set()
    for piece in (text or "").split(","):
        skill = " ".join(piece.split())
        if skill and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(skill)
    return skills


def job_skills(job):
    requirements = parse_json(job.get("requirements"), [])
    if isinstance(requirements, dict):
        requirements = requirements.get("skills", [])
    if not isinstance(requirements, list):
        return []
    return [str(skill) for skill in requirements]


def company_exists(company_id):
    return query_one("SELECT company_id FROM companies WHERE company_id = %s",
                     (company_id,)) is not None


def get_or_404(sql, record_id):
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


@app.route("/")
def dashboard():
    counts = query_one(
        """SELECT (SELECT COUNT(*) FROM companies)    AS companies,
                  (SELECT COUNT(*) FROM jobs)         AS jobs,
                  (SELECT COUNT(*) FROM applications) AS applications,
                  (SELECT COUNT(*) FROM contacts)     AS contacts"""
    )

    status_counts = {status: 0 for status in STATUSES}
    for row in query_all("SELECT status, COUNT(*) AS total FROM applications GROUP BY status"):
        status_counts[row["status"]] = row["total"]

    total = counts["applications"]
    responded = total - status_counts["Applied"]
    stats = {
        "active": status_counts["Applied"] + status_counts["Screening"] + status_counts["Interview"],
        "offers": status_counts["Offer"],
        "response_rate": round(responded / total * 100) if total else 0,
    }

    recent = query_all(
        """SELECT a.application_id, a.application_date, a.status,
                  j.job_title, c.company_name
           FROM applications a
           JOIN jobs j      ON j.job_id = a.job_id
           JOIN companies c ON c.company_id = j.company_id
           ORDER BY a.application_date DESC, a.application_id DESC
           LIMIT 5"""
    )

    return render_template("dashboard.html", counts=counts, stats=stats,
                           status_counts=status_counts, recent=recent)


def validate_company(form):
    errors = []
    data = {field: clean(form, field)
            for field in ("company_name", "industry", "website", "city", "state", "notes")}

    if not data["company_name"]:
        errors.append("Company name is required.")
    check_length(errors, "Company name", data["company_name"], 100)
    check_length(errors, "Industry", data["industry"], 50)
    check_length(errors, "Website", data["website"], 200)
    check_length(errors, "City", data["city"], 50)
    check_length(errors, "State", data["state"], 50)
    check_url(errors, "Website", data["website"])
    return data, errors


@app.route("/companies")
def companies():
    rows = query_all(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM jobs j     WHERE j.company_id = c.company_id) AS job_count,
                  (SELECT COUNT(*) FROM contacts t WHERE t.company_id = c.company_id) AS contact_count
           FROM companies c
           ORDER BY c.company_name"""
    )
    return render_template("companies.html", companies=rows)


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    company = get_or_404("SELECT * FROM companies WHERE company_id = %s", company_id)
    jobs_here = query_all(
        "SELECT * FROM jobs WHERE company_id = %s ORDER BY date_posted DESC", (company_id,))
    contacts_here = query_all(
        "SELECT * FROM contacts WHERE company_id = %s ORDER BY contact_name", (company_id,))
    return render_template("company_detail.html", company=company,
                           jobs=jobs_here, contacts=contacts_here)


@app.route("/companies/add", methods=["GET", "POST"])
def company_add():
    if request.method == "POST":
        data, errors = validate_company(request.form)
        if not errors:
            execute(
                """INSERT INTO companies (company_name, industry, website, city, state, notes)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (data["company_name"], data["industry"], data["website"],
                 data["city"], data["state"], data["notes"]),
            )
            flash(f"Company \"{data['company_name']}\" added.", "success")
            return redirect(url_for("companies"))
        return render_template("company_form.html", form=request.form, errors=errors, company=None)
    return render_template("company_form.html", form={}, errors=[], company=None)


@app.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
def company_edit(company_id):
    company = get_or_404("SELECT * FROM companies WHERE company_id = %s", company_id)
    if request.method == "POST":
        data, errors = validate_company(request.form)
        if not errors:
            execute(
                """UPDATE companies
                   SET company_name = %s, industry = %s, website = %s,
                       city = %s, state = %s, notes = %s
                   WHERE company_id = %s""",
                (data["company_name"], data["industry"], data["website"],
                 data["city"], data["state"], data["notes"], company_id),
            )
            flash(f"Company \"{data['company_name']}\" updated.", "success")
            return redirect(url_for("company_detail", company_id=company_id))
        return render_template("company_form.html", form=request.form, errors=errors, company=company)
    return render_template("company_form.html", form=company, errors=[], company=company)


@app.route("/companies/<int:company_id>/delete", methods=["POST"])
def company_delete(company_id):
    company = get_or_404("SELECT * FROM companies WHERE company_id = %s", company_id)
    execute("DELETE FROM companies WHERE company_id = %s", (company_id,))
    flash(f"Company \"{company['company_name']}\" deleted.", "success")
    return redirect(url_for("companies"))


JOB_SELECT = """SELECT j.*, c.company_name
                FROM jobs j JOIN companies c ON c.company_id = j.company_id"""


def validate_job(form, need_company=True):
    errors = []
    data = {
        "job_title": clean(form, "job_title"),
        "job_type": clean(form, "job_type"),
        "job_url": clean(form, "job_url"),
    }

    company_id = clean(form, "company_id")
    if not need_company:
        data["company_id"] = None
    elif not company_id or not company_id.isdigit() or not company_exists(int(company_id)):
        errors.append("Please choose a company.")
        data["company_id"] = None
    else:
        data["company_id"] = int(company_id)

    if not data["job_title"]:
        errors.append("Job title is required.")
    check_length(errors, "Job title", data["job_title"], 100)

    if data["job_type"] and data["job_type"] not in JOB_TYPES:
        errors.append("Job type is not one of the allowed options.")

    data["salary_min"] = parse_salary(errors, "Minimum salary", clean(form, "salary_min"))
    data["salary_max"] = parse_salary(errors, "Maximum salary", clean(form, "salary_max"))
    if (data["salary_min"] is not None and data["salary_max"] is not None
            and data["salary_min"] > data["salary_max"]):
        errors.append("Minimum salary cannot be greater than maximum salary.")

    check_length(errors, "Job URL", data["job_url"], 300)
    check_url(errors, "Job URL", data["job_url"])
    data["date_posted"] = parse_date(errors, "Date posted", clean(form, "date_posted"))

    skills = parse_skills(form.get("requirements_text"))
    data["requirements"] = json.dumps(skills) if skills else None
    return data, errors


@app.route("/jobs")
def jobs():
    rows = query_all(JOB_SELECT + " ORDER BY j.date_posted DESC, j.job_id DESC")
    for job in rows:
        job["skills"] = job_skills(job)
    return render_template("jobs.html", jobs=rows)


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = get_or_404(JOB_SELECT + " WHERE j.job_id = %s", job_id)
    job["skills"] = job_skills(job)
    job_applications = query_all(
        "SELECT * FROM applications WHERE job_id = %s ORDER BY application_date DESC", (job_id,))
    return render_template("job_detail.html", job=job, applications=job_applications)


@app.route("/jobs/add", methods=["GET", "POST"])
def job_add():
    if request.method == "POST":
        data, errors = validate_job(request.form)
        if not errors:
            execute(
                """INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max,
                                     job_url, date_posted, requirements)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (data["company_id"], data["job_title"], data["job_type"], data["salary_min"],
                 data["salary_max"], data["job_url"], data["date_posted"], data["requirements"]),
            )
            flash(f"Job \"{data['job_title']}\" added.", "success")
            return redirect(url_for("jobs"))
        form = request.form
    else:
        form = {"company_id": request.args.get("company_id", "")}
        errors = []
    return render_template("job_form.html", form=form, errors=errors, job=None,
                           companies=company_choices(), job_types=JOB_TYPES)


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def job_edit(job_id):
    job = get_or_404(JOB_SELECT + " WHERE j.job_id = %s", job_id)
    if request.method == "POST":
        data, errors = validate_job(request.form)
        if not errors:
            execute(
                """UPDATE jobs
                   SET company_id = %s, job_title = %s, job_type = %s, salary_min = %s,
                       salary_max = %s, job_url = %s, date_posted = %s, requirements = %s
                   WHERE job_id = %s""",
                (data["company_id"], data["job_title"], data["job_type"], data["salary_min"],
                 data["salary_max"], data["job_url"], data["date_posted"], data["requirements"],
                 job_id),
            )
            flash(f"Job \"{data['job_title']}\" updated.", "success")
            return redirect(url_for("job_detail", job_id=job_id))
        form = request.form
    else:
        form = dict(job)
        form["requirements_text"] = ", ".join(job_skills(job))
        errors = []
    return render_template("job_form.html", form=form, errors=errors, job=job,
                           companies=company_choices(), job_types=JOB_TYPES)


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def job_delete(job_id):
    job = get_or_404(JOB_SELECT + " WHERE j.job_id = %s", job_id)
    execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
    flash(f"Job \"{job['job_title']}\" deleted.", "success")
    return redirect(url_for("jobs"))


APPLICATION_SELECT = """SELECT a.*, j.job_title, c.company_id, c.company_name
                        FROM applications a
                        JOIN jobs j      ON j.job_id = a.job_id
                        JOIN companies c ON c.company_id = j.company_id"""


def validate_application(form, need_job=True):
    errors = []
    data = {
        "status": clean(form, "status"),
        "resume_version": clean(form, "resume_version"),
        "cover_letter_sent": 1 if form.get("cover_letter_sent") else 0,
    }

    job_id = clean(form, "job_id")
    job_found = job_id and job_id.isdigit() and query_one(
        "SELECT job_id FROM jobs WHERE job_id = %s", (int(job_id),))
    if not need_job:
        data["job_id"] = None
    elif not job_found:
        errors.append("Please choose a job.")
        data["job_id"] = None
    else:
        data["job_id"] = int(job_id)

    data["application_date"] = parse_date(
        errors, "Application date", clean(form, "application_date"), required=True)
    if data["application_date"] and data["application_date"] > date.today():
        errors.append("Application date cannot be in the future.")

    if data["status"] not in STATUSES:
        errors.append("Please choose a status.")
    check_length(errors, "Resume version", data["resume_version"], 50)

    interview = {}
    interview_date = parse_date(errors, "Interview date", clean(form, "interview_date"))
    if interview_date:
        interview["date"] = interview_date.isoformat()
    interview_type = clean(form, "interview_type")
    if interview_type:
        if interview_type in INTERVIEW_TYPES:
            interview["type"] = interview_type
        else:
            errors.append("Interview type is not one of the allowed options.")
    for key, field in (("interviewer", "interviewer"), ("notes", "interview_notes")):
        value = clean(form, field)
        if value:
            interview[key] = value
    data["interview_data"] = json.dumps(interview) if interview else None
    return data, errors


def application_form_values(application):
    form = dict(application)
    interview = parse_json(application.get("interview_data"), {})
    if not isinstance(interview, dict):
        interview = {}
    form["interview_date"] = interview.get("date", "")
    form["interview_type"] = interview.get("type", "")
    form["interviewer"] = interview.get("interviewer", "")
    form["interview_notes"] = interview.get("notes", "")
    return form


@app.route("/applications")
def applications():
    status_filter = request.args.get("status", "")
    sql = APPLICATION_SELECT
    params = ()
    if status_filter in STATUSES:
        sql += " WHERE a.status = %s"
        params = (status_filter,)
    rows = query_all(sql + " ORDER BY a.application_date DESC, a.application_id DESC", params)
    return render_template("applications.html", applications=rows,
                           statuses=STATUSES, status_filter=status_filter)


@app.route("/applications/<int:application_id>")
def application_detail(application_id):
    application = get_or_404(APPLICATION_SELECT + " WHERE a.application_id = %s", application_id)
    interview = parse_json(application.get("interview_data"), {})
    if not isinstance(interview, dict):
        interview = {}
    return render_template("application_detail.html", application=application, interview=interview)


def find_or_create_company(data):
    existing = query_one(
        "SELECT company_id FROM companies WHERE LOWER(company_name) = LOWER(%s)",
        (data["company_name"],))
    if existing:
        return existing["company_id"]
    return execute(
        """INSERT INTO companies (company_name, industry, website, city, state, notes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (data["company_name"], data["industry"], data["website"],
         data["city"], data["state"], data["notes"]),
    )


def contact_fields(form):
    return {
        "contact_name": form.get("contact_name", ""),
        "title": form.get("contact_title", ""),
        "email": form.get("contact_email", ""),
        "phone": form.get("contact_phone", ""),
        "linkedin_url": form.get("contact_linkedin_url", ""),
        "notes": form.get("contact_notes", ""),
    }


@app.route("/applications/add", methods=["GET", "POST"])
def application_add():
    job_id = request.values.get("job_id", "")
    existing_job = None
    if job_id.isdigit():
        existing_job = query_one(JOB_SELECT + " WHERE j.job_id = %s", (int(job_id),))

    if request.method == "POST":
        include_contact = request.form.get("include_contact") == "1"
        app_data, errors = validate_application(request.form, need_job=existing_job is not None)
        if existing_job is None:
            company_data, company_errors = validate_company(request.form)
            job_data, job_errors = validate_job(request.form, need_company=False)
            errors = company_errors + job_errors + errors
        if include_contact:
            contact_data, contact_errors = validate_contact(contact_fields(request.form),
                                                            need_company=False)
            errors = errors + contact_errors
        if not errors:
            if existing_job is None:
                company_id = find_or_create_company(company_data)
                app_data["job_id"] = execute(
                    """INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max,
                                         job_url, date_posted, requirements)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (company_id, job_data["job_title"], job_data["job_type"],
                     job_data["salary_min"], job_data["salary_max"], job_data["job_url"],
                     job_data["date_posted"], job_data["requirements"]),
                )
            else:
                company_id = existing_job["company_id"]
            execute(
                """INSERT INTO applications (job_id, application_date, status, resume_version,
                                             cover_letter_sent, interview_data)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (app_data["job_id"], app_data["application_date"], app_data["status"],
                 app_data["resume_version"], app_data["cover_letter_sent"],
                 app_data["interview_data"]),
            )
            if include_contact:
                execute(
                    """INSERT INTO contacts (company_id, contact_name, title, email, phone,
                                             linkedin_url, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (company_id, contact_data["contact_name"], contact_data["title"],
                     contact_data["email"], contact_data["phone"],
                     contact_data["linkedin_url"], contact_data["notes"]),
                )
                flash("Application and contact added.", "success")
            else:
                flash("Application added.", "success")
            return redirect(url_for("applications"))
        form = request.form
    else:
        form = {"application_date": date.today().isoformat(), "status": "Applied"}
        errors = []
    return render_template("application_form.html", form=form, errors=errors, application=None,
                           existing_job=existing_job,
                           company_names=[c["company_name"] for c in company_choices()],
                           job_types=JOB_TYPES, statuses=STATUSES,
                           interview_types=INTERVIEW_TYPES, today=date.today().isoformat())


@app.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
def application_edit(application_id):
    application = get_or_404(APPLICATION_SELECT + " WHERE a.application_id = %s", application_id)
    if request.method == "POST":
        data, errors = validate_application(request.form)
        if not errors:
            execute(
                """UPDATE applications
                   SET job_id = %s, application_date = %s, status = %s, resume_version = %s,
                       cover_letter_sent = %s, interview_data = %s
                   WHERE application_id = %s""",
                (data["job_id"], data["application_date"], data["status"], data["resume_version"],
                 data["cover_letter_sent"], data["interview_data"], application_id),
            )
            flash("Application updated.", "success")
            return redirect(url_for("application_detail", application_id=application_id))
        form = request.form
    else:
        form = application_form_values(application)
        errors = []
    return render_template("application_form.html", form=form, errors=errors,
                           application=application, jobs=job_choices(), statuses=STATUSES,
                           interview_types=INTERVIEW_TYPES, today=date.today().isoformat())


@app.route("/applications/<int:application_id>/delete", methods=["POST"])
def application_delete(application_id):
    get_or_404("SELECT * FROM applications WHERE application_id = %s", application_id)
    execute("DELETE FROM applications WHERE application_id = %s", (application_id,))
    flash("Application deleted.", "success")
    return redirect(url_for("applications"))


CONTACT_SELECT = """SELECT t.*, c.company_name
                    FROM contacts t JOIN companies c ON c.company_id = t.company_id"""


def validate_contact(form, need_company=True):
    errors = []
    data = {field: clean(form, field)
            for field in ("contact_name", "title", "email", "phone", "linkedin_url", "notes")}

    company_id = clean(form, "company_id")
    if not need_company:
        data["company_id"] = None
    elif not company_id or not company_id.isdigit() or not company_exists(int(company_id)):
        errors.append("Please choose a company.")
        data["company_id"] = None
    else:
        data["company_id"] = int(company_id)

    if not data["contact_name"]:
        errors.append("Contact name is required.")
    check_length(errors, "Contact name", data["contact_name"], 100)
    check_length(errors, "Title", data["title"], 100)
    check_length(errors, "Email", data["email"], 100)
    check_length(errors, "Phone", data["phone"], 20)
    check_length(errors, "LinkedIn URL", data["linkedin_url"], 200)

    if data["email"] and not EMAIL_PATTERN.match(data["email"]):
        errors.append("Email does not look like a valid address.")
    check_url(errors, "LinkedIn URL", data["linkedin_url"])
    return data, errors


@app.route("/contacts")
def contacts():
    rows = query_all(CONTACT_SELECT + " ORDER BY t.contact_name")
    return render_template("contacts.html", contacts=rows)


@app.route("/contacts/<int:contact_id>")
def contact_detail(contact_id):
    contact = get_or_404(CONTACT_SELECT + " WHERE t.contact_id = %s", contact_id)
    return render_template("contact_detail.html", contact=contact)


@app.route("/contacts/add", methods=["GET", "POST"])
def contact_add():
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        if not errors:
            execute(
                """INSERT INTO contacts (company_id, contact_name, title, email, phone,
                                         linkedin_url, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (data["company_id"], data["contact_name"], data["title"], data["email"],
                 data["phone"], data["linkedin_url"], data["notes"]),
            )
            flash(f"Contact \"{data['contact_name']}\" added.", "success")
            return redirect(url_for("contacts"))
        form = request.form
    else:
        form = {"company_id": request.args.get("company_id", "")}
        errors = []
    return render_template("contact_form.html", form=form, errors=errors, contact=None,
                           companies=company_choices())


@app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
def contact_edit(contact_id):
    contact = get_or_404(CONTACT_SELECT + " WHERE t.contact_id = %s", contact_id)
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        if not errors:
            execute(
                """UPDATE contacts
                   SET company_id = %s, contact_name = %s, title = %s, email = %s,
                       phone = %s, linkedin_url = %s, notes = %s
                   WHERE contact_id = %s""",
                (data["company_id"], data["contact_name"], data["title"], data["email"],
                 data["phone"], data["linkedin_url"], data["notes"], contact_id),
            )
            flash(f"Contact \"{data['contact_name']}\" updated.", "success")
            return redirect(url_for("contact_detail", contact_id=contact_id))
        form = request.form
    else:
        form = contact
        errors = []
    return render_template("contact_form.html", form=form, errors=errors, contact=contact,
                           companies=company_choices())


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def contact_delete(contact_id):
    contact = get_or_404("SELECT * FROM contacts WHERE contact_id = %s", contact_id)
    execute("DELETE FROM contacts WHERE contact_id = %s", (contact_id,))
    flash(f"Contact \"{contact['contact_name']}\" deleted.", "success")
    return redirect(url_for("contacts"))


def calculate_match(user_skills, required_skills):
    have = {skill.lower() for skill in user_skills}
    matched = [skill for skill in required_skills if skill.lower() in have]
    missing = [skill for skill in required_skills if skill.lower() not in have]
    total = len(required_skills)
    percent = round(len(matched) / total * 100) if total else 0
    return {"matched": matched, "missing": missing, "total": total, "percent": percent}


def rank_jobs(user_skills, job_rows):
    results = []
    for job in job_rows:
        required = parse_skills(",".join(job_skills(job)))
        if not required:
            continue
        match = calculate_match(user_skills, required)
        match["job"] = job
        results.append(match)
    results.sort(key=lambda m: (-m["percent"], -len(m["matched"]), m["job"]["job_title"]))
    return results


@app.route("/job-match", methods=["GET", "POST"])
def job_match():
    skills_text = request.form.get("skills", "")
    user_skills = parse_skills(skills_text)
    matches = []
    no_match_count = 0
    error = None

    if request.method == "POST":
        if not user_skills:
            error = "Enter at least one skill, separated by commas."
        else:
            ranked = rank_jobs(user_skills, query_all(JOB_SELECT))
            matches = [m for m in ranked if m["percent"] > 0]
            no_match_count = len(ranked) - len(matches)

    return render_template("job_match.html", skills_text=skills_text, user_skills=user_skills,
                           matches=matches, no_match_count=no_match_count, error=error,
                           searched=request.method == "POST" and not error)


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