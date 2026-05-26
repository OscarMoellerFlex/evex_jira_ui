import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go # Required for adding the custom text layer
from jira_loader import fetch_jira_issues
from data_loading import save_data, load_data
from styles import CUSTOM_CSS
from datetime import datetime, timezone, timedelta, time
import pytz
from data_transformation import load_issues, upsert_jira_data, load_issues_Amparex
from plotting import apply_font, create_toggle_chart, generate_distinct_colors
from st_aggrid import AgGrid, GridOptionsBuilder
import pygwalker as pg
from pygwalker.api.streamlit import StreamlitRenderer, init_streamlit_comm
import os
import hmac

# set to dark mode
st.set_page_config(layout="wide")
# Apply custom CSS styles
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def require_password() -> None:
    """
    Simple password gate for the Streamlit UI.

    - Set `UI_PASSWORD` (recommended via Render env var) to enable.
    - If `UI_PASSWORD` is not set, the UI will be accessible without a password.
    """
    configured_password = os.getenv("UI_PASSWORD")
    if not configured_password:
        return

    if st.session_state.get("_ui_authed", False):
        if st.sidebar.button("🔒 Logout"):
            st.session_state["_ui_authed"] = False
            st.rerun()
        return

    st.sidebar.markdown("### 🔐 Login")
    entered = st.sidebar.text_input("Passwort", type="password")
    if entered:
        if hmac.compare_digest(entered, configured_password):
            st.session_state["_ui_authed"] = True
            st.rerun()
        else:
            st.sidebar.error("Falsches Passwort.")

    st.stop()

# Sidebar
# add logo in sidebar
st.sidebar.image("data/evex_logo.png", width=200)
st.sidebar.header("\n\nJIRA Data Analysis")

# Require password before showing any data/controls (set UI_PASSWORD to enable).
#require_password()

st.sidebar.subheader("Data Controls")
# add horizontal radio buttons to toggle between Ipro, Amparex and both
firma = st.sidebar.radio("Firma", ["Ipro", "Amparex", "Beide"], horizontal=True)

try:
    df_old = load_data()
    df = df_old.copy()
    # make sure column clone_in_project is there
    if 'clone_in_project' not in df.columns:
        df['clone_in_project'] = '-'
except:
    df = pd.DataFrame()
    df_old = pd.DataFrame()

# Optional global filters in sidebar
start_date = datetime.now(timezone.utc) - timedelta(days=7)
end_date = datetime.now(timezone.utc)
start_date, end_date = st.sidebar.date_input("Zeitraum (erstellt)", value=(start_date, end_date))

tz = pytz.UTC

start_dt = tz.localize(datetime.combine(start_date, time.min))
end_dt   = tz.localize(datetime.combine(end_date,   time.max))

# toggle to switch between week_string and created_string
if st.sidebar.toggle("Auf Wochenbasis"):
    x_axis = 'week_string'
    x_axis_label = 'Kalenderwoche'
else:
    x_axis = 'created_string'
    x_axis_label = 'Datum'

st.sidebar.write("JIRA Daten aktualisieren.")

if st.sidebar.button("🔄 aktualisieren"):
    st.sidebar.success("Fetch triggered!")
    issues_ipro = fetch_jira_issues(start_dt, end_dt, max_issues=100000, project="SDIPR")
    issues_amparex = fetch_jira_issues(start_dt, end_dt, max_issues=100000, project="SDAX")
    if issues_ipro is None or issues_amparex is None:
        st.sidebar.warning("No JIRA data found — please refresh using sidebar.")
        st.stop()
    else:
        st.sidebar.success(f"JIRA data fetched successfully! {len(issues_ipro)+len(issues_amparex)} tickets fetched.")
    df_new_ipro = load_issues(issues_ipro)
    df_new_amparex = load_issues_Amparex(issues_amparex)
    # st.sidebar.success(f"Data transformed successfully! New {len(df_new_ipro)} tickets loaded for Ipro and {len(df_new_amparex)} tickets loaded for Amparex.")
    df_combined = pd.concat([df_new_ipro, df_new_amparex])
    columns_new = df_combined.columns
    columns_old = df_old.columns
    columns_to_add = set(columns_new) - set(columns_old)
    for column in columns_to_add:
        df_old[column] = ''
    for column in columns_old:
        if column not in columns_new:
            df_combined[column] = ''
    df = upsert_jira_data(df_old, df_combined)
    save_data(df)
    st.sidebar.success(f"Data upserted successfully! Overall {len(df)} tickets loaded.")

