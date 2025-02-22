# from flask import Flask, render_template, request, redirect, url_for, make_response
# import pandas as pd
# import plotly.graph_objects as go
# import json
# import os
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseDownload
# from google.oauth2 import service_account
# import io
# import time
# import hashlib
# from google.cloud import storage



# app = Flask(__name__)



# ADMIN_EMAIL = "tariq.khasawneh@devoteam.com"  
# DRIVE_FILE_ID = "1ZuIYUnITxC2G7Qrmb6yK_SL3LI40XTpi"


# service_account_json = os.getenv("SERVICE_ACCOUNT")

# if service_account_json:
#     credentials_dict = json.loads(service_account_json) 
#     credentials = service_account.Credentials.from_service_account_info(credentials_dict)
# else:
#     raise Exception("Missing SERVICE_ACCOUNT environment variable")

# drive_service = build("drive", "v3", credentials=credentials)


# def fetch_users_from_gcs():
#     """Fetch the users JSON file from Google Cloud Storage."""
#     bucket = storage_client.bucket(BUCKET_NAME)
#     blob = bucket.blob(USERS_FILE_NAME)

#     if not blob.exists():
#         raise Exception(f"Users file {USERS_FILE_NAME} not found in bucket {BUCKET_NAME}")

#     users_json = blob.download_as_text()
#     users_data = json.loads(users_json)
#     return {user["email"]: user["password"] for user in users_data["users"]}

# def save_users_to_gcs(users_dict):
#     """Save the updated users JSON file back to Google Cloud Storage."""
#     bucket = storage_client.bucket(BUCKET_NAME)
#     blob = bucket.blob(USERS_FILE_NAME)

#     users_data = {"users": [{"email": email, "password": password} for email, password in users_dict.items()]}
#     blob.upload_from_string(json.dumps(users_data, indent=4), content_type="application/json")


# storage_client = storage.Client() 
# BUCKET_NAME = "radar-chart-users"
# USERS_FILE_NAME = "users.json"



# VALID_USERS = fetch_users_from_gcs()


# data_dict = {}
# pillar_avg_scores_dict = {}
# latest_hash = None
# last_checked_time = 0
# CHECK_INTERVAL = 60 
# unique_pillars = []

# def calculate_file_hash(file_stream):
#     """Compute the hash of the file to detect changes."""
#     file_stream.seek(0)
#     hasher = hashlib.md5()
#     while chunk := file_stream.read(8192):
#         hasher.update(chunk)
#     return hasher.hexdigest()

# def fetch_latest_excel_if_updated():
#     """Fetch the latest spreadsheet from Google Drive only if an update exists."""
#     global latest_hash, data_dict, pillar_avg_scores_dict, unique_pillars, last_checked_time

#     current_time = time.time()
#     if current_time - last_checked_time < CHECK_INTERVAL:
#         return False  # No need to check again within the interval

#     last_checked_time = current_time  

#     try:
#         request = drive_service.files().get_media(fileId=DRIVE_FILE_ID, supportsAllDrives=True)
#         file_stream = io.BytesIO()
#         downloader = MediaIoBaseDownload(file_stream, request)
#         done = False
#         while not done:
#             _, done = downloader.next_chunk()

#         new_hash = calculate_file_hash(file_stream)

#         if new_hash == latest_hash:
#             return False  # No update detected, skip reloading data

#         latest_hash = new_hash  # Update the stored hash
#         file_stream.seek(0)
#         sheets = pd.ExcelFile(file_stream)

#         new_data_dict = {sheet_name: sheets.parse(sheet_name) for sheet_name in sheets.sheet_names}
#         new_pillar_avg_scores_dict = {}

#         all_pillars = set()

#         for sheet_name, data in new_data_dict.items():
#             if 'Capacity' in data.columns and data['Capacity'].dtype == 'object':
#                 data['Capacity'] = data['Capacity'].str.replace('%', '').astype(float)
            
#             if 'Utilization' in data.columns and data['Utilization'].dtype == 'object':
#                 data['Utilization'] = data['Utilization'].str.replace('%', '').astype(float)

#             if 'Pillar' in data.columns and 'Score' in data.columns:
#                 avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()
#                 new_pillar_avg_scores_dict[sheet_name] = avg_scores
#                 pillars_in_sheet = data['Pillar'].dropna().unique()  
#                 all_pillars.update(pillars_in_sheet)

