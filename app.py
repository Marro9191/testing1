import streamlit as st
import pandas as pd
#import matplotlib.pyplot as plt
#import seaborn as sns
#from datetime import datetime
import openai
#import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# Access OpenAI API key securely from Streamlit secrets (or hardcode for local testing)
if 'OPENAI_API_KEY' in st.secrets["openai"]:
    openai.api_key = st.secrets["openai"]["api_key"]
else:
    # For local testing, hardcode the API key (remove for deployment)
    openai.api_key = "your_openai_api_key_here"  # Replace with your key for local testing only

# Set page configuration
st.set_page_config(page_title="Conversation Insights Dashboard", layout="wide")

# Custom CSS for styling
try:
    st.markdown("""
        <style>
        .stChatMessage {
            border-radius: 10px;
            padding: 10px;
            margin: 5px 0;
        }
        .user-message { background-color: #f0f2f6; }
        .bot-message { background-color: #e8f5e9; }
        </style>
    """, unsafe_allow_html=True)
    st.write("CSS loaded successfully")
except Exception as e:
    st.error(f"Error loading CSS: {str(e)}")

# Connect to Google Sheets securely (service account)
@st.cache_data(ttl=600)  # Cache data for 10 minutes
def load_google_sheet():
    try:
        # Check if running locally or on Streamlit Cloud
        if 'GOOGLE_SHEETS_CREDENTIALS' in st.secrets["connections.gsheets"]:
            # Use secrets for Streamlit Cloud
            credentials_info = st.secrets["connections.gsheets"]["GOOGLE_SHEETS_CREDENTIALS"]
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                credentials_info,
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )
        else:
            # For local testing, use credentials.json file
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                'credentials.json',
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )

        client = gspread.authorize(credentials)
        
        # Get spreadsheet ID from secrets or use a default for local testing
        spreadsheet_id = st.secrets["connections.gsheets"].get("spreadsheet", "YOUR_SPREADSHEET_ID")
        if spreadsheet_id == "YOUR_SPREADSHEET_ID":
            st.error("Please configure the spreadsheet ID in secrets.toml or credentials.json for local testing.")
            return pd.DataFrame()

        spreadsheet = client.open_by_key(spreadsheet_id.split("/d/")[1].split("/edit")[0])
        worksheet = spreadsheet.sheet1  # Adjust worksheet name if needed
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error loading Google Sheet: {str(e)}")
        return pd.DataFrame()

def generate_nlp_response(conversation_text, context=None, data=None):
    """Generate an advanced NLP response using OpenAI's GPT API (version 1.0.0+) and analyze Google Sheet data"""
    try:
        # Prepare the prompt with context, data summary, and user query
        prompt = f"User query: {conversation_text}\n\n"
        if context:
            prompt += f"Context: {context}\n\n"
        if data is not None and not data.empty:
            prompt += f"Available data columns: {list(data.columns)}\nData summary: {data.describe().to_string()}\n\n"
        prompt += "Provide a natural, concise response as a helpful AI assistant for analyzing business data from Google Sheets. If the user asks about a top-performing product, returns, or specific metrics, suggest insights, calculations, or visualizations based on the data. Return the response in this format: 'Response: [your response]' and if a graph is needed, include 'Graph: [description of the graph, e.g., bar chart of top products by performance]'."

        # Call OpenAI API with the new chat completions endpoint
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",  # Use "gpt-4" for more advanced responses if available
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant for analyzing business data from Google Sheets and providing insights or visualizations."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,  # Increased for more detailed responses
            temperature=0.7  # Balanced between creativity and coherence
        )
        
        full_response = response.choices[0].message.content.strip()
        # Parse the response for text and graph instructions
        if "Response:" in full_response and "Graph:" in full_response:
            response_text = full_response.split("Response:")[1].split("Graph:")[0].strip()
            graph_instruction = full_response.split("Graph:")[1].strip()
            return response_text, graph_instruction
        return full_response, None
    except Exception as e:
        st.error(f"Error generating NLP response: {str(e)}")
        return "Sorry, I encountered an issue processing your request.", None

