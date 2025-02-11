from flask import Flask, render_template, request, redirect, url_for, make_response
import pandas as pd
import plotly.graph_objects as go
import json
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import io
import time
import hashlib
from google.cloud import storage



app = Flask(__name__)



ADMIN_EMAIL = "tariq.khasawneh@devoteam.com"  # Define the admin user
DRIVE_FILE_ID = "1CdG-BtG3aqJVkZKzKwFrPFSPhRIwmXQteI4DNVfYtGc"

service_account_json = os.getenv("SERVICE_ACCOUNT")

if service_account_json:
    credentials_dict = json.loads(service_account_json)  # Convert string to dict
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
else:
    raise Exception("Missing SERVICE_ACCOUNT environment variable")

drive_service = build("drive", "v3", credentials=credentials)


def fetch_users_from_gcs():
    """Fetch the users JSON file from Google Cloud Storage."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(USERS_FILE_NAME)

    if not blob.exists():
        raise Exception(f"Users file {USERS_FILE_NAME} not found in bucket {BUCKET_NAME}")

    users_json = blob.download_as_text()
    users_data = json.loads(users_json)
    return {user["email"]: user["password"] for user in users_data["users"]}

def save_users_to_gcs(users_dict):
    """Save the updated users JSON file back to Google Cloud Storage."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(USERS_FILE_NAME)

    users_data = {"users": [{"email": email, "password": password} for email, password in users_dict.items()]}
    blob.upload_from_string(json.dumps(users_data, indent=4), content_type="application/json")


storage_client = storage.Client()  # No explicit credentials needed in Cloud Run
BUCKET_NAME = "radar-chart-users"
USERS_FILE_NAME = "users.json"



# Fetch users initially
VALID_USERS = fetch_users_from_gcs()


# Global variables to track the latest hash and sheets
data_dict = {}
pillar_avg_scores_dict = {}
latest_hash = None
last_checked_time = 0
CHECK_INTERVAL = 60  # Check for updates every 60 seconds

def calculate_file_hash(file_stream):
    """Compute the hash of the file to detect changes."""
    file_stream.seek(0)
    hasher = hashlib.md5()
    while chunk := file_stream.read(8192):
        hasher.update(chunk)
    return hasher.hexdigest()

def fetch_latest_excel_if_updated():
    """Fetch the latest spreadsheet from Google Drive only if an update exists."""
    global latest_hash, data_dict, pillar_avg_scores_dict, unique_pillars, last_checked_time
    
    current_time = time.time()
    if current_time - last_checked_time < CHECK_INTERVAL:
        return  # Skip checking if within the interval
    
    last_checked_time = current_time  # Update the last checked time
    
    request = drive_service.files().get_media(fileId=DRIVE_FILE_ID)
    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    
    new_hash = calculate_file_hash(file_stream)
    
    if new_hash == latest_hash:
        return  # No changes detected, skip reloading
    
    latest_hash = new_hash  # Update the stored hash
    file_stream.seek(0)
    sheets = pd.ExcelFile(file_stream)
    
    # Load the updated data
    new_data_dict = {sheet_name: sheets.parse(sheet_name) for sheet_name in sheets.sheet_names}
    new_pillar_avg_scores_dict = {}

    all_pillars = set()
    
    for sheet_name, data in new_data_dict.items():
        if 'Utilization' in data.columns and data['Utilization'].dtype == 'object':
            data['Utilization'] = data['Utilization'].str.replace('%', '').astype(float)
        
        if 'Pillar' in data.columns and 'Score' in data.columns:
            avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()
            new_pillar_avg_scores_dict[sheet_name] = avg_scores
            all_pillars.update(data['Pillar'].unique())
    
    # Update global variables only after successful loading
    data_dict = new_data_dict
    pillar_avg_scores_dict = new_pillar_avg_scores_dict
    unique_pillars = sorted(all_pillars)

@app.before_request
def check_for_updates():
    """Check for spreadsheet updates before handling any request."""
    fetch_latest_excel_if_updated()

# Authentication Middleware
def get_authenticated_user(request):
    """Check if the user is authenticated via cookies."""
    email = request.cookies.get("user_email")
    password = request.cookies.get("user_password")

    if email in VALID_USERS and VALID_USERS[email] == password:
        return email
    return None