#         unique_pillars = sorted(all_pillars) if all_pillars else ["No Data"]

#         # Update global variables only if data has changed
#         data_dict.update(new_data_dict)
#         pillar_avg_scores_dict.update(new_pillar_avg_scores_dict)

#         return True  # Return True to indicate new data was loaded

#     except Exception as e:
#         print(f"Error fetching spreadsheet: {e}")
#         return False




# @app.before_request
# def check_for_updates():
#     """Check for spreadsheet updates only when needed."""
#     fetch_latest_excel_if_updated()  

# def get_authenticated_user(request):
#     """Check if the user is authenticated via cookies."""
#     email = request.cookies.get("user_email")
#     password = request.cookies.get("user_password")

#     if email in VALID_USERS and VALID_USERS[email] == password:
#         return email
#     return None


# @app.route('/admin/users', methods=['GET', 'POST'])
# def manage_users():
#     """Admin panel for managing users."""
#     user = get_authenticated_user(request)
#     if user != ADMIN_EMAIL:
#         return redirect(url_for('index')) 

#     if request.method == 'POST':
#         action = request.form.get("action")
#         email = request.form.get("email")
#         password = request.form.get("password")

#         if action == "add" and email and password:
#             if email not in VALID_USERS:
#                 VALID_USERS[email] = password
#                 save_users_to_gcs(VALID_USERS)

#         elif action == "edit" and email and password:
#             if email in VALID_USERS:
#                 VALID_USERS[email] = password
#                 save_users_to_gcs(VALID_USERS)

#         elif action == "remove" and email:
#             if email in VALID_USERS:
#                 del VALID_USERS[email]
#                 save_users_to_gcs(VALID_USERS)

#     return render_template('admin.html', users=VALID_USERS, user=user)



# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         password = request.form.get('password')

        
#         global VALID_USERS
#         VALID_USERS = fetch_users_from_gcs()

#         if email in VALID_USERS and VALID_USERS[email] == password:
#             response = make_response(redirect(url_for('index')))
#             response.set_cookie("user_email", email)
#             response.set_cookie("user_password", password)
#             return response
#         else:
#             return render_template("login.html", error="Invalid email or password")

#     return render_template("login.html")

# @app.route('/logout')
# def logout():
#     """Logout user by clearing cookies."""
#     response = make_response(redirect(url_for('login')))
#     response.delete_cookie("user_email")
#     response.delete_cookie("user_password")
#     return response

# def get_applied_filters(request):
#     """Retrieve filters from cookies"""
#     applied_filters = request.cookies.get('applied_filters', '[]')
#     return json.loads(applied_filters)

# def set_applied_filters(response, applied_filters):
#     """Set filters in cookies"""
#     response.set_cookie('applied_filters', json.dumps(applied_filters))

# def filter_data(data, applied_filters):
#     """Apply all filters to the given data."""
#     filtered_data_dict = {}

#     for sheet_name, df in data.items(): 
#         include_sheet = True  

#         if 'Pillar' in df.columns and 'Score' in df.columns:
#             avg_scores = pillar_avg_scores_dict.get(sheet_name, pd.DataFrame())

#             for filter_str in applied_filters:
#                 try:
                    
#                     filter_parts = filter_str.replace('Pillar: ', '').split(' ', 2)
#                     if len(filter_parts) != 3:
#                         continue  

#                     pillar = filter_parts[0]
#                     operator = filter_parts[1]
#                     try:
#                         value = float(filter_parts[2])
#                     except ValueError:
#                         continue  

#                     if pillar in avg_scores['Pillar'].values:
#                         avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]
#                     else:
#                         avg_score = None

#                     if pd.isna(avg_score) or avg_score is None:
#                         include_sheet = False
#                         break

#                     if operator == '>' and not avg_score > value:
#                         include_sheet = False
#                         break
#                     elif operator == '<' and not avg_score < value:
#                         include_sheet = False
#                         break
#                     elif operator == '=' and not avg_score == value:
#                         include_sheet = False
#                         break
#                     elif operator == '>=' and not avg_score >= value:
#                         include_sheet = False
#                         break
#                     elif operator == '<=' and not avg_score <= value:
#                         include_sheet = False
#                         break

