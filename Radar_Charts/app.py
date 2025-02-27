from flask import Flask, render_template, request, redirect, url_for, make_response
import pandas as pd
import json
import os
import io
import time
import re
import hashlib
from google.cloud import storage
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import plotly.graph_objects as go

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
BUCKET_NAME = "new-radar-chart-users"
USERS_FILE_NAME = "users.json"

CHECK_INTERVAL = 10

data_dict = {}
pillar_avg_scores_dict = {}
latest_hash = None
last_mod_time = None
last_checked_time = 0
unique_pillars = []

# --------------------------------------------------------------------------------------
# User Management from GCS
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

@app.route('/admin/users', methods=['GET','POST'])
def manage_users():
    user = get_authenticated_user(request)
    if user != ADMIN_EMAIL:
        return redirect(url_for('index'))

    if request.method=='POST':
        action = request.form.get("action")
        email = request.form.get("email")
        password = request.form.get("password")
        if action=="add" and email and password:
            if email not in VALID_USERS:
                VALID_USERS[email] = password
                save_users_to_gcs(VALID_USERS)
        elif action=="edit" and email and password:
            if email in VALID_USERS:
                VALID_USERS[email] = password
                save_users_to_gcs(VALID_USERS)
        elif action=="remove" and email:
            if email in VALID_USERS:
                del VALID_USERS[email]
                save_users_to_gcs(VALID_USERS)

    return render_template('admin.html', users=VALID_USERS, user=user)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form.get('email')
        password = request.form.get('password')
        global VALID_USERS
        VALID_USERS = fetch_users_from_gcs()

        if email in VALID_USERS and VALID_USERS[email]==password:
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie("user_email", email)
            resp.set_cookie("user_password", password)
            return resp
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route('/logout')
def logout():
    resp= make_response(redirect(url_for('login')))
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
            return False
        latest_hash = new_hash

        file_stream.seek(0)
        sheets = pd.ExcelFile(file_stream)

        new_data_dict = {}
        new_pillar_avg_scores_dict = {}
        all_pillars = set()

        for sheet_name in sheets.sheet_names:
            df = sheets.parse(sheet_name)
            # Handle 'Capacity'/'Utilization'
            if 'Capacity' in df.columns and df['Capacity'].dtype == 'object':
                df['Capacity'] = df['Capacity'].str.replace('%','').astype(float)
            if 'Utilization' in df.columns and df['Utilization'].dtype == 'object':
                df['Utilization'] = df['Utilization'].str.replace('%','').astype(float)

            new_data_dict[sheet_name] = df

            if 'Pillar' in df.columns and 'Score' in df.columns:
                avg_scores = df.groupby('Pillar')['Score'].mean().round(1).reset_index()
                new_pillar_avg_scores_dict[sheet_name] = avg_scores
                pillars_in_sheet = df['Pillar'].dropna().unique()
                all_pillars.update(pillars_in_sheet)

        # Instead of merging, we replace the dictionaries
        data_dict = new_data_dict
        pillar_avg_scores_dict = new_pillar_avg_scores_dict

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

def set_applied_filters(resp, applied_filters):
    import json
    resp.set_cookie('applied_filters', json.dumps(applied_filters))

# We unify the same regex used in both filter_data() and generate_chart() to parse the filter
filter_regex = re.compile(r'^Pillar:\s*(.+)\s+(>|<|=|>=|<=)\s+([0-9.]+)$', re.IGNORECASE)