if df is None:
    st.warning("No JIRA data found — please refresh using sidebar.")
    st.stop()
else:
    # Filter dataframe by date range
    df = df[(df['created'] >= start_dt) & (df['created'] <= end_dt)]
    st.sidebar.success(f"Data filtered successfully! {len(df)} tickets loaded.")



if firma == "Ipro":
    df = df[df['firma'] == "IPRO"]
elif firma == "Amparex":
    df = df[df['firma'] == "Amparex"]
else:
    pass
df_raw = df.copy()

plot_height = 900
plot_width = 1500
# Tabs
tab_overview, tab_categories, tab_subcategories, tab_sources, tab_status, tab_cycle_time, tab_resolution_time, tab_customer_tickets, tab_clones, tab_raw, tab_interactive = st.tabs([
    "📊 Überblick",
    "📊 Kategorien",
    "📊 Unterkategorien",
    "📊 Quellen",
    "📊 Offene Tickets nach Status",
    "⏱️ Ticketbearbeitungszeit",
    "📈 Erstlösequote",
    "📚 Tickets pro Kunde",
    "📊 Clone Tickets",
    "📄 Rohdaten",
    "📄 Interaktiv"
])


# -------------------------------
# Tab 1 – Overview
# -------------------------------
with tab_overview:
    st.header("📊 Überblick")

    # 1. Prepare the Data
    result = df[[x_axis, 'status', 'key']].groupby([x_axis, 'status']).count().reset_index()

    # Calculate percentages
    total_per_group = result.groupby(x_axis)['key'].transform('sum')
    result['percentage'] = result['key'] / total_per_group

    # Create custom label
    result['custom_label'] = result.apply(
        lambda x: f"{x['key']} ({x['percentage']:.0%})", axis=1
    )

    # --- NEW: Define Order Logic ---
    # Get all unique statuses
    status_order = result['status'].unique().tolist()

    # If "Fertig" exists, move it to the front of the list (Index 0 = Bottom of stack)
    target_status = "Fertig"
    if target_status in status_order:
        status_order.remove(target_status)
        status_order.insert(0, target_status)
    # -------------------------------

    # 2. Add Toggle
    mode = st.radio(
        "Ansicht wählen:",
        ["Absolute Zahlen", "Relativ (%)"],
        horizontal=True,
        index=0 
    )

    # 3. Configure Axis Variables
    if mode == "Absolute Zahlen":
        y_col = 'key'
        y_title = 'Anzahl Tickets'
        y_format = None
    else:
        y_col = 'percentage'
        y_title = 'Prozentualer Anteil'
        y_format = '.0%' 

    # 4. Plot with Category Order
    fig = px.bar(
        result, 
        x=x_axis, 
        y=y_col, 
        text='custom_label', 
        color='status',
        # Apply the forced order here
        category_orders={'status': status_order} 
    )

    fig.update_xaxes(title_text=x_axis_label)
    fig.update_yaxes(title_text=y_title, tickformat=y_format)
    fig = apply_font(fig)

    st.plotly_chart(fig, height=plot_height, width=plot_width)


