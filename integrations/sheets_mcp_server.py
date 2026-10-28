# Expose the optional Google Sheets integration through the MCP server.
import os
import gspread
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Job Tracker Sheets")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Credentials File
CREDENTIALS_FILE = os.path.join(
    BASE_DIR, "Credentials", "gen-lang-client-0317453229-e1a20eae4bae.json"
)
SPREADSHEET_FILE_NAME = "Vedro - Job Application"

# Authenticate service account
gc = gspread.service_account(CREDENTIALS_FILE)


# Define the Tool for the AI to add applied job
@mcp.tool
def log_job_application(
    company: str,
    position: str,
    applied_date: str,
    location: str,
    status: str,
    link: str,
) -> str:
    """
    Logs a new job application into the user's Google Sheets Job Tracker.
    Always call this tool when the user asks to save or log an application.
    """
    try:
        # Open the spreadsheet and select the first sheet
        sheet = gc.open(SPREADSHEET_FILE_NAME).sheet1

        # The data we want to insert as a new row
        new_row = [company, position, applied_date, location, status, link]

        # Append the row to the bottom of the sheet
        sheet.append_row(new_row)

        return f"Successfully logged application for {position} at {company} with status: {status}."
    except Exception as e:
        return f"Error logging application to Google Sheets: {str(e)}"


if __name__ == "__main__":
    # Start the server
    mcp.run()
