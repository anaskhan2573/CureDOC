import re
import json
import requests
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image as PILImage
from io import BytesIO

app = Flask(__name__)
CORS(app)

# === Configuration ===
IMAGES_DIR = Path("medical_images")
IMAGES_DIR.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = IMAGES_DIR
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size

# === MongoDB Setup ===
mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["curebot"]
sessions_collection = db["sessions"]

# === API Key and Model ===
model7B = "mistralai/mistral-7b-instruct:free"

# === Helper Functions ===
def checkCondition(query, model):
    try:
        if any(word in query.lower() for word in ["hi", "hello", "hey", "greetings"]):
            return "greeting"
        if any(phrase in query.lower() for phrase in ["who are you", "what are you", "your name"]):
            return "introduction"

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {"OPEN"}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": f"Query: {query}. Is this query related to the medical field or not? Answer in one word."}]
            },
        )
        return response.json()["choices"][0]["message"]["content"].strip().lower()
    except Exception as e:
        print(f"Error in checkCondition: {e}")
        return "error"

def checkQuery(condition):
    if condition in ["greeting", "introduction"]:
        return condition
    matches = re.findall(r"\b(yes|no)\b", condition, re.IGNORECASE)
    return matches[0].lower() if matches else "no"

def gen_response(query, model):
    try:
        condition_type = checkQuery(checkCondition(query, model))
        if condition_type == "greeting":
            return "Hello! I'm CureBot, your medical assistant. How can I help you today?"
        if condition_type == "introduction":
            return "I am CureBot, an AI-powered health assistant developed by Singularity team!."

        prompt = f"""A patient asked: '{query}'. In 2-3 simple sentences, explain why this might be happening."""

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {"OPEN"}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error in gen_response: {e}")
        return "I'm sorry, I couldn't generate a response."

def gen_followups(query, model):
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {"OPEN"}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": f"Given the medical condition described: '{query}', generate 5 relevant follow-up questions to understand the symptoms better. Format:\n1. <question>\n2. <question>\n3. <question>\n4. <question>\n5. <question>"}]},
        )
        return response.json()["choices"][0]["message"]["content"].strip().split('\n')
    except Exception as e:
        print(f"Error in gen_followups: {e}")
        return []

def mergeFollowupsResponse(followups, responses):
    return '\n'.join([f"Followup {i+1}: {f.split('.')[-1].strip()}, Response {i+1}: {r}" for i, (f, r) in enumerate(zip(followups, responses))])

def gen_final_solution(context, model):
    try:
        final_prompt = f"""The patient gave the following answers to your follow-up questions:\n\n{context}\n\nBased on this, respond like a real doctor:\n1. Give a likely diagnosis (1 sentence)\n2. Suggest appropriate medicine for every age group okay with quanitity (basic and common only)\n3. Add any home remedies or care tips\n4. Mention 2-3 warning signs when to go to hospital\nKeep your answer under 7 sentences. Be simple and professional."""

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {"OPEN"}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": final_prompt}]},
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error in gen_final_solution: {e}")
        return "I'm sorry, I couldn't generate a final medical recommendation."

def analyze_medical_image(image_path, prompt):
    try:
        import ollama

        if not prompt or prompt.strip() == "":
            prompt = """Analyze this medical image and provide a detailed report with:
            - Disease/Condition Identification
            - Symptoms
            - Diagnosis
            - Treatment Options
            - Medications
            - Precautions
            Include disclaimers about professional medical advice."""

        response = ollama.chat(
            model='llava:latest',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [str(image_path)]
            }]
        )

        result = response['message']['content']
        return result
    except Exception as e:
        print(f"Error in analyze_medical_image: {e}")
        return f"Analysis error: {str(e)}"
def resize_image(image_path, max_width=500, max_height=500):
    try:
        img = PILImage.open(image_path)
        img.thumbnail((max_width, max_height), PILImage.Resampling.LANCZOS)
        
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return img_byte_arr  # Return a file-like object, not ImageReader
    except Exception as e:
        print(f"Error resizing image: {e}")
        return None