# -------------------------------
# Tab 2 – Categories Breakdown
# -------------------------------
with tab_categories:
    st.header("📊 Aufteilung Kategorien")

    # 1. Prepare Data
    result = df[['Hauptkategorie','resolution','key']].groupby(['Hauptkategorie','resolution']).count().reset_index()
    result = result.rename(columns={'key': 'Anzahl'})

    # Calculate Totals & Percentages
    total_per_group = result.groupby('Hauptkategorie')['Anzahl'].transform('sum')
    result['percentage'] = result['Anzahl'] / total_per_group

    result['custom_label'] = result.apply(
        lambda x: f"{x['Anzahl']}<br>({x['percentage']:.0%})", axis=1
    )

    # 2. Define Sorting
    category_totals = result.groupby('Hauptkategorie')['Anzahl'].sum().reset_index()
    category_totals = category_totals.sort_values('Anzahl', ascending=False)
    sorted_categories = category_totals['Hauptkategorie'].tolist()

    resolution_order = result['resolution'].unique().tolist()
    if "Same day" in resolution_order:
        resolution_order.remove("Same day")
        resolution_order.insert(0, "Same day")

    # 3. Add Toggle
    mode_cat = st.radio(
        "Ansicht wählen:",
        ["Absolute Zahlen", "Relativ (%)"],
        horizontal=True,
        index=0,
        key="toggle_categories" 
    )

    # 4. Configure Axis
    if mode_cat == "Absolute Zahlen":
        y_col = 'Anzahl'
        y_title = 'Anzahl Tickets'
        y_format = None
        y_text_pos = category_totals['Anzahl']
        text_content = category_totals['Anzahl'].astype(str)
        y_max = category_totals['Anzahl'].max() * 1.15 
    else:
        y_col = 'percentage'
        y_title = 'Prozentualer Anteil'
        y_format = '.0%'
        y_text_pos = [1] * len(category_totals)
        text_content = category_totals['Anzahl'].apply(lambda x: f"Total: {x}")
        y_max = 1.15

    # 5. Plot Main Bars
    fig = px.bar(
        result, 
        x='Hauptkategorie', 
        y=y_col, 
        color='resolution',
        text='custom_label',
        color_discrete_map={"Same day": "green", "> 1 day": "#FFD700"},
        category_orders={'resolution': resolution_order, 'Hauptkategorie': sorted_categories}
    )

    # --- FIX STEP 1: Apply styling to the bars NOW, before adding the scatter trace ---
    # This prevents 'apply_font' from trying to set bar properties on the scatter trace later
    fig.update_traces(textposition='auto') 
    fig = apply_font(fig) 

    # --- FIX STEP 2: Add the Scatter Trace (Totals) AFTER styling ---
    fig.add_trace(
        go.Scatter(
            x=category_totals['Hauptkategorie'],
            y=y_text_pos,
            text=text_content,
            mode='text',
            textposition='top center',
            textfont=dict(size=14, color='black', weight='bold'),
            showlegend=False,
            hoverinfo='skip'
        )
    )

    # Final Layout Updates
    fig.update_yaxes(title_text=y_title, tickformat=y_format, range=[0, y_max])
    
    st.plotly_chart(fig, height=plot_height, width=plot_width)

# -------------------------------
# Tab 3 – Categories Breakdown
# -------------------------------
with tab_subcategories:
    st.header("📊 Aufteilung Unterkategorien")
    subcategories = df["Unterkategorie"].unique()
    palette = generate_distinct_colors(len(subcategories))

    color_map = dict(zip(subcategories, palette))

    result = df[['Hauptkategorie','Unterkategorie','key']].groupby(['Hauptkategorie','Unterkategorie']).count().reset_index()
    result = result.rename(columns={'key': 'Anzahl'})
    # sort by overall count
    result = result.sort_values('Anzahl', ascending=False)

    fig = px.bar(result, x='Hauptkategorie', y='Anzahl', 
                color='Unterkategorie',color_discrete_map=color_map)
    fig = apply_font(fig)
    st.plotly_chart(fig, height=plot_height, width=plot_width)


# -------------------------------
# Tab 3 – Sources Breakdown
# -------------------------------

