#### data.xlsx have 6 sheets
#### data_original have 4 sheets

from flask import Flask, render_template, request
import pandas as pd
import plotly.graph_objects as go
import math

app = Flask(__name__)

# Load the predefined spreadsheet
file_path = 'data.xlsx'  # Make sure data.xlsx is in the same directory
sheets = pd.ExcelFile(file_path)
data_dict = {}

for sheet_name in sheets.sheet_names:
    data = sheets.parse(sheet_name)
    if 'Pillar' in data.columns and 'Score' in data.columns:
        data_dict[sheet_name] = data  # Store the entire DataFrame

# Get unique pillars for the checkboxes
all_pillars = []
for sheet_name, data in data_dict.items():
    all_pillars.extend(data['Pillar'].unique())
unique_pillars = sorted(set(all_pillars))


@app.route('/', methods=['GET', 'POST'])
def index():
    selected_pillars = []
    page = int(request.args.get('page', 1))
    selected_pillars_query = request.args.get('selected_pillars', '')

    # Parse selected pillars from query parameters
    if selected_pillars_query:
        selected_pillars = selected_pillars_query.split(',')

    # Handle form submission on the first page
    if request.method == 'POST' and page == 1:
        selected_pillars = request.form.getlist('pillar')

    # Filter data based on selected pillars
    filtered_data_dict = {}
    if selected_pillars:
        for sheet_name, data in data_dict.items():
            filtered_data = data[data['Pillar'].isin(selected_pillars)]
            if not filtered_data.empty:
                filtered_data_dict[sheet_name] = filtered_data

    # Apply pagination
    total_charts = len(filtered_data_dict)
    charts_per_page = 4
    total_pages = math.ceil(total_charts / charts_per_page)

    start_index = (page - 1) * charts_per_page
    end_index = start_index + charts_per_page
    paginated_data = dict(list(filtered_data_dict.items())[start_index:end_index])

    return render_template(
        'index.html',
        pillars=unique_pillars,
        selected_pillars=selected_pillars,
        data=paginated_data,
        current_page=page,
        total_pages=total_pages,
        show_filter_form=(page == 1),
        selected_pillars_query=','.join(selected_pillars)
    )



@app.route('/chart/<sheet_name>/<pillars>')
def generate_chart(sheet_name, pillars):
    if sheet_name not in data_dict:
        return "Sheet not found", 404

    selected_pillars = pillars.split(',')
    data = data_dict[sheet_name]

    # Calculate the average score for each pillar
    filtered_data = data[data['Pillar'].isin(selected_pillars)]
    avg_scores = filtered_data.groupby('Pillar')['Score'].mean().round(1).reset_index()

    fig = go.Figure()

    categories = avg_scores['Pillar'].tolist()
    values = avg_scores['Score'].tolist()

    categories += [categories[0]]
    values += [values[0]]

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=sheet_name
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10]),
            angularaxis=dict(tickfont=dict(size=8))
        ),
        showlegend=False,
    )

    return fig.to_html(full_html=False)

if __name__ == '__main__':
    app.run(debug=True)


