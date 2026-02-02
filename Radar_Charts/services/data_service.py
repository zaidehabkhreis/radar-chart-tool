"""
Data service for Excel/Drive data management.
"""
import io
import time
import hashlib
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from ..config import Config


class DataService:
    """Handles data fetching and processing from Google Drive."""

    def __init__(self, credentials):
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.data_dict = {}
        self.pillar_avg_scores_dict = {}
        self.unique_pillars = []
        self._latest_hash = None
        self._last_checked_time = 0

    def _calculate_file_hash(self, file_stream) -> str:
        """Calculate MD5 hash of file content."""
        file_stream.seek(0)
        hasher = hashlib.md5()
        while True:
            chunk = file_stream.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
        return hasher.hexdigest()

    def fetch_if_updated(self) -> bool:
        """Fetch latest Excel data if it has been updated."""
        current_time = time.time()
        if current_time - self._last_checked_time < Config.CHECK_INTERVAL:
            return False
        self._last_checked_time = current_time

        try:
            request = self.drive_service.files().get_media(
                fileId=Config.DRIVE_FILE_ID,
                supportsAllDrives=True
            )
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            new_hash = self._calculate_file_hash(file_stream)
            if new_hash == self._latest_hash:
                return False
            self._latest_hash = new_hash

            file_stream.seek(0)
            self._process_excel(file_stream)
            return True

        except Exception as e:
            print(f"Error fetching spreadsheet: {e}")
            return False

    def _process_excel(self, file_stream):
        """Process Excel file and extract data."""
        sheets = pd.ExcelFile(file_stream)

        new_data_dict = {}
        new_pillar_avg_scores_dict = {}
        all_pillars = set()

        for sheet_name in sheets.sheet_names:
            df = sheets.parse(sheet_name)

            # Handle percentage columns
            for col in ['Capacity', 'Utilization']:
                if col in df.columns and df[col].dtype == 'object':
                    df[col] = df[col].str.replace('%', '').astype(float)

            new_data_dict[sheet_name] = df

            if 'Pillar' in df.columns and 'Score' in df.columns:
                avg_scores = df.groupby('Pillar')['Score'].mean().round(1).reset_index()
                new_pillar_avg_scores_dict[sheet_name] = avg_scores
                pillars_in_sheet = df['Pillar'].dropna().unique()
                all_pillars.update(pillars_in_sheet)

        self.data_dict = new_data_dict
        self.pillar_avg_scores_dict = new_pillar_avg_scores_dict
        self.unique_pillars = sorted(all_pillars) if all_pillars else ["No Data"]

    def get_employee_summary(self, sheet_name: str) -> dict:
        """Get a summary of an employee's data."""
        if sheet_name not in self.data_dict:
            return None

        df = self.data_dict[sheet_name]
        summary = {"name": sheet_name, "skills": {}}

        if 'Pillar' in df.columns and 'Score' in df.columns:
            avg_scores = df.groupby('Pillar')['Score'].mean().round(1)
            summary["skills"] = avg_scores.to_dict()
            summary["overall_avg"] = round(avg_scores.mean(), 1)

        if 'Capacity' in df.columns and not df.empty:
            summary["capacity"] = df['Capacity'].iloc[0]

        if 'Utilization' in df.columns and not df.empty:
            summary["utilization"] = df['Utilization'].iloc[0]

        if 'Specific Skill' in df.columns:
            summary["specific_skills"] = df['Specific Skill'].tolist()

        return summary

    def get_all_employees_summary(self) -> list:
        """Get summary of all employees for chatbot context."""
        summaries = []
        for sheet_name in self.data_dict.keys():
            summary = self.get_employee_summary(sheet_name)
            if summary:
                summaries.append(summary)
        return summaries

    def build_context_for_chat(self) -> str:
        """Build a text context of all employee data for the chatbot."""
        summaries = self.get_all_employees_summary()
        if not summaries:
            return "No employee data available."

        context_lines = []
        for emp in summaries:
            lines = [f"\n=== {emp['name']} ==="]

            if emp.get('skills'):
                lines.append("Skills & Scores:")
                for skill, score in emp['skills'].items():
                    lines.append(f"  - {skill}: {score}/10")
                if 'overall_avg' in emp:
                    lines.append(f"  Overall Average: {emp['overall_avg']}/10")

            if 'capacity' in emp:
                cap = emp['capacity']
                cap_display = f"{int(cap * 100)}%" if cap <= 1 else f"{int(cap)}%"
                lines.append(f"Capacity: {cap_display}")

            if 'utilization' in emp:
                util = emp['utilization']
                util_display = f"{int(util * 100)}%" if util <= 1 else f"{int(util)}%"
                lines.append(f"Utilization: {util_display}")

            if emp.get('specific_skills'):
                lines.append(f"Specific Skills: {', '.join(str(s) for s in emp['specific_skills'] if pd.notna(s))}")

            context_lines.append("\n".join(lines))

        return "\n".join(context_lines)