def generate_pdf_report(session, filename="diagnosis_report.pdf"):
    try:
        doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)
        story = []
        styles = getSampleStyleSheet()
        cell_style = ParagraphStyle('cell_style', parent=styles["BodyText"], fontSize=10, leading=12)

        # Add logo and header
        logo_path = "curebot_logo.png"
        if os.path.exists(logo_path):
            logo = PDFImage(logo_path, width=60, height=60)
            story.append(logo)
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>CureBot - Medical Report</b>", styles["Title"]))
        story.append(Paragraph(f"<i>Date:</i> {datetime.now().strftime('%d %B %Y, %I:%M %p')}", styles["Normal"]))
        story.append(Spacer(1, 12))

        # Add patient query or image description
        if "query" in session:
            story.append(Paragraph("<b>🩺 Patient Query</b>", styles["Heading2"]))
            story.append(Paragraph(session["query"], styles["BodyText"]))
            story.append(Spacer(1, 10))

        # Add image if available
        if "image_path" in session and os.path.exists(session["image_path"]):
            story.append(Paragraph("<b>🖼 Medical Image</b>", styles["Heading2"]))
            
            # Resize and add image
            resized_image = resize_image(session["image_path"])
            if resized_image:
                story.append(PDFImage(resized_image, width=300, height=200))
                story.append(Spacer(1, 10))
            
            # Add custom prompt if available
            if "user_prompt" in session and session["user_prompt"]:
                story.append(Paragraph("<b>🔍 Analysis Request</b>", styles["Heading3"]))
                story.append(Paragraph(session["user_prompt"], styles["BodyText"]))
                story.append(Spacer(1, 10))

        # Add image analysis results
        if "image_analysis" in session:
            story.append(Paragraph("<b>📝 Image Analysis Results</b>", styles["Heading2"]))
            for line in session["image_analysis"].split('\n'):
                if line.strip():
                    story.append(Paragraph(line, styles["BodyText"]))
            story.append(Spacer(1, 15))

        # Add follow-up Q&A if available
        if "followups" in session and "responses" in session:
            story.append(PageBreak())
            story.append(Paragraph("<b>❓ Follow-up Questions & Answers</b>", styles["Heading2"]))
            data = [[Paragraph("<b>Question</b>", styles["BodyText"]), Paragraph("<b>Answer</b>", styles["BodyText"])]]
            for f, r in zip(session["followups"], session["responses"]):
                data.append([Paragraph(f, cell_style), Paragraph(r, cell_style)])
            table = Table(data, colWidths=[220, 300])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00BCD4")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOX', (0, 0), (-1, -1), 1, colors.grey),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(table)
            story.append(Spacer(1, 12))

        # Add final diagnosis/solution
        if "final_solution" in session:
            story.append(Paragraph("<b>✅ Doctor's Assessment</b>", styles["Heading2"]))
            for line in session["final_solution"].split("\n"):
                if line.strip():
                    story.append(Paragraph(line, styles["BodyText"]))
            story.append(Spacer(1, 12))

        # Add footer with disclaimer
        story.append(Paragraph("<i>Disclaimer:</i> This report is AI-generated and not a substitute for professional medical advice. Please consult a licensed doctor for confirmation.", styles["Italic"]))
        story.append(Spacer(1, 8))
        story.append(Paragraph("<i>Powered by CureBot – Your AI Health Companion</i>", styles["Normal"]))

        doc.build(story)
        return filename
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return None

# === Routes ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "No query provided"}), 400

    quick_type = checkQuery(checkCondition(query, model7B))
    if quick_type == "greeting":
        return jsonify({"response": "Hello! I'm CureBot, your medical assistant. How can I help you today?", "followups": []})
    elif quick_type == "introduction":
        return jsonify({"response": "I am CureBot, an AI-powered health assistant developed by Singularity team!", "followups": []})

    condition = checkCondition(query, model7B)
    if condition == "error":
        return jsonify({"error": "Error processing your query."}), 500

    if checkQuery(condition) == "yes":
        response_text = gen_response(query, model7B)
        followups = gen_followups(query, model7B)
        return jsonify({"response": response_text, "followups": followups})
    else:
        return jsonify({"response": "I am sorry, I can only respond to medical-related queries!"})

@app.route('/answer', methods=['POST'])
def answer():
    data = request.json
    followups = data.get("followups", [])
    responses = data.get("responses", [])
    query = data.get("query", "")
    image_analysis = data.get("image_analysis", None)
    image_path = data.get("image_path", None)

    if not followups or not responses:
        return jsonify({"error": "Missing follow-up questions or responses."}), 400

    context = mergeFollowupsResponse(followups, responses)
    final_solution = gen_final_solution(context, model7B)

    session_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "followups": followups,
        "responses": responses,
        "final_solution": final_solution
    }

    if image_analysis:
        session_data["image_analysis"] = image_analysis
    if image_path:
        session_data["image_path"] = image_path

    result = sessions_collection.insert_one(session_data)
    session_id = str(result.inserted_id)

    return jsonify({
        "final_solution": final_solution,
        "session_id": session_id,
        "pdf_download": f"/download/pdf/{session_id}"
    })

@app.route('/upload', methods=['POST'])
def upload_image():
    # Check if image is provided
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No image selected"}), 400
    
    # Get the custom prompt if provided
    custom_prompt = request.form.get('prompt', '').strip()
    query = request.form.get('query', 'Image analysis').strip()

    # Save the image
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = secure_filename(f"{timestamp}_{file.filename}")
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(image_path)

    # Analyze the image
    analysis_result = analyze_medical_image(image_path, custom_prompt)

    # Store the session
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "user_prompt": custom_prompt if custom_prompt else None,
        "image_path": image_path,
        "image_analysis": analysis_result,
        "final_solution": analysis_result
    }
    
    result = sessions_collection.insert_one(session_data)
    session_id = str(result.inserted_id)

    return jsonify({
        "result": analysis_result,
        "session_id": session_id,
        "pdf_download": f"/download/pdf/{session_id}"
    })

@app.route('/download/pdf/<session_id>')
def download_pdf(session_id):
    try:
        session = sessions_collection.find_one({"_id": ObjectId(session_id)})
        if not session:
            return jsonify({"error": "Session not found"}), 404

        filename = f"medical_report_{session_id}.pdf"
        generate_pdf_report(session, filename=filename)
        
        # Clean up after sending (optional)
        if os.path.exists(filename):
            return send_from_directory(directory=".", path=filename, as_attachment=True)
        else:
            return jsonify({"error": "Failed to generate PDF"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5009)