with tab_sources:
    st.header("📊 Aufteilung Quellen")

    # 1. Prepare Data
    # Filter out empty request types and group
    result = df[df['request_type']!=''][['request_type', x_axis, 'key']].groupby(['request_type', x_axis]).count().reset_index()

    # Calculate Totals & Percentages per x-axis group
    # We group by x_axis to get the total stack height for each column
    total_per_group = result.groupby(x_axis)['key'].transform('sum')
    result['percentage'] = result['key'] / total_per_group

    # Create Custom Label: "Count <br> (Percentage%)"
    result['custom_label'] = result.apply(
        lambda x: f"{x['key']}({x['percentage']:.0%})", axis=1
    )

    # 2. Calculate Totals for Top Labels
    # Create a separate DataFrame for the totals that will sit on top of the bars
    group_totals = result.groupby(x_axis)['key'].sum().reset_index()
    
    # 3. Add Toggle
    mode_source = st.radio(
        "Ansicht wählen:",
        ["Absolute Zahlen", "Relativ (%)"],
        horizontal=True,
        index=0,
        key="toggle_sources"  # Unique key is required for Streamlit widgets
    )

    # 4. Configure Axis and Top Labels based on toggle
    if mode_source == "Absolute Zahlen":
        y_col = 'key'
        y_title = 'Anzahl Tickets'
        y_format = None
        
        # Labels for top of bars
        y_text_pos = group_totals['key']
        text_content = group_totals['key'].astype(str)
        # Add 15% buffer to Y-axis max so labels fit
        y_max = group_totals['key'].max() * 1.15
    else:
        y_col = 'percentage'
        y_title = 'Prozentualer Anteil'
        y_format = '.0%'
        
        # Labels for top of bars (always at 100%)
        y_text_pos = [1] * len(group_totals)
        # Show "Total: N" so context isn't lost in percent mode
        text_content = group_totals['key'].apply(lambda x: f"Total: {x}")
        y_max = 1.15

    # 5. Plot Main Bars
    fig = px.bar(
        result, 
        x=x_axis, 
        y=y_col, 
        color='request_type',
        text='custom_label'
    )

    # --- CRITICAL: Apply Bar Styling BEFORE adding Scatter trace ---
    # This prevents the "Invalid property insidetextanchor" error
    fig.update_traces(
        textposition='inside',
        insidetextanchor='middle'
    )
    fig = apply_font(fig)

    # 6. Add Scatter Trace for Totals
    fig.add_trace(
        go.Scatter(
            x=group_totals[x_axis],
            y=y_text_pos,
            text=text_content,
            mode='text',
            textposition='top center',
            textfont=dict(size=12, color='black', weight='bold'),
            showlegend=False,
            hoverinfo='skip'
        )
    )

    # 7. Final Layout Updates
    fig.update_xaxes(title_text=x_axis_label)
    fig.update_yaxes(title_text=y_title, tickformat=y_format, range=[0, y_max])
    
    st.plotly_chart(fig,  height=plot_height, width=plot_width)

# -------------------------------
# Tab 4 – Status Breakdown
# -------------------------------
with tab_status:
    st.header("📊 Offene Tickets nach Status")
    result = df[df['status_category']!='Fertig'][['status_category','status','key']].groupby(['status_category','status']).count().reset_index().sort_values('key', ascending=False)
    result['status_key'] = result['status'] + ' (' + result['key'].astype(str) + ')'
    # plot using plotly with status_category on x axis and status on y axis, show status and key values inside of bars
    fig = px.bar(result, x='status_category', y='key', color='status', text='status_key')
    # add labels inside of bars
    fig.update_traces(
        textposition='inside',
        insidetextanchor='middle'
    )
    # add y axis label
    fig.update_yaxes(title_text='Anzahl Tickets')
    fig.update_xaxes(title_text='Statuskategorie')
    #remove legend
    fig.update_layout(showlegend=False)
    # set fontsize of plot to 24
    fig = apply_font(fig)

    st.plotly_chart(fig,  height=plot_height, width=plot_width)
    

# -------------------------------
# Tab 5 – Backlog Health
# -------------------------------
with tab_cycle_time:
    st.header("⏱️ Ticketbearbeitungszeit (Fertige Tickets)")

