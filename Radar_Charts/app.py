"""
Radar Chart Generator - Flask Application

A web application for visualizing employee skills as radar charts
with an AI-powered staffing assistant.
"""
import re
import json
from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
import plotly.graph_objects as go

from .config import Config
from .services import AuthService, DataService, ChatService

# --------------------------------------------------------------------------------------
# Application Factory
# --------------------------------------------------------------------------------------
app = Flask(__name__)

# Initialize services
credentials = Config.get_credentials()
auth_service = AuthService()
data_service = DataService(credentials)
chat_service = ChatService(data_service)

# Filter regex pattern
FILTER_REGEX = re.compile(r'^Pillar:\s*(.+)\s+(>|<|=|>=|<=)\s+([0-9.]+)$', re.IGNORECASE)


# --------------------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------------------
def get_applied_filters(req):
    """Get applied filters from cookies."""
    af_str = req.cookies.get('applied_filters', '[]')
    return json.loads(af_str)


def set_applied_filters(resp, applied_filters):
    """Set applied filters in cookies."""
    resp.set_cookie('applied_filters', json.dumps(applied_filters))


def filter_data(data, applied_filters):
    """Filter data based on applied pillar filters."""
    filtered_data_dict = {}

    for sheet_name, df in data.items():
        include_sheet = True

        if 'Pillar' in df.columns and 'Score' in df.columns:
            local_scores = df.copy()
            local_scores['lpillar'] = local_scores['Pillar'].str.lower()
            avg_scores = local_scores.groupby('lpillar')['Score'].mean().round(1)

            for filter_str in applied_filters:
                match = FILTER_REGEX.match(filter_str.strip())
                if not match:
                    continue

                raw_pillar, op, val_str = match.groups()
                raw_pillar = raw_pillar.strip().lower()
                val = float(val_str)

                if raw_pillar not in avg_scores.index:
                    include_sheet = False
                    break

                score = avg_scores[raw_pillar]
                if not _evaluate_filter(score, op, val):
                    include_sheet = False
                    break

        if include_sheet and not df.empty:
            filtered_data_dict[sheet_name] = df

    return filtered_data_dict


def _evaluate_filter(score, operator, value):
    """Evaluate a filter condition."""
    operations = {
        '>': lambda a, b: a > b,
        '<': lambda a, b: a < b,
        '=': lambda a, b: a == b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
    }
    return operations.get(operator, lambda a, b: True)(score, value)


# --------------------------------------------------------------------------------------
# Before Request Hook
# --------------------------------------------------------------------------------------
@app.before_request
def check_for_updates():
    """Check for data updates before each request."""
    data_service.fetch_if_updated()


# --------------------------------------------------------------------------------------
# Authentication Routes
# --------------------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        auth_service.refresh_users()

        if auth_service.validate_user(email, password):
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie("user_email", email)
            resp.set_cookie("user_password", password)
            return resp
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")


@app.route('/logout')
def logout():
    """Handle user logout."""
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie("user_email")
    resp.delete_cookie("user_password")
    return resp


# --------------------------------------------------------------------------------------
# Admin Routes
# --------------------------------------------------------------------------------------
@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    """Admin panel for user management."""
    user = auth_service.get_authenticated_user(request)
    if not auth_service.is_admin(user):
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get("action")
        email = request.form.get("email")
        password = request.form.get("password")

        if action == "add" and email and password:
            auth_service.add_user(email, password)
        elif action == "edit" and email and password:
            auth_service.update_user(email, password)
        elif action == "remove" and email:
            auth_service.remove_user(email)

    return render_template('admin.html', users=auth_service.get_all_users(), user=user)


# --------------------------------------------------------------------------------------
# Main Routes
# --------------------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    """Main dashboard page."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    # Handle filter removal
    remove_filter = request.args.get('remove_filter')
    applied_filters = get_applied_filters(request)

    if remove_filter:
        applied_filters = [f for f in applied_filters if f != remove_filter]
        resp = make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    # Handle new filter
    if request.method == 'POST':
        fp = request.form.get('filter_pillar', '').strip()
        fo = request.form.get('filter_operator', '').strip()
        fv = request.form.get('filter_value1', '').strip()

        if fp and fo and fv:
            new_filter = f"Pillar: {fp} {fo} {fv}"
            if new_filter not in applied_filters:
                applied_filters.append(new_filter)

        resp = make_response(redirect(url_for('index')))
        set_applied_filters(resp, applied_filters)
        return resp

    search_name = request.args.get('search_name', '').lower()

    return render_template(
        'index.html',
        pillars=data_service.unique_pillars,
        applied_filters=applied_filters,
        search_name=search_name,
        user=user,
        chat_enabled=chat_service.is_available()
    )