def filter_data(data, applied_filters):
    filtered_data_dict={}
    for sheet_name, df in data.items():
        include_sheet=True
        if 'Pillar' in df.columns and 'Score' in df.columns:
            # Create a local avg_scores with .lower() pillars:
            local_scores = df.copy()
            # We'll store a lowercase pillar for comparison:
            local_scores['lpillar'] = local_scores['Pillar'].str.lower()

            # Build avg of 'Score' by that lowercase pillar
            avg_scores = local_scores.groupby('lpillar')['Score'].mean().round(1)

            # for each filter, parse it
            for filter_str in applied_filters:
                filter_str = filter_str.strip()
                m = filter_regex.match(filter_str)
                if not m:
                    # if it doesn't match "Pillar: X op Y", we skip it
                    continue
                raw_pillar, op, val_str = m.groups()
                raw_pillar = raw_pillar.strip().lower()  # unify lower
                val = float(val_str)
                if raw_pillar not in avg_scores.index:
                    include_sheet=False
                    break
                a = avg_scores[raw_pillar]

                if op=='>' and not (a>val): include_sheet=False; break
                elif op=='<' and not (a<val): include_sheet=False; break
                elif op=='=' and not (a==val): include_sheet=False; break
                elif op=='>=' and not (a>=val): include_sheet=False; break
                elif op=='<=' and not (a<=val): include_sheet=False; break

        if include_sheet and not df.empty:
            filtered_data_dict[sheet_name]=df

    return filtered_data_dict

# --------------------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------------------
@app.route('/', methods=['GET','POST'])
def index():
    user= get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    remove_filter = request.args.get('remove_filter')
    applied_filters= get_applied_filters(request)
    if remove_filter:
        # remove that filter
        applied_filters=[f for f in applied_filters if f!=remove_filter]
        resp= make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    if request.method=='POST':
        fp = request.form.get('filter_pillar','').strip()
        fo = request.form.get('filter_operator','').strip()
        fv = request.form.get('filter_value1','').strip()

        if fp and fo and fv:
            new_filter = f"Pillar: {fp} {fo} {fv}"
            # only add if not already present
            if new_filter not in applied_filters:
                applied_filters.append(new_filter)

        resp= make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    search_name=request.args.get('search_name','').lower()

    return render_template(
        'index.html',
        pillars=unique_pillars,
        applied_filters=applied_filters,
        search_name=search_name,
        user=user
    )

# --------------------------------------------------------------------------------------
# Return how many charts pass filters
# --------------------------------------------------------------------------------------
@app.route('/count_charts')
def count_charts():
    user= get_authenticated_user(request)
    if not user:
        return {"count":0}
    applied_filters= get_applied_filters(request)
    filtered= filter_data(data_dict, applied_filters)
    search_name= request.args.get('search_name','').lower()

    sheets=[s for s,df in filtered.items() if not df.empty]
    # Apply partial match if user typed something
    if search_name:
        search_words = [w.strip() for w in search_name.split() if w.strip()]
        sheets = [
            s for s in sheets
            if all(word in s.lower() for word in search_words)
        ]

    return {"count": len(sheets)}