# plot time to resolution bin counts using plotly
# sort by midpoint of intervals/bins
    result = df[df['currentstatus_name'] == 'Fertig'][['time_to_resolution_bin','key']].groupby('time_to_resolution_bin').count().reset_index()
    fig = px.bar(result,x='time_to_resolution_bin', y='key')
    # add x axis label

    fig.update_layout(
        title='Anzahl Fertige Tickets nach Bearbeitungszeit',
    )
    fig.update_xaxes(title_text='Bearbeitungszeit in Stunden')
    # add y axis label
    fig.update_yaxes(title_text='Anzahl Fertige Tickets')
    # set width of plot
    fig.update_layout(width=1000)
    fig = apply_font(fig)
    st.plotly_chart(fig, height=plot_height, width=plot_width)

# -------------------------------
# Tab 6 – Resolution Time
# -------------------------------
with tab_resolution_time:
    st.header("📈 Erstlösequote")
    create_toggle_chart(
        df=df,
        x_col=x_axis,
        group_col='resolution',
        count_col='key', # renamed internally later
        toggle_key="toggle_resolution_time",
        color_map={"Same day": "green", "> 1 day": "#FFD700"},
        force_bottom_value="Same day",
        sort_x_by_total=True, # Sorts bars from tallest to shortest
        plot_height=plot_height,
        plot_width=plot_width
    )

# -------------------------------
# Tab 7 – Customer Tickets
# -------------------------------
with tab_customer_tickets:
    st.header("📚 Anzahl Tickets pro Kunde")
    result = df[df['status_category']=='Fertig'][['zentrale','key']].groupby(['zentrale']).count().reset_index()
    result = result.rename(columns={'key': 'Anzahl'})
    result = result.sort_values('Anzahl', ascending=False)
    result = result.head(25)
    fig = px.bar(result, x='zentrale', y='Anzahl', text='Anzahl')
    fig = apply_font(fig)
    st.plotly_chart(fig,  height=plot_height, width=plot_width)

# -------------------------------
# Tab 8 – Clone Tickets
# -------------------------------
with tab_clones:
    st.header("📊 Clone Tickets")
    result = df[['clone_in_project','key']].groupby(['clone_in_project']).count().reset_index()
    result = result.rename(columns={'key': 'Anzahl'})
    result = result.sort_values('Anzahl', ascending=False)
    fig = px.bar(result, x='clone_in_project', y='Anzahl', text='Anzahl')
    fig = apply_font(fig)
    st.plotly_chart(fig, height=plot_height, width=plot_width)

    # plot clones by project per week
    result = df[['clone_in_project','key',x_axis]].groupby(['clone_in_project',x_axis]).count().reset_index()
    result = result.rename(columns={'key': 'Anzahl'})
    fig = px.bar(result, x=x_axis, y='Anzahl', color='clone_in_project', text='Anzahl')
    # add labels inside of bars
    fig.update_traces(
        textposition='inside',
        insidetextanchor='middle'
    )
    fig = apply_font(fig)
    st.plotly_chart(fig, height=plot_height, width=plot_width)


# -------------------------------
# Tab 9 – Raw Data
# -------------------------------
with tab_raw:
    df = df[['Link', *[col for col in df.columns if col != 'Link']]]
    st.header("📄 Rohdaten")

    st.dataframe(df,
        column_config={
        "Link": st.column_config.LinkColumn(
            "JIRA Link",
            display_text="Open in JIRA"
        )
    },#
    hide_index=True,
    height=plot_height,
    )


# -------------------------------
# Tab 10 – Interactive Data
# -------------------------------
with tab_interactive:
    st.header("📄 Interaktiv")
    problem_cols = [
    col for col in df.columns
    if df[col].apply(lambda x: isinstance(x, (list, dict, set))).any()
    ]
    df = df.drop(columns=problem_cols)
    # display dataframe with pygwalker
    renderer = StreamlitRenderer(df)
    renderer.explorer()

    st.write("\n\n\n\n\n\n")

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(filter=True, sortable=True)
    grid_options = gb.build()

    AgGrid(df, gridOptions=grid_options, height=plot_height, width=plot_width)

