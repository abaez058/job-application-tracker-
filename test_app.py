"""Tests for the Job Application Tracker.

Run with:  python test_app.py

MySQL has to be running with schema.sql loaded. Everything the tests create
is named "ZZ Test ..." and gets deleted at the end, so your real data is safe.
"""

import unittest

from app import app, calculate_match, parse_skills, rank_jobs
from database import execute, query_one


class MatchLogicTests(unittest.TestCase):
    """The Job Match math. These don't need the database at all."""

    def test_parse_skills_trims_and_removes_duplicates(self):
        self.assertEqual(parse_skills(" Python, sql ,, PYTHON,  REST   APIs "),
                         ["Python", "sql", "REST APIs"])

    def test_full_match(self):
        match = calculate_match(["python", "sql", "flask"], ["Python", "SQL", "Flask"])
        self.assertEqual(match["percent"], 100)
        self.assertEqual(match["missing"], [])

    def test_partial_match_lists_missing_skills(self):
        match = calculate_match(["Python", "SQL", "Flask"], ["Python", "SQL", "Tableau"])
        self.assertEqual(match["percent"], 67)
        self.assertEqual(match["matched"], ["Python", "SQL"])
        self.assertEqual(match["missing"], ["Tableau"])

    def test_no_requirements_is_zero_not_an_error(self):
        self.assertEqual(calculate_match(["Python"], [])["percent"], 0)

    def test_ranking_orders_best_match_first_and_skips_empty_jobs(self):
        jobs = [
            {"job_title": "Analyst", "requirements": '["Python", "SQL", "Tableau"]'},
            {"job_title": "No skills listed", "requirements": None},
            {"job_title": "Developer", "requirements": '["Python", "SQL", "Flask"]'},
        ]
        ranked = rank_jobs(["Python", "SQL", "Flask"], jobs)
        self.assertEqual([m["job"]["job_title"] for m in ranked], ["Developer", "Analyst"])
        self.assertEqual([m["percent"] for m in ranked], [100, 67])