#                 except Exception as e:
#                     print(f"Filter error: {e}, Filter: {filter_str}")
#                     include_sheet = False
#                     break

#         if include_sheet and not df.empty:
#             filtered_data_dict[sheet_name] = df

#     return filtered_data_dict


# @app.route('/', methods=['GET', 'POST'])
# def index():
#     user = get_authenticated_user(request)
#     if not user:
#         return redirect(url_for('login'))

#     # Check for updates only once before rendering
#     fetch_latest_excel_if_updated()

#     search_name = request.args.get('search_name', '').lower()  
#     remove_filter = request.args.get('remove_filter', None)

#     applied_filters = get_applied_filters(request)

#     if remove_filter:
#         applied_filters = [f for f in applied_filters if f != remove_filter]
#         response = make_response(redirect(url_for('index')))
#         set_applied_filters(response, applied_filters)
#         return response

#     if request.method == 'POST': 
#         filter_pillar = request.form.get('filter_pillar')
#         filter_operator = request.form.get('filter_operator')
#         filter_value1 = request.form.get('filter_value1')

#         filter_str = f"Pillar: {filter_pillar} {filter_operator} {filter_value1}"

#         if filter_str not in applied_filters:  
#             applied_filters.append(filter_str)

#         response = make_response(redirect(url_for('index')))
#         set_applied_filters(response, applied_filters)
#         return response

#     # Use cached data unless updates are detected
#     filtered_data_dict = filter_data(data_dict, applied_filters)

#     sheets_to_display = [sheet_name for sheet_name, data in filtered_data_dict.items() if not data.empty]

#     if search_name:
#         sheets_to_display = [sheet for sheet in sheets_to_display if sheet.lower() == search_name]

#     return render_template(
#         'index.html',
#         pillars=unique_pillars,
#         sheets_to_display=sheets_to_display,
#         applied_filters=applied_filters,
#         data_dict=data_dict,
#         search_name=search_name,
#         user=user
#     )






# @app.route('/chart/<sheet_name>')
# def generate_chart(sheet_name):
        
#     user = get_authenticated_user(request)
#     if not user:
#         return redirect(url_for('login'))
#     applied_filters = get_applied_filters(request)

#     if sheet_name not in data_dict:
#         return "Sheet not found", 404

#     data = data_dict[sheet_name].copy()

#     if 'Score' not in data.columns or 'Pillar' not in data.columns:
#         return "Invalid data format for chart generation.", 404

#     avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()

#     for filter_str in applied_filters:
#         try:
#             if not filter_str.startswith("Pillar: "):
#                 continue

#             import re
#             match = re.match(r"Pillar: (.+) (>|<|=|>=|<=) ([0-9.]+)", filter_str)
#             if not match:
#                 continue

#             pillar = match.group(1).strip()
#             operator = match.group(2)
#             value = float(match.group(3))

#             if pillar not in avg_scores['Pillar'].values:
#                 return "No data available for the selected filters.", 404

#             avg_score = avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]

#             if operator == '>' and not avg_score > value:
#                 return "No data available for the selected filters.", 404
#             elif operator == '<' and not avg_score < value:
#                 return "No data available for the selected filters.", 404
#             elif operator == '=' and not avg_score == value:
#                 return "No data available for the selected filters.", 404
#             elif operator == '>=' and not avg_score >= value:
#                 return "No data available for the selected filters.", 404
#             elif operator == '<=' and not avg_score <= value:
#                 return "No data available for the selected filters.", 404

#         except Exception as e:
#             print(f"Error applying filter {filter_str}: {e}")
#             return "Error applying filters.", 400

#     fig = go.Figure()
#     categories = avg_scores['Pillar'].tolist()
#     values = avg_scores['Score'].tolist()

#     categories.append(categories[0])
#     values.append(values[0])

#     hover_data = []
#     for pillar in categories:
#         pillar_data = data[data['Pillar'] == pillar]
#         specific_skills = pillar_data['Specific Skill'].tolist()
#         scores = pillar_data['Score'].tolist()
#         hover_info = f"Averaged Score: {avg_scores.loc[avg_scores['Pillar'] == pillar, 'Score'].values[0]}<br>"
#         hover_info += f"Attribute: {pillar}<br>"
#         hover_info += "<br>".join([f"<span style='font-size: 10px;'>{skill}: {score}</span>" for skill, score in zip(specific_skills, scores)])
#         hover_data.append(hover_info)