@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    """Admin panel for managing users."""
    user = get_authenticated_user(request)
    if user != ADMIN_EMAIL:
        return redirect(url_for('index'))  # Only admin can access

    if request.method == 'POST':
        action = request.form.get("action")
        email = request.form.get("email")
        password = request.form.get("password")

        if action == "add" and email and password:
            if email not in VALID_USERS:
                VALID_USERS[email] = password
                save_users_to_gcs(VALID_USERS)

        elif action == "edit" and email and password:
            if email in VALID_USERS:
                VALID_USERS[email] = password
                save_users_to_gcs(VALID_USERS)

        elif action == "remove" and email:
            if email in VALID_USERS:
                del VALID_USERS[email]
                save_users_to_gcs(VALID_USERS)

    return render_template('admin.html', users=VALID_USERS, user=user)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Fetch users dynamically to ensure we have the latest list
        global VALID_USERS
        VALID_USERS = fetch_users_from_gcs()

        if email in VALID_USERS and VALID_USERS[email] == password:
            response = make_response(redirect(url_for('index')))
            response.set_cookie("user_email", email)
            response.set_cookie("user_password", password)
            return response
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route('/logout')
def logout():
    """Logout user by clearing cookies."""
    response = make_response(redirect(url_for('login')))
    response.delete_cookie("user_email")
    response.delete_cookie("user_password")
    return response

def get_applied_filters(request):
    """Retrieve filters from cookies"""
    applied_filters = request.cookies.get('applied_filters', '[]')
    return json.loads(applied_filters)

def set_applied_filters(response, applied_filters):
    """Set filters in cookies"""
    response.set_cookie('applied_filters', json.dumps(applied_filters))

def filter_data(data, applied_filters):
    """Apply all filters to the given data."""
    filtered_data_dict = {}

    for sheet_name, df in data.items():  # Iterate over each sheet
        include_sheet = True  # Assume sheet is included until proven otherwise

        if 'Pillar' in df.columns and 'Score' in df.columns:
            avg_scores = pillar_avg_scores_dict.get(sheet_name, pd.DataFrame())

            for filter_str in applied_filters:
                try:
                    # Extract pillar, operator, and value from filter string
                    filter_parts = filter_str.replace('Pillar: ', '').split(' ', 2)
                    if len(filter_parts) != 3:
                        continue  # Skip invalid filters

                    pillar = filter_parts[0]
                    operator = filter_parts[1]
                    try:
                        value = float(filter_parts[2])
                    except ValueError:
                        continue  # Skip filters with invalid numeric values

                    # Get the average score for the pillar from the precomputed avg scores
                    if pillar in avg_scores['Pillar'].values:
                        avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]
                    else:
                        avg_score = None

                    # Handle NaN case or missing pillar
                    if pd.isna(avg_score) or avg_score is None:
                        include_sheet = False
                        break

                    # Compare avg_score using the operator
                    if operator == '>' and not avg_score > value:
                        include_sheet = False
                        break
                    elif operator == '<' and not avg_score < value:
                        include_sheet = False
                        break
                    elif operator == '=' and not avg_score == value:
                        include_sheet = False
                        break
                    elif operator == '>=' and not avg_score >= value:
                        include_sheet = False
                        break
                    elif operator == '<=' and not avg_score <= value:
                        include_sheet = False
                        break

                except Exception as e:
                    print(f"Filter error: {e}, Filter: {filter_str}")
                    include_sheet = False  # Exclude if error occurs
                    break

        # Only include sheets that pass all filters and have data (non-empty)
        if include_sheet and not df.empty:
            filtered_data_dict[sheet_name] = df

    return filtered_data_dict


@app.route('/', methods=['GET', 'POST'])
def index():
    user = get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))
    
    search_name = request.args.get('search_name', '').lower()  # Convert search input to lowercase
    remove_filter = request.args.get('remove_filter', None)

    # Get filters from cookies
    applied_filters = get_applied_filters(request)

    if remove_filter:
        # Remove the filter if it exists
        applied_filters = [f for f in applied_filters if f != remove_filter]

        # Create response to save updated filters in cookies
        response = make_response(redirect(url_for('index')))
        set_applied_filters(response, applied_filters)
        return response

    if request.method == 'POST':  # Apply filters via POST request
        # Get filter values from the form
        filter_pillar = request.form.get('filter_pillar')
        filter_operator = request.form.get('filter_operator')
        filter_value1 = request.form.get('filter_value1')

        # Construct filter string for display
        filter_str = f"Pillar: {filter_pillar} {filter_operator} {filter_value1}"

        # Append new filter if it doesn't already exist
        if filter_str not in applied_filters:  # Avoid adding duplicates
            applied_filters.append(filter_str)

        # Create response to save applied filters in cookies
        response = make_response(redirect(url_for('index')))
        set_applied_filters(response, applied_filters)
        return response

    # Filter data based on applied filters
    filtered_data_dict = filter_data(data_dict, applied_filters)  # Get the filtered dictionary

    # Remove sheets that do not comply with filters
    sheets_to_display = [sheet_name for sheet_name, data in filtered_data_dict.items() if not data.empty]

    # If a search_name exists, filter only for the exact name
    if search_name:
        matching_sheets = [
            sheet for sheet in sheets_to_display
            if sheet.lower() == search_name  # Ensure case-insensitive exact match
        ]
        sheets_to_display = matching_sheets  # Show only the sheets that match the search_name

    # Pass only the sheets that comply with filters or search_name to the template
    return render_template(
        'index.html',
        pillars=unique_pillars,
        sheets_to_display=sheets_to_display,
        applied_filters=applied_filters,
        data_dict=data_dict,
        search_name=search_name,
        user=user
    )