# --------------------------------------------------------------------------------------
# Single chart route
# --------------------------------------------------------------------------------------
@app.route('/chart/<sheet_name>')
def generate_chart(sheet_name):
    user= get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    if sheet_name not in data_dict:
        return "Sheet not found"

    df = data_dict[sheet_name].copy()
    if 'Score' not in df.columns or 'Pillar' not in df.columns:
        return "Invalid data format for chart generation."

    # Re-check filters
    applied_filters = get_applied_filters(request)
    local = df.copy()
    local['lpillar'] = local['Pillar'].str.lower()
    avg_scores = local.groupby('lpillar')['Score'].mean().round(1)

    for filter_str in applied_filters:
        filter_str=filter_str.strip()
        m = filter_regex.match(filter_str)
        if m:
            raw_pillar, op, val_str = m.groups()
            raw_pillar= raw_pillar.strip().lower()
            val=float(val_str)

            if raw_pillar not in avg_scores.index:
                return "No data available for the selected filters."
            a= avg_scores[raw_pillar]
            if op=='>' and not(a>val): return "No data available for the selected filters."
            elif op=='<' and not(a<val): return "No data available for the selected filters."
            elif op=='=' and not(a==val): return "No data available for the selected filters."
            elif op=='>=' and not(a>=val): return "No data available for the selected filters."
            elif op=='<=' and not(a<=val): return "No data available for the selected filters."


    # Now we want the actual "original pillar" average
    # The old code used:
    raw_avg_df = df.groupby('Pillar')['Score'].mean().round(1).reset_index()

    categories = raw_avg_df['Pillar'].tolist()
    values = raw_avg_df['Score'].tolist()
    categories.append(categories[0])
    values.append(values[0])

    # build hover
    hover_data=[]
    for cat in categories:
        sub= df[df['Pillar']==cat]
        if sub.empty:
            hover_data.append(f"No data for {cat}")
            continue
        sskills=sub['Specific Skill'].tolist()
        scs=sub['Score'].tolist()
        cat_avg = raw_avg_df.loc[raw_avg_df['Pillar']==cat,'Score'].values[0]
        info= f"Averaged Score: {cat_avg}<br>Attribute: {cat}<br>"
        for (sk, scv) in zip(sskills, scs):
            info+=f"<span style='font-size:10px;'>{sk}: {scv}</span><br>"
        hover_data.append(info)

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=categories,
        fill='toself', name=sheet_name,
        hoverinfo='text', text=hover_data
    ))

    def safe_int(x):
        try: return int(round(x))
        except: return 0

    cap_val= safe_int(df.loc[0,'Capacity']*100 if 'Capacity' in df.columns and not df.empty else 0)
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

    cap_col= capacity_color(cap_val)
    util_col= utilization_color(util_val)

    fig.add_annotation(
        x=0.14, y=-0.18,  # between ~-0.23 (original) and -0.15 (new)
        text=f"Capacity: {cap_val}%",
        showarrow=False,
        font=dict(color=cap_col, size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect",
        x0=0.35, 
        x1=0.85,
        y0=-0.18,  # aligns with the label’s y so the bar is to the right
        y1=-0.14,  # a bit of height for the bar
        fillcolor=cap_col,
        line=dict(width=0),
        xref="paper",
        yref="paper"
    )

    fig.add_annotation(
        x=0.14, y=-0.25,  # between ~-0.33 (original) and -0.22 (new)
        text=f"Utilization: {util_val}%",
        showarrow=False,
        font=dict(color=util_col, size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect",
        x0=0.35,
        x1=0.85,
        y0=-0.25,
        y1=-0.21,
        fillcolor=util_col,
        line=dict(width=0),
        xref="paper",
        yref="paper"
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
# Single chart snippet for offset
# --------------------------------------------------------------------------------------
@app.route('/load_one_chart')
def load_one_chart():
    user = get_authenticated_user(request)
    if not user:
        return "Not logged in",401

    offset_str= request.args.get('offset','0')
    search_name= request.args.get('search_name','').lower()
    try:
        offset=int(offset_str)
    except:
        offset=0

    applied_filters = get_applied_filters(request)
    filtered= filter_data(data_dict, applied_filters)
    sheets=[s for s,df in filtered.items() if not df.empty]
    if search_name:
        search_words = search_name.split()
        sheets = [
            s for s in sheets
            if all(word in s.lower() for word in search_words)
        ]

    if offset>= len(sheets):
        return ""

    sheet_name= sheets[offset]
    df= data_dict[sheet_name]

    snippet=f"""
    <iframe src="{url_for('generate_chart', sheet_name=sheet_name)}"
            frameborder="0"
            onload="iframeLoaded(this)"
            style="width:100%; height:450px; display:none;">
    </iframe>
    <p>{sheet_name}</p>
    <button onclick="openPopup('{sheet_name}')">Show Engagements</button>
    <div id="popup-{sheet_name}" class="popup">
        <span class="close-btn" onclick="closePopup('{sheet_name}')">×</span>
        <div class="popup-title">Engagements for {sheet_name}</div>
        <ul>
    """
    if df is not None and 'Engagements' in df.columns and not df['Engagements'].isnull().all():
        all_engagements=set()
        for e_list in df['Engagements']:
            if e_list and isinstance(e_list,str):
                for eng in e_list.split(','):
                    all_engagements.add(eng.strip())
        for eng in sorted(all_engagements):
            snippet += f"<li>{eng}</li>"

    snippet+="</ul></div>"
    return snippet

if __name__=='__main__':
    app.run(debug=True)