#     fig.add_trace(go.Scatterpolar(
#         r=values,
#         theta=categories,
#         fill='toself',
#         name=sheet_name,
#         hoverinfo='text',
#         text=hover_data
#     ))

#     capacity = int((data.loc[0, 'Capacity'] if 'Capacity' in data.columns and not data.empty else 0) * 100)
#     utilization = int((data.loc[0, 'Utilization'] if 'Utilization' in data.columns and not data.empty else 0) * 100)

#     if capacity <= 50:
#         capacity_color = '#6EC664'  
#     elif capacity <= 80:
#         capacity_color = '#FFCB6B'  
#     elif capacity <= 95:
#         capacity_color = '#DC7633'  
#     else:
#         capacity_color = '#E74C3C' 

#     if utilization <= 50:
#         utilization_color = '#E74C3C'  
#     elif utilization <= 80:
#         utilization_color = '#DC7633'  
#     elif utilization <= 95:
#         utilization_color = '#FFCB6B'  
#     else:
#         utilization_color = '#6EC664'

#     fig.add_annotation(
#         x=0.08,
#         y=-0.25,
#         text=f"Capacity: {capacity}%",
#         showarrow=False,
#         font=dict(color=capacity_color, size=12),
#         xref="paper",
#         yref="paper"
#     )

#     fig.add_shape(
#         type="rect",
#         x0=0.35,
#         x1=0.85,
#         y0=-0.23,
#         y1=-0.19,
#         fillcolor=capacity_color,
#         line=dict(width=0),
#         xref="paper",
#         yref="paper"
#     )

#     fig.add_annotation(
#         x=0.07,
#         y=-0.35,
#         text=f"Utilization: {utilization}%",
#         showarrow=False,
#         font=dict(color=utilization_color, size=12),
#         xref="paper",
#         yref="paper"
#     )

#     fig.add_shape(
#         type="rect",
#         x0=0.35,
#         x1=0.85,
#         y0=-0.33,
#         y1=-0.29,
#         fillcolor=utilization_color,
#         line=dict(width=0),
#         xref="paper",
#         yref="paper"
#     )

#     fig.update_layout(
#         polar=dict(
#             radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=6.5)),
#             angularaxis=dict(tickfont=dict(size=9))
#         ),
#         showlegend=False,
#     )

#     return fig.to_html(full_html=False)


# if __name__ == '__main__':
#     app.run(debug=True)






from flask import Flask, render_template, request, redirect, url_for, make_response
import pandas as pd
import json
import os
import io
import time
import hashlib
from google.cloud import storage
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

app = Flask(__name__)

# --------------------------------------------------------------------------------------
# Configuration / Globals
# --------------------------------------------------------------------------------------
ADMIN_EMAIL = "tariq.khasawneh@devoteam.com"
DRIVE_FILE_ID = "1ZuIYUnITxC2G7Qrmb6yK_SL3LI40XTpi"

service_account_json = os.getenv("SERVICE_ACCOUNT")
if service_account_json:
    credentials_dict = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
else:
    raise Exception("Missing SERVICE_ACCOUNT environment variable")

drive_service = build("drive", "v3", credentials=credentials)

storage_client = storage.Client()
BUCKET_NAME = "radar-chart-users"
USERS_FILE_NAME = "users.json"

CHECK_INTERVAL = 60  # how often we check Google Drive for updates (seconds)

data_dict = {}                 # { sheet_name -> DataFrame }
pillar_avg_scores_dict = {}    # { sheet_name -> DataFrame of Pillar vs average Score }
latest_hash = None
last_checked_time = 0
unique_pillars = []

# --------------------------------------------------------------------------------------
# User management from GCS
# --------------------------------------------------------------------------------------
def fetch_users_from_gcs():
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(USERS_FILE_NAME)
    if not blob.exists():
        raise Exception(f"Users file {USERS_FILE_NAME} not found in bucket {BUCKET_NAME}")

    users_json = blob.download_as_text()
    users_data = json.loads(users_json)
    return {u["email"]: u["password"] for u in users_data["users"]}

