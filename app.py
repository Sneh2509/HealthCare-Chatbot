import os
import re
import base64
from flask import Flask, render_template, request, session, jsonify
from groq import Groq
from werkzeug.utils import secure_filename
import PyPDF2
import io
import docx
import csv

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Groq client
client = Groq(api_key="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")

def format_response(response, language="english"):
    """Clean and format the AI response to be concise and professional."""
    # Remove thinking sections
    response = re.sub(r"<Thinking>.*?</Thinking>", "", response, flags=re.DOTALL)
    
    # Remove analysis patterns and introductory phrases
    response = re.sub(r"^.*?(Alright|Okay|Let's|First|Looking|Now|So|Wait|I'll|I need to).*$\n?", "", response, flags=re.MULTILINE)
    
    # Remove excessive spacing
    response = re.sub(r'\n{3,}', '\n\n', response)
    
    # Convert markdown headers to HTML for better formatting
    response = re.sub(r'###\s*(.*?)\s*\n', r'<h3>\1</h3>', response)
    response = re.sub(r'##\s*(.*?)\s*\n', r'<h2>\1</h2>', response)
    response = re.sub(r'#\s*(.*?)\s*\n', r'<h1>\1</h1>', response)
    
    # Format bullet points consistently
    response = re.sub(r'\n\s*[•\-]\s*', '\n<li>', response)
    response = re.sub(r'\n\s*(\d+)\.\s*', r'\n<li><strong>\1.</strong> ', response)
    
    # Add closing </li> tags and wrap in <ul>
    response = re.sub(r'<li>(.*?)(?=\n<li>|\n*$)', r'<li>\1</li>', response, flags=re.DOTALL)
    if '<li>' in response:
        response = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', response, flags=re.DOTALL)
    
    # Language-specific formatting for headers
    if language == "hindi":
        hindi_headers = {
            "विश्लेषण": "विश्लेषण",
            "सिफारिशें": "सिफारिशें",
            "परिणाम": "परिणाम",
            "निष्कर्ष": "निष्कर्ष",
            "कमी का नाम और विवरण": "कमी का नाम और विवरण",
            "सामान्य सीमा": "सामान्य सीमा",
            "आहार संबंधित सिफारिशें": "आहार संबंधित सिफारिशें",
            "जीवनशैली में बदलाव": "जीवनशैली में बदलाव"
        }
        for header in hindi_headers.values():
            response = re.sub(fr'{header}:', f'<h3>{header}</h3>', response)
    
    # Wrap the response in a div with proper styling
    response = f'<div class="formatted-response">{response.strip()}</div>'
    
    return response

