import os
from flask import Flask, render_template, request, send_file
from dotenv import load_dotenv
from compliance_logic import read_docx, check_compliance, modify_docx
from email_smtp import send_email

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

UPLOAD_FOLDER = "contracts"
MODIFIED_FOLDER = "modified"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = os.getenv("FLASK_SECRET_KEY")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODIFIED_FOLDER, exist_ok=True)


# ✅ Google Sheets setup function
def write_to_google_sheet(original_file, missing_clauses, email_status):
    try:
        if os.getenv("GOOGLE_SHEETS_ENABLED") != "true":
            return "Google Sheets logging disabled"

        credentials_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        sheet_tab = os.getenv("GOOGLE_SHEET_TAB")

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(sheet_id).worksheet(sheet_tab)

        missing_text = ", ".join(missing_clauses) if missing_clauses else "No missing clauses"

        sheet.append_row([
            original_file,
            missing_text,
            email_status,
        ])

        return "Logged to Google Sheets"

    except Exception as e:
        return f"Google Sheets Error: {str(e)}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return "No file selected"

    file = request.files["file"]

    if file.filename == "":
        return "Empty filename"

    saved_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(saved_path)

    # ✅ Read contract
    content = read_docx(saved_path)
    missing = check_compliance(content)

    # ✅ Prepare modified file
    modified_filename = file.filename.replace(".docx", "_modified.docx")
    modified_path = os.path.join(MODIFIED_FOLDER, modified_filename)
    modify_docx(saved_path, modified_path, missing)

    # ✅ Missing clauses text
    if missing:
        missing_text = "\n".join(f"- {m}" for m in missing)
    else:
        missing_text = "✅ No missing clauses — fully compliant."

    # ✅ Email body
    email_message = f"""
Hello {os.getenv("EMAIL_TEAM_NAME")},

Contract checked: {file.filename}

Missing clauses:
{missing_text}

Modified contract is available for download.

Regards,
Compliance Checker AI System
"""

    # ✅ Send email
    email_status = send_email(
        subject="Compliance Checker Update",
        body=email_message,
        recipients=os.getenv("EMAIL_TO").split(","),
        smtp_server=os.getenv("EMAIL_SMTP_HOST"),
        smtp_port=int(os.getenv("EMAIL_SMTP_PORT")),
        smtp_user=os.getenv("EMAIL_FROM"),
        smtp_password=os.getenv("EMAIL_PASSWORD"),
    )

    # ✅ Log result to Google Sheets
    sheet_status = write_to_google_sheet(file.filename, missing, email_status)

    return render_template(
        "result.html",
        original_filename=file.filename,
        updated_filename=modified_filename,
        missing=missing,
        email_status=email_status,
        sheet_status=sheet_status
    )


@app.route("/download/uploads/<path:filename>")
def download_upload(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename), as_attachment=True)


@app.route("/download/updated/<path:filename>")
def download_modified(filename):
    return send_file(os.path.join(MODIFIED_FOLDER, filename), as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