def save_users_to_gcs(users_dict):
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(USERS_FILE_NAME)
    users_data = {"users": [{"email": e, "password": p} for e, p in users_dict.items()]}
    blob.upload_from_string(json.dumps(users_data, indent=4), content_type="application/json")

VALID_USERS = fetch_users_from_gcs()

def get_authenticated_user(request):
    email = request.cookies.get("user_email")
    password = request.cookies.get("user_password")
    if email in VALID_USERS and VALID_USERS[email] == password:
        return email
    return None

@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
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
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie("user_email", email)
            resp.set_cookie("user_password", password)
            return resp
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie("user_email")
    resp.delete_cookie("user_password")
    return resp

# --------------------------------------------------------------------------------------
# Google Drive + Data loading
# --------------------------------------------------------------------------------------
def calculate_file_hash(file_stream):
    file_stream.seek(0)
    hasher = hashlib.md5()
    while True:
        chunk = file_stream.read(8192)
        if not chunk:
            break
        hasher.update(chunk)
    return hasher.hexdigest()

def fetch_latest_excel_if_updated():
    """Fetch the latest spreadsheet from Google Drive only if an update is detected."""
    global latest_hash, data_dict, pillar_avg_scores_dict, unique_pillars, last_checked_time
    current_time = time.time()
    if current_time - last_checked_time < CHECK_INTERVAL:
        return False
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
            return False  # no update

        latest_hash = new_hash
        file_stream.seek(0)
        sheets = pd.ExcelFile(file_stream)

        new_data_dict = {}
        new_pillar_avg_scores_dict = {}
        all_pillars = set()

        for sheet_name in sheets.sheet_names:
            df = sheets.parse(sheet_name)

            # Clean capacity/utilization columns if present
            if 'Capacity' in df.columns and df['Capacity'].dtype == 'object':
                df['Capacity'] = df['Capacity'].str.replace('%','').astype(float)
            if 'Utilization' in df.columns and df['Utilization'].dtype == 'object':
                df['Utilization'] = df['Utilization'].str.replace('%','').astype(float)

            new_data_dict[sheet_name] = df

            # Compute avg scores
            if 'Pillar' in df.columns and 'Score' in df.columns:
                avg_scores = df.groupby('Pillar')['Score'].mean().round(1).reset_index()
                new_pillar_avg_scores_dict[sheet_name] = avg_scores
                pillars_in_sheet = df['Pillar'].dropna().unique()
                all_pillars.update(pillars_in_sheet)

        data_dict.update(new_data_dict)
        pillar_avg_scores_dict.update(new_pillar_avg_scores_dict)

        unique_pillars.clear()
        if all_pillars:
            unique_pillars.extend(sorted(all_pillars))
        else:
            unique_pillars.append("No Data")

        return True
    except Exception as e:
        print("Error fetching spreadsheet:", e)
        return False

@app.before_request
def check_for_updates():
    fetch_latest_excel_if_updated()

# --------------------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------------------
def get_applied_filters(request):
    af_str = request.cookies.get('applied_filters','[]')
    return json.loads(af_str)

def set_applied_filters(response, applied_filters):
    response.set_cookie('applied_filters', json.dumps(applied_filters))

def filter_data(data, applied_filters):
    """Apply all Pillar-based filters to produce a dict of {sheet_name -> DataFrame}."""
    filtered_data_dict = {}
    for sheet_name, df in data.items():
        include_sheet = True
        if 'Pillar' in df.columns and 'Score' in df.columns:
            avg_scores = pillar_avg_scores_dict.get(sheet_name, pd.DataFrame())
            for filter_str in applied_filters:
                try:
                    parts = filter_str.replace('Pillar: ','').split(' ',2)
                    if len(parts)!=3:
                        continue
                    pillar, op, val_str = parts
                    val = float(val_str)

                    if pillar in avg_scores['Pillar'].values:
                        avg_score = avg_scores.loc[avg_scores['Pillar']==pillar,'Score'].values[0]
                    else:
                        avg_score = None
                    if pd.isna(avg_score) or avg_score is None:
                        include_sheet=False
                        break

                    if op=='>' and not avg_score>val: include_sheet=False; break
                    elif op=='<' and not avg_score<val: include_sheet=False; break
                    elif op=='=' and not avg_score==val: include_sheet=False; break
                    elif op=='>=' and not avg_score>=val: include_sheet=False; break
                    elif op=='<=' and not avg_score<=val: include_sheet=False; break
                except Exception as e:
                    print("Filter error:", e, "Filter:", filter_str)
                    include_sheet=False
                    break

        if include_sheet and not df.empty:
            filtered_data_dict[sheet_name] = df

    return filtered_data_dict

