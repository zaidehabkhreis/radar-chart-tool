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



ADMIN_EMAIL = "tariq.khasawneh@devoteam.com"  
DRIVE_FILE_ID = "1ZuIYUnITxC2G7Qrmb6yK_SL3LI40XTpi"

service_account_json = os.getenv("SERVICE_ACCOUNT")

if service_account_json:
    credentials_dict = json.loads(service_account_json) 
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


storage_client = storage.Client() 
BUCKET_NAME = "radar-chart-users"
USERS_FILE_NAME = "users.json"



VALID_USERS = fetch_users_from_gcs()


data_dict = {}
pillar_avg_scores_dict = {}
latest_hash = None
last_checked_time = 0
CHECK_INTERVAL = 60 
unique_pillars = []

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
        return  

    last_checked_time = current_time  

    try:
        request = drive_service.files().get_media(fileId=DRIVE_FILE_ID, supportsAllDrives=True)

        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        new_hash = calculate_file_hash(file_stream)

        if new_hash == latest_hash:
            return  

        latest_hash = new_hash 
        file_stream.seek(0)
        sheets = pd.ExcelFile(file_stream)

        new_data_dict = {sheet_name: sheets.parse(sheet_name) for sheet_name in sheets.sheet_names}
        new_pillar_avg_scores_dict = {}

        all_pillars = set()

        for sheet_name, data in new_data_dict.items():
            if 'Capacity' in data.columns and data['Capacity'].dtype == 'object':
                data['Capacity'] = data['Capacity'].str.replace('%', '').astype(float)
            
            if 'Utilization' in data.columns and data['Utilization'].dtype == 'object':
                data['Utilization'] = data['Utilization'].str.replace('%', '').astype(float)

            if 'Pillar' in data.columns and 'Score' in data.columns:
                avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()
                new_pillar_avg_scores_dict[sheet_name] = avg_scores
                pillars_in_sheet = data['Pillar'].dropna().unique()  
                all_pillars.update(pillars_in_sheet)

        if not all_pillars:
            print("No pillars were found in the Excel file! Check data format.")

        unique_pillars = sorted(all_pillars) if all_pillars else ["No Data"]

        data_dict = new_data_dict
        pillar_avg_scores_dict = new_pillar_avg_scores_dict

    except Exception as e:
        print(f"Error fetching spreadsheet: {e}")



@app.before_request
def check_for_updates():
    """Check for spreadsheet updates before handling any request."""
    fetch_latest_excel_if_updated()

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
        return redirect(url_for('index')) 

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

    for sheet_name, df in data.items(): 
        include_sheet = True  

        if 'Pillar' in df.columns and 'Score' in df.columns:
            avg_scores = pillar_avg_scores_dict.get(sheet_name, pd.DataFrame())

            for filter_str in applied_filters:
                try:
                    
                    filter_parts = filter_str.replace('Pillar: ', '').split(' ', 2)
                    if len(filter_parts) != 3:
                        continue  

                    pillar = filter_parts[0]
                    operator = filter_parts[1]
                    try:
                        value = float(filter_parts[2])
                    except ValueError:
                        continue  

                    if pillar in avg_scores['Pillar'].values:
                        avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]
                    else:
                        avg_score = None

                    if pd.isna(avg_score) or avg_score is None:
                        include_sheet = False
                        break

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
                    include_sheet = False
                    break

        if include_sheet and not df.empty:
            filtered_data_dict[sheet_name] = df

    return filtered_data_dict


@app.route('/', methods=['GET', 'POST'])
def index():
    user = get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))
    
    search_name = request.args.get('search_name', '').lower()  
    remove_filter = request.args.get('remove_filter', None)

    applied_filters = get_applied_filters(request)

    if remove_filter:
        applied_filters = [f for f in applied_filters if f != remove_filter]

        response = make_response(redirect(url_for('index')))
        set_applied_filters(response, applied_filters)
        return response

    if request.method == 'POST': 
        filter_pillar = request.form.get('filter_pillar')
        filter_operator = request.form.get('filter_operator')
        filter_value1 = request.form.get('filter_value1')

        filter_str = f"Pillar: {filter_pillar} {filter_operator} {filter_value1}"

        if filter_str not in applied_filters:  
            applied_filters.append(filter_str)

        response = make_response(redirect(url_for('index')))
        set_applied_filters(response, applied_filters)
        return response

    filtered_data_dict = filter_data(data_dict, applied_filters)

    sheets_to_display = [sheet_name for sheet_name, data in filtered_data_dict.items() if not data.empty]

    if search_name:
        matching_sheets = [
            sheet for sheet in sheets_to_display
            if sheet.lower() == search_name  
        ]
        sheets_to_display = matching_sheets  

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
    applied_filters = get_applied_filters(request)

    if sheet_name not in data_dict:
        return "Sheet not found", 404

    data = data_dict[sheet_name].copy()

    if 'Score' not in data.columns or 'Pillar' not in data.columns:
        return "Invalid data format for chart generation.", 404

    avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()

    for filter_str in applied_filters:
        try:
            if not filter_str.startswith("Pillar: "):
                continue

            import re
            match = re.match(r"Pillar: (.+) (>|<|=|>=|<=) ([0-9.]+)", filter_str)
            if not match:
                continue

            pillar = match.group(1).strip()
            operator = match.group(2)
            value = float(match.group(3))

            if pillar not in avg_scores['Pillar'].values:
                return "No data available for the selected filters.", 404

            avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]

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

    fig = go.Figure()
    categories = avg_scores['Pillar'].tolist()
    values = avg_scores['Score'].tolist()

    categories.append(categories[0])
    values.append(values[0])

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

    capacity = int((data.loc[0, 'Capacity'] if 'Capacity' in data.columns and not data.empty else 0) * 100)
    utilization = int((data.loc[0, 'Utilization'] if 'Utilization' in data.columns and not data.empty else 0) * 100)

    if capacity <= 50:
        capacity_color = '#6EC664'  
    elif capacity <= 80:
        capacity_color = '#FFCB6B'  
    elif capacity <= 95:
        capacity_color = '#DC7633'  
    else:
        capacity_color = '#E74C3C' 


    if utilization <= 50:
        utilization_color = '#E74C3C'  
    elif utilization <= 80:
        utilization_color = '#DC7633'  
    elif utilization <= 95:
        utilization_color = '#FFCB6B'  
    else:
        utilization_color = '#6EC664'

    fig.add_annotation(
        x=0.3,
        y=-0.2,
        text=f"Capacity: {capacity}%",
        showarrow=False,
        font=dict(color=capacity_color, size=12),
        xref="paper",
        yref="paper"
    )

    fig.add_shape(
        type="rect",
        x0=0.05,
        x1=0.25,
        y0=-0.3,
        y1=-0.25,
        fillcolor=capacity_color,
        line=dict(width=0),
        xref="paper",
        yref="paper"
    )

    fig.add_annotation(
        x=0.7,
        y=-0.2,
        text=f"Utilization: {utilization}%",
        showarrow=False,
        font=dict(color=utilization_color, size=12),
        xref="paper",
        yref="paper"
    )

    fig.add_shape(
        type="rect",
        x0=0.55,
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