def get_disease_prediction(symptoms, language="english", is_lab_report=False):
    messages = session.get("messages", [])
    
    # Create system prompt based on selected language
    if language == "hindi":
        if is_lab_report:
            system_prompt = """आप एक स्वास्थ्य सहायक हैं जो प्रयोगशाला रिपोर्ट्स का विश्लेषण करने में विशेषज्ञ हैं।
            केवल हिंदी में जवाब दें। अंग्रेजी का प्रयोग न करें।
            
            रिपोर्ट का विश्लेषण करें और निम्नलिखित प्रारूप में जवाब दें:
            
            विश्लेषण:
            • पाई गई कमियों का विवरण
            
            प्रत्येक कमी के लिए:
            
            कमी का नाम और विवरण:
            • विस्तृत जानकारी
            
            सामान्य सीमा और वर्तमान स्थिति:
            • मापदंडों की जानकारी
            
            आहार संबंधित सिफारिशें:
            • खाद्य पदार्थों की सूची
            
            जीवनशैली में बदलाव:
            • सुधार के लिए सुझाव
            
            किसी भी दवा की सिफारिश न करें।
            सीधे विश्लेषण से शुरू करें, कोई परिचय या सोच प्रक्रिया न दें।"""
        else:
            system_prompt = """आप एक स्वास्थ्य सहायक हैं।
            केवल हिंदी में जवाब दें। अंग्रेजी का प्रयोग न करें।
            
            अपने जवाब को निम्नलिखित प्रारूप में व्यवस्थित करें:
            
            लक्षण:
            • मुख्य लक्षण
            
            कारण:
            • संभावित कारण
            
            उपचार:
            • घरेलू उपचार
            • जीवनशैली में बदलाव
            
            डॉक्टर को कब दिखाएं:
            • गंभीर लक्षण
            
            किसी भी दवा की सिफारिश न करें।
            सीधे विश्लेषण से शुरू करें, कोई परिचय या सोच प्रक्रिया न दें।"""
    
    elif language == "gujarati":
        # Similar system prompts for Gujarati
        if is_lab_report:
            system_prompt = """તમે આરોગ્ય સહાયક છો જે લેબોરેટરી રિપોર્ટ્સનું વિશ્લેષણ કરવામાં નિષ્ણાત છે. 
            ગુજરાતી ભાષામાં જવાબ આપો. અંગ્રેજીનો ઉપયોગ કરશો નહીં.
            
            રિપોર્ટનું વિશ્લેષણ કરો અને નીચેના ફોર્મેટમાં જવાબ આપો:
            
            વિશ્લેષણ:
            • મળેલી ખામીઓનું વર્ણન
            
            દરેક ખામી માટે:
            
            ખામીનું નામ અને વર્ણન:
            • વિગતવાર માહિતી
            
            સામાન્ય શ્રેણી અને વર્તમાન સ્થિતિ:
            • માપદંડોની માહિતી
            
            આહાર સંબંધિત ભલામણો:
            • ખોરાકની યાદી
            
            જીવનશૈલીમાં ફેરફાર:
            • સુધારા માટે સૂચનો
            
            કોઈપણ દવાની ભલામણ કરશો નહીં.
            સીધા વિશ્લેષણથી શરૂ કરો, કોઈ પરિચય કે વિચાર પ્રક્રિયા ન આપો."""
        else:
            system_prompt = """તમે આરોગ્ય સહાયક છો.
            ગુજરાતી ભાષામાં જવાબ આપો. અંગ્રેજીનો ઉપયોગ કરશો નહીં.
            
            તમારા જવાબને નીચેના ફોર્મેટમાં ગોઠવો:
            
            લક્ષણો:
            • મુખ્ય લક્ષણો
            
            કારણો:
            • સંભવિત કારણો
            
            ઉપચાર:
            • ઘરેલુ ઉપચાર
            • જીવનશૈલીમાં ફેરફાર
            
            ડૉક્ટરને ક્યારે મળવું:
            • ગંભીર લક્ષણો
            
            કોઈપણ દવાની ભલામણ કરશો નહીં.
            સીધા વિશ્લેષણથી શરૂ કરો, કોઈ પરિચય કે વિચાર પ્રક્રિયા ન આપો."""
    else:
        # English system prompt
        if is_lab_report:
            system_prompt = """You are a healthcare assistant specialized in analyzing laboratory reports.
            Respond in English.
            Identify and explain any deficiencies in the report.
            For each deficiency, provide:
            1. Name of the deficiency and its description
            2. Normal range and the patient's current status
            3. Clear list of foods and nutrients to eat to address this deficiency
            4. Lifestyle changes for improvement

            Organize your response in clear sections and use bullet points.
            Do NOT provide medicine recommendations or diagnoses.
            Do NOT include your thinking process or analysis steps in your response.
            Start your response directly with the findings and recommendations.
            If the input is unrelated to laboratory reports, respond with 'Sorry, I can only analyze laboratory reports.'"""
        else:
            system_prompt = """You are a healthcare assistant. Respond only to health-related queries in English.
            Format your response with clear sections and bullet points for better readability.
            Structure your answers with clear sections like:
            
            Symptoms:
            • Symptom 1
            • Symptom 2
            
            Causes:
            • Cause 1
            • Cause 2
            
            Treatment:
            • Treatment 1
            • Treatment 2
            
            Do NOT provide medicine recommendations or diagnoses.
            Do NOT include your thinking process or analysis steps in your response.
            Start your response directly with the findings and recommendations.
            If the input is unrelated to health, respond with 'Sorry, I can only assist with health-related queries.'"""

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt}
        ] + messages + [
            {"role": "user", "content": symptoms}
        ],
        model="deepseek-r1-distill-llama-70b",
    ) 

    response = chat_completion.choices[0].message.content
    formatted_response = format_response(response, language)
    
    return formatted_response

# File reading functions
def read_pdf(file_path):
    """Read content from PDF file"""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {str(e)}")
        return None

def read_docx(file_path):
    """Read content from DOCX file"""
    try:
        doc = docx.Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        print(f"Error reading DOCX: {str(e)}")
        return None