# --------------------------------------------------------------------------------------
# Main index (rendering index.html)
# --------------------------------------------------------------------------------------
@app.route('/', methods=['GET','POST'])
def index():
    user = get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    # removing a filter via URL param
    remove_filter = request.args.get('remove_filter')
    applied_filters = get_applied_filters(request)
    if remove_filter:
        applied_filters = [f for f in applied_filters if f!=remove_filter]
        resp = make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    # adding a filter
    if request.method=='POST':
        fp = request.form.get('filter_pillar')
        fo = request.form.get('filter_operator')
        fv = request.form.get('filter_value1')
        fstr = f"Pillar: {fp} {fo} {fv}"
        if fstr not in applied_filters:
            applied_filters.append(fstr)
        resp = make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    search_name = request.args.get('search_name','').lower()

    # We do NOT load all charts here; we only render the template with filters/pillars.
    return render_template(
        'index.html',
        pillars=unique_pillars,
        applied_filters=applied_filters,
        search_name=search_name,
        user=user
    )

# --------------------------------------------------------------------------------------
# Count how many charts exist after filtering + searching
# --------------------------------------------------------------------------------------
@app.route('/count_charts')
def count_charts():
    user = get_authenticated_user(request)
    if not user:
        return {"count": 0}
    applied_filters = get_applied_filters(request)
    filtered = filter_data(data_dict, applied_filters)
    search_name = request.args.get('search_name','').lower()

    # get all valid sheets
    sheets = [s for s, df in filtered.items() if not df.empty]
    if search_name:
        sheets = [s for s in sheets if s.lower()==search_name]

    return {"count": len(sheets)}

