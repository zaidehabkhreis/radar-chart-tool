from flask import Flask, render_template, request, redirect, url_for, make_response
import pandas as pd
import plotly.graph_objects as go
import json
import os

app = Flask(__name__)

# Load the predefined spreadsheet
base_path = os.path.dirname(__file__)
file_path = os.path.join(base_path, "data2.xlsx")
sheets = pd.ExcelFile(file_path)
data_dict = {}

# Store the unique pillars and their average scores for each sheet
pillar_avg_scores_dict = {}

for sheet_name in sheets.sheet_names:
    data = sheets.parse(sheet_name)

    if 'Utilization' in data.columns:
        if data['Utilization'].dtype == 'object':
            data['Utilization'] = data['Utilization'].str.replace('%', '').astype(float)

    data_dict[sheet_name] = data

    if 'Pillar' in data.columns and 'Score' in data.columns:
        avg_scores = data.groupby('Pillar')['Score'].mean().round(1).reset_index()
        pillar_avg_scores_dict[sheet_name] = avg_scores


# Get unique pillars for the filter dropdown
all_pillars = []
for sheet_name, data in data_dict.items():
    if 'Pillar' in data.columns:
        all_pillars.extend(data['Pillar'].unique())
unique_pillars = sorted(set(all_pillars))

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
        search_name=search_name
    )






@app.route('/chart/<sheet_name>')
def generate_chart(sheet_name):
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
    utilization = (data.loc[0, 'Utilization'] if not data.empty and 'Utilization' in data.columns else 0)*100
    utilization_color = 'green' if utilization >= 75 else 'yellow' if utilization >= 50 else 'red'

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