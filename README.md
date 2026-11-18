# Job Application Tracker

Track companies, jobs, applications and contacts, and match your skills to jobs.
Built with MySQL, Flask and HTML/CSS.

## Setup

```bash
git clone https://github.com/abaez058/job-application-tracker-.git
cd job-application-tracker-
pip install -r requirements.txt
WINODWS
  cmd /c "mysql -u root -p < schema.sql"
MAC
  mysql -u root -p < schema.sql
```

On Windows PowerShell, load the database with `cmd /c "mysql -u root -p < schema.sql"`.

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000. Run the tests with `python test_app.py`.