@app.route('/chart/<sheet_name>')
def generate_chart(sheet_name):
        
    user = get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))
    # Get filters from cookies
    applied_filters = get_applied_filters(request)

    # Check if the sheet exists in the data
    if sheet_name not in data_dict:
        return "Sheet not found", 404

    # Load the data for the specified sheet
    data = data_dict[sheet_name].copy()

    # Ensure the necessary columns exist for filtering and chart generation
    if 'Score' not in data.columns or 'Pillar' not in data.columns:
        return "Invalid data format for chart generation.", 404

    # Compute average scores for pillars
    avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()

    # Apply filters directly within this function
    for filter_str in applied_filters:
        try:
            # Improved parsing of filter strings
            if not filter_str.startswith("Pillar: "):
                continue

            # Extract the pillar, operator, and value using regex
            import re
            match = re.match(r"Pillar: (.+) (>|<|=|>=|<=) ([0-9.]+)", filter_str)
            if not match:
                continue

            pillar = match.group(1).strip()
            operator = match.group(2)
            value = float(match.group(3))

            # Check if the pillar exists in the current sheet's averages
            if pillar not in avg_scores['Pillar'].values:
                return "No data available for the selected filters.", 404

            # Retrieve the average score for the specified pillar
            avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]

            # Apply the filter condition
            if operator == '>' and not avg_score > value:
                return "No data available for the selected filters.", 404
            elif operator == '<' and not avg_score < value:
                return "No data available for the selected filters.", 404
            elif operator == '=' and not avg_score == value:
                return "No data available for the selected filters.", 404
            elif operator == '>=' and not avg_score >= value:
                return "No data available for the selected filters.", 404
            elif operator == '<=' and not avg_score <= value:
                return "No data available for the selected filters.", 404

        except Exception as e:
            print(f"Error applying filter {filter_str}: {e}")
            return "Error applying filters.", 400

    # Generate the radar chart using filtered averages
    fig = go.Figure()
    categories = avg_scores['Pillar'].tolist()
    values = avg_scores['Score'].tolist()

    # Close the loop on radar chart
    categories.append(categories[0])
    values.append(values[0])

    # Add all individual scores to hover data
    hover_data = []
    for pillar in categories:
        pillar_data = data[data['Pillar'] == pillar]
        specific_skills = pillar_data['Specific Skill'].tolist()
        scores = pillar_data['Score'].tolist()
        hover_info = f"Averaged Score: {avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]}<br>"
        hover_info += f"Attribute: {pillar}<br>"
        hover_info += "<br>".join([f"<span style='font-size: 10px;'>{skill}: {score}</span>" for skill, score in zip(specific_skills, scores)])
        hover_data.append(hover_info)

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=sheet_name,
        hoverinfo='text',
        text=hover_data
    ))

    # Extract the utilization value from the first row
    utilization = int((data.loc[0, 'Utilization'] if not data.empty and 'Utilization' in data.columns else 0) *100)
    if utilization <= 50:
        utilization_color = '#6EC664'  # Neutral green
    elif utilization <= 80:
        utilization_color = '#FFCB6B'  # Neutral yellow
    elif utilization <= 95:
        utilization_color = '#DC7633'  # Neutral orange
    else:
        utilization_color = '#E74C3C'  # Neutral red

    # Add utilization bar under the chart
    fig.add_annotation(
        x=0.5,
        y=-0.2,
        text=f"Utilization: {utilization}%",
        showarrow=False,
        font=dict(color=utilization_color, size=12),
        xref="paper",
        yref="paper"
    )

    fig.add_shape(
        type="rect",
        x0=0.25,
        x1=0.75,
        y0=-0.3,
        y1=-0.25,
        fillcolor=utilization_color,
        line=dict(width=0),
        xref="paper",
        yref="paper"
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=6.5)),
            angularaxis=dict(tickfont=dict(size=9))
        ),
        showlegend=False,
    )

    return fig.to_html(full_html=False)



if __name__ == '__main__':
    app.run(debug=True)