@app.route('/count_charts')
def count_charts():
    """Return count of charts matching current filters."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return {"count": 0}

    applied_filters = get_applied_filters(request)
    filtered = filter_data(data_service.data_dict, applied_filters)
    search_name = request.args.get('search_name', '').lower()

    sheets = [s for s, df in filtered.items() if not df.empty]

    if search_name:
        search_words = [w.strip() for w in search_name.split() if w.strip()]
        sheets = [s for s in sheets if all(word in s.lower() for word in search_words)]

    return {"count": len(sheets)}


# --------------------------------------------------------------------------------------
# Chart Routes
# --------------------------------------------------------------------------------------
@app.route('/chart/<sheet_name>')
def generate_chart(sheet_name):
    """Generate a radar chart for a specific employee."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return redirect(url_for('login'))

    if sheet_name not in data_service.data_dict:
        return "Sheet not found"

    df = data_service.data_dict[sheet_name].copy()

    if 'Score' not in df.columns or 'Pillar' not in df.columns:
        return "Invalid data format for chart generation."

    # Verify filters
    applied_filters = get_applied_filters(request)
    local = df.copy()
    local['lpillar'] = local['Pillar'].str.lower()
    avg_scores = local.groupby('lpillar')['Score'].mean().round(1)

    for filter_str in applied_filters:
        match = FILTER_REGEX.match(filter_str.strip())
        if match:
            raw_pillar, op, val_str = match.groups()
            raw_pillar = raw_pillar.strip().lower()
            val = float(val_str)

            if raw_pillar not in avg_scores.index:
                return "No data available for the selected filters."

            if not _evaluate_filter(avg_scores[raw_pillar], op, val):
                return "No data available for the selected filters."

    # Build chart
    raw_avg_df = df.groupby('Pillar')['Score'].mean().round(1).reset_index()
    categories = raw_avg_df['Pillar'].tolist()
    values = raw_avg_df['Score'].tolist()
    categories.append(categories[0])
    values.append(values[0])

    # Build hover data
    hover_data = _build_hover_data(df, categories, raw_avg_df)

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=sheet_name,
        hoverinfo='text',
        text=hover_data
    ))

    # Add capacity/utilization annotations
    _add_capacity_utilization(fig, df)

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=6.5)),
            angularaxis=dict(tickfont=dict(size=9))
        ),
        showlegend=False
    )

    return fig.to_html(full_html=False)


def _build_hover_data(df, categories, raw_avg_df):
    """Build hover text for chart points."""
    hover_data = []

    for cat in categories:
        sub = df[df['Pillar'] == cat]
        if sub.empty:
            hover_data.append(f"No data for {cat}")
            continue

        skills = sub['Specific Skill'].tolist()
        scores = sub['Score'].tolist()
        cat_avg = raw_avg_df.loc[raw_avg_df['Pillar'] == cat, 'Score'].values[0]

        info = f"Averaged Score: {cat_avg}<br>Attribute: {cat}<br>"
        for skill, score in zip(skills, scores):
            info += f"<span style='font-size:10px;'>{skill}: {score}</span><br>"

        hover_data.append(info)

    return hover_data


def _add_capacity_utilization(fig, df):
    """Add capacity and utilization indicators to chart."""
    def safe_int(x):
        try:
            return int(round(x))
        except:
            return 0

    cap_val = safe_int(df.loc[0, 'Capacity'] * 100 if 'Capacity' in df.columns and not df.empty else 0)
    util_val = safe_int(df.loc[0, 'Utilization'] * 100 if 'Utilization' in df.columns and not df.empty else 0)

    def capacity_color(c):
        if c <= 50:
            return '#6EC664'
        elif c <= 80:
            return '#FFCB6B'
        elif c <= 95:
            return '#DC7633'
        return '#E74C3C'

    def utilization_color(u):
        if u <= 50:
            return '#E74C3C'
        elif u <= 80:
            return '#DC7633'
        elif u <= 95:
            return '#FFCB6B'
        return '#6EC664'

    cap_col = capacity_color(cap_val)
    util_col = utilization_color(util_val)

    # Capacity annotation and bar
    fig.add_annotation(
        x=0.14, y=-0.18,
        text=f"Capacity: {cap_val}%",
        showarrow=False,
        font=dict(color=cap_col, size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect",
        x0=0.35, x1=0.85, y0=-0.18, y1=-0.14,
        fillcolor=cap_col,
        line=dict(width=0),
        xref="paper", yref="paper"
    )

    # Utilization annotation and bar
    fig.add_annotation(
        x=0.14, y=-0.25,
        text=f"Utilization: {util_val}%",
        showarrow=False,
        font=dict(color=util_col, size=12),
        xref="paper", yref="paper"
    )
    fig.add_shape(
        type="rect",
        x0=0.35, x1=0.85, y0=-0.25, y1=-0.21,
        fillcolor=util_col,
        line=dict(width=0),
        xref="paper", yref="paper"
    )


@app.route('/load_one_chart')
def load_one_chart():
    """Load a single chart by offset for lazy loading."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return "Not logged in", 401

    try:
        offset = int(request.args.get('offset', '0'))
    except ValueError:
        offset = 0

    search_name = request.args.get('search_name', '').lower()

    applied_filters = get_applied_filters(request)
    filtered = filter_data(data_service.data_dict, applied_filters)
    sheets = [s for s, df in filtered.items() if not df.empty]

    if search_name:
        search_words = search_name.split()
        sheets = [s for s in sheets if all(word in s.lower() for word in search_words)]

    if offset >= len(sheets):
        return ""

    sheet_name = sheets[offset]
    df = data_service.data_dict[sheet_name]

    # Build snippet HTML
    snippet = f"""
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
        all_engagements = set()
        for e_list in df['Engagements']:
            if e_list and isinstance(e_list, str):
                for eng in e_list.split(','):
                    all_engagements.add(eng.strip())
        for eng in sorted(all_engagements):
            snippet += f"<li>{eng}</li>"

    snippet += "</ul></div>"
    return snippet


# --------------------------------------------------------------------------------------
# Chat API Routes
# --------------------------------------------------------------------------------------
@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """Handle chat messages from the AI assistant."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    question = data.get('question', '')
    history = data.get('history', [])

    result = chat_service.chat(question, history)
    return jsonify(result)


@app.route('/api/chat/suggestions')
def chat_suggestions():
    """Get quick suggestion prompts."""
    user = auth_service.get_authenticated_user(request)
    if not user:
        return jsonify({"error": "Not authenticated"}), 401

    return jsonify({"suggestions": chat_service.get_quick_suggestions()})


# --------------------------------------------------------------------------------------
# Entry Point
# --------------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