# --------------------------------------------------------------------------------------
# Single chart generation for each <iframe>
# --------------------------------------------------------------------------------------
@app.route('/chart/<sheet_name>')
def generate_chart(sheet_name):
    user = get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    if sheet_name not in data_dict:
        return "Sheet not found", 404

    df = data_dict[sheet_name].copy()
    if 'Score' not in df.columns or 'Pillar' not in df.columns:
        return "Invalid data format for chart generation.", 404

    # Check if filter disqualifies this sheet
    applied_filters = get_applied_filters(request)
    avg_scores = df.groupby('Pillar')['Score'].mean().round(1).reset_index()

    import re
    for filter_str in applied_filters:
        if not filter_str.startswith("Pillar: "):
            continue
        match = re.match(r"Pillar:\s*(.+)\s+(>|<|=|>=|<=)\s+([0-9.]+)", filter_str)
        if match:
            pillar, op, val_str = match.groups()
            val = float(val_str)
            if pillar not in avg_scores['Pillar'].values:
                return "No data available for the selected filters.", 404
            sc = avg_scores.loc[avg_scores['Pillar']==pillar,'Score'].values[0]
            if op=='>' and not sc>val: return "No data available for the selected filters.", 404
            elif op=='<' and not sc<val: return "No data available for the selected filters.", 404
            elif op=='=' and not sc==val: return "No data available for the selected filters.", 404
            elif op=='>=' and not sc>=val: return "No data available for the selected filters.", 404
            elif op=='<=' and not sc<=val: return "No data available for the selected filters.", 404

    # Build the radar chart via Plotly
    import plotly.graph_objects as go
    fig = go.Figure()
    categories = avg_scores['Pillar'].tolist()
    values = avg_scores['Score'].tolist()
    categories.append(categories[0])
    values.append(values[0])

    # Hover data
    hover_data = []
    for cat in categories:
        if cat not in df['Pillar'].values:
            hover_data.append(f"No data for {cat}")
            continue
        cat_df = df[df['Pillar'] == cat]
        sskills = cat_df['Specific Skill'].tolist()
        scs = cat_df['Score'].tolist()
        cat_avg = avg_scores.loc[avg_scores['Pillar']==cat,'Score'].values[0] if cat in avg_scores['Pillar'].values else 'N/A'
        info = f"Averaged Score: {cat_avg}<br>Attribute: {cat}<br>"
        for sk, scv in zip(sskills, scs):
            info+=f"<span style='font-size:10px;'>{sk}: {scv}</span><br>"
        hover_data.append(info)

    fig.add_trace(go.Scatterpolar(
        r=values, theta=categories,
        fill='toself', name=sheet_name,
        hoverinfo='text', text=hover_data
    ))

    def safe_int(x):
        try: return int(round(x))
        except: return 0
    cap_val = safe_int(df.loc[0,'Capacity']*100 if 'Capacity' in df.columns and not df.empty else 0)
    util_val= safe_int(df.loc[0,'Utilization']*100 if 'Utilization' in df.columns and not df.empty else 0)

    def capacity_color(c):
        if c<=50: return '#6EC664'
        elif c<=80: return '#FFCB6B'
        elif c<=95: return '#DC7633'
        else: return '#E74C3C'
    def utilization_color(u):
        if u<=50: return '#E74C3C'
        elif u<=80: return '#DC7633'
        elif u<=95: return '#FFCB6B'
        else: return '#6EC664'

    cap_col = capacity_color(cap_val)
    util_col = utilization_color(util_val)

    fig.add_annotation(
        x=0.14, y=-0.25,
        text=f"Capacity: {cap_val}%", showarrow=False,
        font=dict(color=cap_col,size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect", x0=0.35, x1=0.85,
        y0=-0.23, y1=-0.19,
        fillcolor=cap_col, line=dict(width=0),
        xref="paper", yref="paper"
    )

    fig.add_annotation(
        x=0.14, y=-0.35,
        text=f"Utilization: {util_val}%", showarrow=False,
        font=dict(color=util_col,size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect", x0=0.35, x1=0.85,
        y0=-0.33, y1=-0.29,
        fillcolor=util_col, line=dict(width=0),
        xref="paper", yref="paper"
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0,10], tickfont=dict(size=6.5)),
            angularaxis=dict(tickfont=dict(size=9))
        ),
        showlegend=False
    )
    return fig.to_html(full_html=False)

# --------------------------------------------------------------------------------------
# Return exactly ONE chart snippet at given offset (or "" if no more charts)
# --------------------------------------------------------------------------------------
@app.route('/load_one_chart')
def load_one_chart():
    user = get_authenticated_user(request)
    if not user:
        return "Not logged in", 401

    offset_str = request.args.get('offset','0')
    search_name = request.args.get('search_name','').lower()
    try:
        offset = int(offset_str)
    except:
        offset = 0

    applied_filters = get_applied_filters(request)
    filtered = filter_data(data_dict, applied_filters)
    sheets = [s for s, df in filtered.items() if not df.empty]
    if search_name:
        sheets = [s for s in sheets if s.lower() == search_name]

    if offset >= len(sheets):
        return ""  # no more charts at this offset

    sheet_name = sheets[offset]
    df = data_dict[sheet_name]

    # We do not add another .chart wrapper here (the placeholders have it).
    snippet = f"""
    <div class="chart-mid">
        <iframe src="{url_for('generate_chart', sheet_name=sheet_name)}" frameborder="0"></iframe>
    </div>
    <p>{sheet_name}</p>
    <button onclick="openPopup('{sheet_name}')">Show Engagements</button>
    <div id="popup-{sheet_name}" class="popup">
        <span class="close-btn" onclick="closePopup('{sheet_name}')">×</span>
        <div class="popup-title">Engagements for {sheet_name}</div>
        <ul>
    """
    if df is not None and 'Engagements' in df.columns and not df['Engagements'].isnull().all():
        all_engagements = set()
        for e_list in df['Engagements']:
            if e_list and isinstance(e_list,str):
                for eng in e_list.split(','):
                    all_engagements.add(eng.strip())
        for eng in sorted(all_engagements):
            snippet += f"<li>{eng}</li>"

    snippet += """
        </ul>
    </div>
    """
    return snippet

if __name__ == '__main__':
    app.run(debug=True)