def read_txt(file_path):
    """Read content from TXT file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read()
        except Exception as e:
            print(f"Error reading TXT: {str(e)}")
            return None

def read_csv(file_path):
    """Read content from CSV file"""
    try:
        text = []
        with open(file_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                text.append(", ".join(row))
        return "\n".join(text)
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                csv_reader = csv.reader(file)
                text = []
                for row in csv_reader:
                    text.append(", ".join(row))
                return "\n".join(text)
        except Exception as e:
            print(f"Error reading CSV: {str(e)}")
            return None

def process_lab_report(file_path, language="english"):
    """Process uploaded lab report file"""
    # Get file extension
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # Read file content based on file type
    if file_ext == '.pdf':
        report_content = read_pdf(file_path)
    elif file_ext in ['.doc', '.docx']:
        report_content = read_docx(file_path)
    elif file_ext == '.txt':
        report_content = read_txt(file_path)
    elif file_ext == '.csv':
        report_content = read_csv(file_path)
    else:
        return "Unsupported file format. Please upload PDF, DOC, DOCX, TXT, or CSV files."
    
    if report_content is None:
        return "Error reading file. Please ensure the file is not corrupted and try again."
    
    # Add a prefix to indicate this is a lab report based on selected language
    if language == "english":
        prompt = f"This is a laboratory report. Please analyze it for any deficiencies, explain them, and suggest dietary recommendations:\n\n{report_content}"
    elif language == "gujarati":
        prompt = f"આ એક લેબોરેટરી રિપોર્ટ છે. કૃપા કરીને કોઈપણ ખામીઓ માટે તેનું વિશ્લેષણ કરો, તેમને સમજાવો, અને આહાર સંબંધિત ભલામણો સૂચવો:\n\n{report_content}"
    elif language == "hindi":
        prompt = f"यह एक प्रयोगशाला रिपोर्ट है। कृपया किसी भी कमी के लिए इसका विश्लेषण करें, उन्हें समझाएं, और आहार संबंधित सिफारिशें सुझाएं:\n\n{report_content}"
    
    return get_disease_prediction(prompt, language, is_lab_report=True)

# Ensure session clears when the page loads
@app.before_request
def clear_session_on_refresh():
    if request.endpoint == "home" and request.method == "GET":
        session.clear()  # Fully reset session on page refresh
        session["messages"] = []  # Initialize empty message history
        session["language"] = None  # Initialize language preference as None

@app.route("/", methods=["GET"])
def home():
    """ Renders the chat page. """
    if "messages" not in session:
        session["messages"] = []  # Initialize session if not present
    if "language" not in session:
        session["language"] = None  # Initialize language preference if not present
    return render_template("chat.html", messages=session["messages"], language=session.get("language"))

@app.route("/set_language", methods=["POST"])
def set_language():
    """ Sets the language preference. """
    data = request.json
    language = data.get("language")
    
    if language in ["english", "gujarati", "hindi"]:
        session["language"] = language
        
        # Add welcome message based on selected language
        if language == "english":
            welcome_message = "Welcome! How can I help you with your health concerns today? You can also upload laboratory reports for analysis."
        elif language == "gujarati":
            welcome_message = "સ્વાગત છે! આજે હું તમારી આરોગ્ય સંબંધિત ચિંતાઓમાં કેવી રીતે મદદ કરી શકું? તમે વિશ્લેષણ માટે લેબોરેટરી રિપોર્ટ્સ પણ અપલોડ કરી શકો છો."
        else:  # hindi
            welcome_message = "स्वागत है! आज मैं आपकी स्वास्थ्य संबंधित चिंताओं में कैसे मदद कर सकता हूं? आप विश्लेषण के लिए प्रयोगशाला रिपोर्ट भी अपलोड कर सकते हैं।"
        
        session["messages"].append({"role": "assistant", "content": welcome_message})
        session.modified = True
        
        return jsonify({"success": True, "language": language, "welcome_message": welcome_message})
    
    return jsonify({"success": False, "error": "Invalid language selection"}), 400

@app.route("/send_message", methods=["POST"])
def send_message():
    """ Handles message submission via AJAX. """
    data = request.json
    user_input = data.get("user_input")
    
    # If language is not set and this is the first message, prompt for language selection
    if not session.get("language") and not session.get("messages"):
        return jsonify({
            "response": "Please select your preferred language / कृपया अपनी पसंदीदा भाषा चुनें / કૃપા કરીને તમારી પસંદગીની ભાષા પસંદ કરો", 
            "show_language_selection": True
        })

    if user_input:
        session["messages"].append({"role": "user", "content": user_input})
        response = get_disease_prediction(user_input, session.get("language", "english"))
        session["messages"].append({"role": "assistant", "content": response})
        session.modified = True
        return jsonify({"response": response, "messages": session["messages"]})

    return jsonify({"error": "No input provided"}), 400

@app.route("/upload_report", methods=["POST"])
def upload_report():
    """Handle lab report file uploads"""
    if 'report_file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['report_file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Check file extension
        allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.csv'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            return jsonify({"error": "Unsupported file format. Please upload PDF, DOC, DOCX, TXT, or CSV files."}), 400
        
        try:
            # Save the file
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Process the file
            language = session.get("language", "english")
            response = process_lab_report(file_path, language)
            
            # Add to message history
            if language == "english":
                user_message = f"I've uploaded a laboratory report: {filename}"
            elif language == "gujarati":
                user_message = f"મેં લેબોરેટરી રિપોર્ટ અપલોડ કર્યો છે: {filename}"
            else:  # hindi
                user_message = f"मैंने प्रयोगशाला रिपोर्ट अपलोड की है: {filename}"
                
            session["messages"].append({"role": "user", "content": user_message})
            session["messages"].append({"role": "assistant", "content": response})
            session.modified = True
            
            # Clean up the uploaded file
            os.remove(file_path)
            
            return jsonify({
                "success": True,
                "filename": filename,
                "response": response
            })
            
        except Exception as e:
            # Clean up the file if it was saved
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"error": f"Error processing file: {str(e)}"}), 500
    
    return jsonify({"error": "File upload failed"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)