def create_graph(data, graph_instruction):
    """Create a graph based on the OpenAI instruction"""
    try:
        if "bar chart" in graph_instruction.lower():
            if "top products" in graph_instruction.lower() and "performance" in graph_instruction.lower():
                top_products = data.sort_values(by="Performance", ascending=False).head(5)  # Adjust column name as needed
                fig, ax = plt.subplots(figsize=(5, 3))
                sns.barplot(data=top_products, x="Product", y="Performance", ax=ax)  # Adjust column names
                ax.set_title("Top 5 Products by Performance")
                ax.set_xlabel("Product")
                ax.set_ylabel("Performance")
                return fig
            elif "returns" in graph_instruction.lower():
                fig, ax = plt.subplots(figsize=(5, 3))
                sns.barplot(data=data, x="Product", y="Returns", ax=ax)  # Adjust column names
                ax.set_title("Returns by Product")
                ax.set_xlabel("Product")
                ax.set_ylabel("Returns")
                return fig
        elif "line chart" in graph_instruction.lower():
            if "performance over time" in graph_instruction.lower():
                fig, ax = plt.subplots(figsize=(5, 3))
                sns.lineplot(data=data, x="Date", y="Performance", ax=ax)  # Adjust column names
                ax.set_title("Performance Over Time")
                ax.set_xlabel("Date")
                ax.set_ylabel("Performance")
                return fig
        return None
    except Exception as e:
        st.error(f"Error creating graph: {str(e)}")
        return None

def process_conversation(conversation_text, context=None):
    """Process the conversation text with advanced NLP, analyze Google Sheet data, and return analysis"""
    try:
        # Load data from Google Sheets
        data = load_google_sheet()
        
        # Generate NLP response and graph instruction
        nlp_response, graph_instruction = generate_nlp_response(conversation_text, context, data)
        
        # Simple keyword-based analysis for insights (can be enhanced with NLP)
        lines = conversation_text.strip().split('\n')
        analysis = {"insights": [], "graphs": [], "response": nlp_response}
        
        for line in lines:
            if "top performing product" in line.lower():
                if not data.empty:
                    top_product = data.loc[data["Performance"].idxmax()]  # Adjust column name
                    analysis["insights"].append(f"Top-performing product: {top_product['Product']} with performance {top_product['Performance']}")
            elif "drove most return" in line.lower():
                if not data.empty:
                    top_return = data.loc[data["Returns"].idxmax()]  # Adjust column name
                    analysis["insights"].append(f"Product with most returns: {top_return['Product']} with returns {top_return['Returns']}")
        
        # Create graph if instructed
        if graph_instruction and not data.empty:
            graph = create_graph(data, graph_instruction)
            if graph:
                analysis["graphs"].append(graph)
        
        return analysis
    except Exception as e:
        st.error(f"Error in process_conversation: {str(e)}")
        return {"insights": [], "graphs": [], "response": "Sorry, I encountered an error processing your request."}

def main():
    st.title("Conversation Insights Dashboard")
    
    # Initialize session state for conversation context
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    
    st.sidebar.title("Navigation")
    pages = ["Dashboard", "Insights", "Recommendations", "Content Quality", 
             "Search Placement", "Reviews & Ratings", "Pricing", "KPIs", "Audits", "Accounts", "Help"]
    selected_page = st.sidebar.radio("", pages)
    
    st.header(selected_page)
    
    if selected_page == "Dashboard":
        st.subheader("Enter Conversation or Prompt")
        
        conversation = st.text_area("Type your query about the data (e.g., 'Show me the top-performing product' or 'Graph returns over time')", height=200)
        
        if st.button("Analyze"):
            if conversation:
                with st.spinner("Analyzing conversation and data..."):
                    try:
                        # Add user input to conversation history
                        st.session_state.conversation_history.append({"role": "user", "content": conversation})
                        
                        # Process the conversation with context from history
                        context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in st.session_state.conversation_history])
                        analysis = process_conversation(conversation, context)
                    
                        # Display the system's conversational response
                        if analysis["response"]:
                            st.markdown(f'<div class="stChatMessage bot-message">Bot: {analysis["response"]}</div>', unsafe_allow_html=True)
                            st.session_state.conversation_history.append({"role": "bot", "content": analysis["response"]})
                        
                        # Display conversation history
                        st.subheader("Conversation History")
                        for msg in st.session_state.conversation_history:
                            role_class = "user-message" if msg["role"] == "user" else "bot-message"
                            st.markdown(f'<div class="stChatMessage {role_class}">{"You" if msg["role"] == "user" else "Bot"}: {msg["content"]}</div>', unsafe_allow_html=True)
                        
                        # Display insights
                        st.subheader("Analysis Insights")
                        for insight in analysis["insights"]:
                            st.write(f"- {insight}")
                        
                        # Display graphs
                        st.subheader("Visualizations")
                        for graph in analysis["graphs"]:
                            st.pyplot(graph)
                        
                        # Feedback
                        st.text_input("Feedback", key="feedback")
                        if st.button("Submit Feedback"):
                            st.success("Thank you for your feedback!")
                    except Exception as e:
                        st.error(f"Error during analysis: {str(e)}")
            else:
                st.error("Please enter a query to analyze")
    
    else:
        st.write("This feature is coming soon!")

if __name__ == "__main__":
    main()
