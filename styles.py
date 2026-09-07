"""Custom CSS styles for the Streamlit app."""

CUSTOM_CSS = """
    <style>
    /* Increase base font size */
    .stApp {
        font-size: 1.1rem;
    }
    
    /* Increase text size */
    p, div, span, label {
        font-size: 1.1rem !important;
    }
    
    /* Increase header sizes */
    h1 {
        font-size: 2.5rem !important;
    }
    
    h2 {
        font-size: 2rem !important;
    }
    
    h3 {
        font-size: 1.75rem !important;
    }
    
    /* Increase sidebar text */
    .css-1d391kg {
        font-size: 1.1rem !important;
    }
    
    /* Increase metric values */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
    }
    
    /* Increase metric label */
    [data-testid="stMetricLabel"] {
        font-size: 1rem !important;
    }
    
    /* Increase button text */
    .stButton > button {
        font-size: 1.1rem !important;
    }
    
    /* Increase selectbox and other widget text */
    .stSelectbox label, .stMultiselect label, .stDateInput label {
        font-size: 1.1rem !important;
    }
    
    /* Increase dataframe text */
    .dataframe {
        font-size: 1rem !important;
    }
    
    /* Increase tab text */
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.1rem !important;
    }
    </style>
    """