class CrudTests(unittest.TestCase):
    """Add, view, edit and delete through the real pages and the real database."""

    def setUp(self):
        self.client = app.test_client()
        self.cleanup()

    def tearDown(self):
        self.cleanup()

    @staticmethod
    def cleanup():
        # Deleting the test companies takes their jobs, applications and contacts too.
        execute("DELETE FROM companies WHERE company_name LIKE 'ZZ Test%'")

    def add_company(self):
        self.client.post("/companies/add", data={"company_name": "ZZ Test Co", "city": "Miami"})
        return query_one("SELECT * FROM companies WHERE company_name = 'ZZ Test Co'")

    def add_job(self, company_id):
        self.client.post("/jobs/add", data={
            "company_id": company_id, "job_title": "ZZ Test Engineer", "job_type": "Full-time",
            "salary_min": "50000", "salary_max": "60000",
            "requirements_text": "Python, SQL, Docker"})
        return query_one("SELECT * FROM jobs WHERE job_title = 'ZZ Test Engineer'")

    def test_every_page_loads(self):
        for path in ("/", "/companies", "/jobs", "/applications", "/contacts", "/job-match",
                     "/companies/add", "/jobs/add", "/applications/add", "/contacts/add",
                     "/applications?status=Interview"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_missing_record_gives_404(self):
        for path in ("/companies/999999", "/jobs/999999/edit", "/applications/999999",
                     "/contacts/999999"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_company_crud(self):
        company = self.add_company()
        self.assertIsNotNone(company)
        company_id = company["company_id"]

        self.assertIn(b"ZZ Test Co", self.client.get("/companies").data)
        self.assertEqual(self.client.get(f"/companies/{company_id}").status_code, 200)

        self.client.post(f"/companies/{company_id}/edit",
                         data={"company_name": "ZZ Test Co Renamed", "industry": "Software"})
        updated = query_one("SELECT * FROM companies WHERE company_id = %s", (company_id,))
        self.assertEqual(updated["company_name"], "ZZ Test Co Renamed")
        self.assertIsNone(updated["city"])  # left blank on purpose, so it should be cleared

        self.client.post(f"/companies/{company_id}/delete")
        self.assertIsNone(query_one("SELECT * FROM companies WHERE company_id = %s", (company_id,)))

    def test_company_validation(self):
        response = self.client.post("/companies/add", data={"company_name": "  "})
        self.assertIn(b"Company name is required", response.data)
        response = self.client.post("/companies/add",
                                    data={"company_name": "ZZ Test Bad", "website": "not-a-url"})
        self.assertIn(b"must start with http", response.data)
        self.assertIsNone(query_one("SELECT * FROM companies WHERE company_name = 'ZZ Test Bad'"))

    def test_job_crud_and_validation(self):
        company_id = self.add_company()["company_id"]
        job = self.add_job(company_id)
        self.assertIsNotNone(job)
        job_id = job["job_id"]
        self.assertIn(b"Docker", self.client.get(f"/jobs/{job_id}").data)
        self.assertIn(b"Python, SQL, Docker", self.client.get(f"/jobs/{job_id}/edit").data)

        # A minimum salary above the maximum should be refused, with nothing saved.
        response = self.client.post(f"/jobs/{job_id}/edit", data={
            "company_id": company_id, "job_title": "ZZ Test Engineer",
            "salary_min": "90000", "salary_max": "60000"})
        self.assertIn(b"cannot be greater than", response.data)
        self.assertEqual(query_one("SELECT salary_min FROM jobs WHERE job_id = %s",
                                   (job_id,))["salary_min"], 50000)

        response = self.client.post("/jobs/add", data={"company_id": "999999", "job_title": ""})
        self.assertIn(b"Please choose a company", response.data)
        self.assertIn(b"Job title is required", response.data)

        self.client.post(f"/jobs/{job_id}/edit", data={
            "company_id": company_id, "job_title": "ZZ Test Engineer II",
            "job_type": "Contract", "requirements_text": "Go"})
        self.assertIn(b"ZZ Test Engineer II", self.client.get("/jobs").data)

        self.client.post(f"/jobs/{job_id}/delete")
        self.assertIsNone(query_one("SELECT * FROM jobs WHERE job_id = %s", (job_id,)))

    def test_application_crud_and_validation(self):
        job_id = self.add_job(self.add_company()["company_id"])["job_id"]

        response = self.client.post("/applications/add", data={
            "job_id": job_id, "application_date": "2999-01-01", "status": "Applied"})
        self.assertIn(b"cannot be in the future", response.data)
        response = self.client.post("/applications/add", data={
            "job_id": job_id, "application_date": "", "status": "Hired"})
        self.assertIn(b"Application date is required", response.data)
        self.assertIn(b"Please choose a status", response.data)

        self.client.post("/applications/add", data={
            "job_id": job_id, "application_date": "2026-11-01", "status": "Interview",
            "resume_version": "v1", "cover_letter_sent": "1",
            "interview_date": "2026-11-12", "interview_type": "Phone",
            "interviewer": "ZZ Interviewer", "interview_notes": "Bring questions"})
        application = query_one("SELECT * FROM applications WHERE job_id = %s", (job_id,))
        self.assertIsNotNone(application)
        self.assertEqual(application["cover_letter_sent"], 1)
        application_id = application["application_id"]

        page = self.client.get(f"/applications/{application_id}").data
        self.assertIn(b"ZZ Interviewer", page)
        self.assertIn(b"Bring questions", self.client.get(f"/applications/{application_id}/edit").data)

        self.client.post(f"/applications/{application_id}/edit", data={
            "job_id": job_id, "application_date": "2026-11-01", "status": "Offer"})
        updated = query_one("SELECT * FROM applications WHERE application_id = %s", (application_id,))
        self.assertEqual(updated["status"], "Offer")
        self.assertEqual(updated["cover_letter_sent"], 0)
        self.assertIsNone(updated["interview_data"])

        self.client.post(f"/applications/{application_id}/delete")
        self.assertIsNone(query_one("SELECT * FROM applications WHERE application_id = %s",
                                    (application_id,)))

    def test_contact_crud_and_validation(self):
        company_id = self.add_company()["company_id"]

        response = self.client.post("/contacts/add", data={
            "company_id": company_id, "contact_name": "ZZ Test Person", "email": "not-an-email"})
        self.assertIn(b"valid address", response.data)

        self.client.post("/contacts/add", data={
            "company_id": company_id, "contact_name": "ZZ Test Person",
            "email": "zz@example.com", "phone": "305-555-0100"})
        contact = query_one("SELECT * FROM contacts WHERE contact_name = 'ZZ Test Person'")
        self.assertIsNotNone(contact)
        contact_id = contact["contact_id"]
        self.assertIn(b"zz@example.com", self.client.get(f"/contacts/{contact_id}").data)

        self.client.post(f"/contacts/{contact_id}/edit", data={
            "company_id": company_id, "contact_name": "ZZ Test Person", "title": "Recruiter"})
        self.assertEqual(query_one("SELECT title FROM contacts WHERE contact_id = %s",
                                   (contact_id,))["title"], "Recruiter")

        self.client.post(f"/contacts/{contact_id}/delete")
        self.assertIsNone(query_one("SELECT * FROM contacts WHERE contact_id = %s", (contact_id,)))

    def test_deleting_company_cascades(self):
        company_id = self.add_company()["company_id"]
        job_id = self.add_job(company_id)["job_id"]
        self.client.post("/applications/add", data={
            "job_id": job_id, "application_date": "2026-11-01", "status": "Applied"})
        self.client.post(f"/companies/{company_id}/delete")
        self.assertIsNone(query_one("SELECT * FROM jobs WHERE job_id = %s", (job_id,)))
        self.assertIsNone(query_one("SELECT * FROM applications WHERE job_id = %s", (job_id,)))

    def test_delete_requires_post(self):
        company_id = self.add_company()["company_id"]
        self.assertEqual(self.client.get(f"/companies/{company_id}/delete").status_code, 405)

    def test_job_match_page(self):
        self.add_job(self.add_company()["company_id"])
        response = self.client.post("/job-match", data={"skills": "python, sql"})
        self.assertIn(b"ZZ Test Engineer", response.data)
        self.assertIn(b"67%", response.data)
        self.assertIn(b"(2/3 skills)", response.data)

        response = self.client.post("/job-match", data={"skills": " , "})
        self.assertIn(b"Enter at least one skill", response.data)

    def test_html_is_escaped(self):
        self.client.post("/companies/add", data={"company_name": "ZZ Test <script>x</script>"})
        page = self.client.get("/companies").data
        self.assertNotIn(b"<script>x</script>", page)
        self.assertIn(b"&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main(verbosity=1)
