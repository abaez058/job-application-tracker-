-- ============================================================
-- Job Application Tracker - database setup
-- COP4751 Course Project
--
-- Run it with:  mysql -u root -p < schema.sql
-- Heads up: this deletes job_tracker and builds it again from scratch,
-- so you can re-run it any time you want a clean start.
-- ============================================================

DROP DATABASE IF EXISTS job_tracker;
CREATE DATABASE job_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE job_tracker;

-- ------------------------------------------------------------
-- companies: every employer you're keeping track of
-- ------------------------------------------------------------
CREATE TABLE companies (
    company_id   INT PRIMARY KEY AUTO_INCREMENT,
    company_name VARCHAR(100) NOT NULL,
    industry     VARCHAR(50),
    website      VARCHAR(200),
    city         VARCHAR(50),
    state        VARCHAR(50),
    notes        TEXT
);

-- ------------------------------------------------------------
-- jobs: a job posting, always tied to one company
-- requirements holds the skills as a JSON list,
--   e.g. ["Python", "SQL", "Flask"]
-- ------------------------------------------------------------
CREATE TABLE jobs (
    job_id       INT PRIMARY KEY AUTO_INCREMENT,
    company_id   INT NOT NULL,
    job_title    VARCHAR(100) NOT NULL,
    job_type     ENUM('Full-time', 'Part-time', 'Contract', 'Internship'),
    salary_min   INT,
    salary_max   INT,
    job_url      VARCHAR(300),
    date_posted  DATE,
    requirements JSON,
    CONSTRAINT fk_jobs_company
        FOREIGN KEY (company_id) REFERENCES companies (company_id)
        ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- applications: each time you apply to a job
-- interview_data keeps the interview details as JSON,
--   e.g. {"date": "2026-11-02", "type": "Phone",
--         "interviewer": "Jane Doe", "notes": "Went well"}
-- ------------------------------------------------------------
CREATE TABLE applications (
    application_id    INT PRIMARY KEY AUTO_INCREMENT,
    job_id            INT NOT NULL,
    application_date  DATE NOT NULL,
    status            ENUM('Applied', 'Screening', 'Interview',
                           'Offer', 'Rejected', 'Withdrawn')
                      NOT NULL DEFAULT 'Applied',
    resume_version    VARCHAR(50),
    cover_letter_sent BOOLEAN NOT NULL DEFAULT FALSE,
    interview_data    JSON,
    CONSTRAINT fk_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs (job_id)
        ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- contacts: people you know at a company
-- ------------------------------------------------------------
CREATE TABLE contacts (
    contact_id   INT PRIMARY KEY AUTO_INCREMENT,
    company_id   INT NOT NULL,
    contact_name VARCHAR(100) NOT NULL,
    title        VARCHAR(100),
    email        VARCHAR(100),
    phone        VARCHAR(20),
    linkedin_url VARCHAR(200),
    notes        TEXT,
    CONSTRAINT fk_contacts_company
        FOREIGN KEY (company_id) REFERENCES companies (company_id)
        ON DELETE CASCADE
);

-- ============================================================
-- A few sample rows so the app isn't empty the first time you open it
-- ============================================================

INSERT INTO companies (company_name, industry, website, city, state, notes) VALUES
    ('TechCorp',       'Software',   'https://www.techcorp.example',   'Miami',       'FL', 'Met a recruiter at the fall career fair.'),
    ('DataCo',         'Analytics',  'https://www.dataco.example',     'Austin',      'TX', NULL),
    ('Sunshine Health','Healthcare', 'https://www.sunhealth.example',  'Orlando',     'FL', 'Hybrid schedule, 3 days in office.'),
    ('FinEdge',        'Finance',    'https://www.finedge.example',    'New York',    'NY', NULL);

INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, job_url, date_posted, requirements) VALUES
    (1, 'Software Developer',     'Full-time',  75000, 95000,  'https://www.techcorp.example/jobs/101',  '2026-10-20', '["Python", "SQL", "Flask"]'),
    (1, 'Backend Intern',         'Internship', 40000, 48000,  'https://www.techcorp.example/jobs/118',  '2026-11-01', '["Python", "Git", "REST APIs"]'),
    (2, 'Data Analyst',           'Full-time',  65000, 80000,  'https://www.dataco.example/careers/7',   '2026-10-15', '["Python", "SQL", "Tableau"]'),
    (3, 'Database Administrator', 'Full-time',  80000, 105000, 'https://www.sunhealth.example/jobs/55', '2026-10-28', '["MySQL", "SQL", "Linux", "Backups"]'),
    (4, 'Web Developer',          'Contract',   60000, 78000,  'https://www.finedge.example/jobs/9',    '2026-11-05', '["HTML", "CSS", "JavaScript", "Flask"]');

INSERT INTO applications (job_id, application_date, status, resume_version, cover_letter_sent, interview_data) VALUES
    (1, '2026-10-22', 'Interview', 'v3-backend', TRUE,
        '{"date": "2026-11-10", "type": "Technical", "interviewer": "Maria Lopez", "notes": "Live coding in Python, then SQL joins."}'),
    (3, '2026-10-18', 'Screening', 'v2-data',    TRUE,
        '{"date": "2026-10-30", "type": "Phone", "interviewer": "Sam Patel", "notes": "Recruiter screen, 20 minutes."}'),
    (4, '2026-11-02', 'Applied',   'v3-backend', FALSE, NULL),
    (5, '2026-11-06', 'Rejected',  'v1-general', FALSE, NULL);

INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes) VALUES
    (1, 'Maria Lopez', 'Engineering Manager', 'maria.lopez@techcorp.example', '305-555-0142', 'https://www.linkedin.com/in/maria-lopez-example', 'Interviewer for the Software Developer role.'),
    (2, 'Sam Patel',   'Technical Recruiter', 'sam.patel@dataco.example',     '512-555-0177', NULL, 'Prefers email over phone.'),
    (3, 'Dana Kim',    'HR Coordinator',      'dana.kim@sunhealth.example',   NULL,           NULL, NULL);
