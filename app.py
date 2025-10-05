from flask import Flask, request, render_template
import requests
import tempfile
import os
from dotenv import load_dotenv
import json

# Appwrite SDK imports
from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.services.databases import Databases
from appwrite.exception import AppwriteException
from appwrite.input_file import InputFile
import pytesseract
from PIL import Image
from io import BytesIO

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)

# Load keys and config from environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT")
APPWRITE_PROJECT_ID = os.getenv("APPWRITE_PROJECT_ID")
APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY")
APPWRITE_STORAGE_BUCKET_ID = os.getenv("APPWRITE_STORAGE_BUCKET_ID")
APPWRITE_DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID")
APPWRITE_DATABASE_COLLECTION_ID = os.getenv("APPWRITE_DATABASE_COLLECTION_ID")

# Initialize Appwrite client and services
client = Client()
(client
    .set_endpoint(APPWRITE_ENDPOINT)
    .set_project(APPWRITE_PROJECT_ID)
    .set_key(APPWRITE_API_KEY)  # Use API key with Storage and Database permissions
)

storage = Storage(client)
database = Databases(client)




def extract_text_from_receipt(image_file):
    # Convert file stream to PIL Image
    img = Image.open(BytesIO(image_file.read()))
    # Use pytesseract to extract text
    text = pytesseract.image_to_string(img)
    # Reset stream position for further use if needed
    image_file.seek(0)
    return text



def categorize_expense(text):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "<YOUR_SITE_URL>",
        "X-Title": "<YOUR_SITE_NAME>"
    }
    data = {
        "model": "openai/gpt-4o",  # Confirm the model name with OpenRouter docs
        "messages": [{"role": "user", "content": f"Classify this expense: '{text}' into categories like food, transport, entertainment, etc."}]
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        data=json.dumps(data)
    )

    if response.status_code == 200:
        response_json = response.json()
        return response_json['choices'][0]['message']['content'].strip()
    else:
        return "Error in categorization"



def generate_advice(expenses_summary):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "<YOUR_SITE_URL>",
        "X-Title": "<YOUR_SITE_NAME>"
    }
    data = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": f"Based on these expenses: {expenses_summary}, suggest quick saving tips."}]
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        data=json.dumps(data)
    )

    if response.status_code == 200:
        response_json = response.json()
        return response_json['choices'][0]['message']['content'].strip()
    else:
        return "Error in generating advice"



@app.route('/')
def home():
    return render_template('index.html')




@app.route('/analyze', methods=['POST'])
def analyze():
    if 'receipt' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['receipt']

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        upload_result = storage.create_file(
            bucket_id=APPWRITE_STORAGE_BUCKET_ID,
            file_id="unique()",
            file=InputFile.from_path(tmp_path),  # Wrap file with InputFile
            permissions=["read(\"any\")"]        # Example: public read
        )
        file_id = upload_result['$id']
    except AppwriteException as e:
        os.remove(tmp_path)
        return f"Storage upload error: {e.message}", 500

    os.remove(tmp_path)

    file.stream.seek(0)
    text = extract_text_from_receipt(file)

    category = categorize_expense(text)
    summary = f"{text} categorized as {category}"
    print("category: ", category)
    print("summary: ", summary)
    advice = generate_advice(summary)

    try:
        database.create_document(
            database_id = APPWRITE_DATABASE_ID,
            collection_id=APPWRITE_DATABASE_COLLECTION_ID,
            document_id="unique()",
            data={
                "text": text,
                "category": category,
                "advice": advice,
                "fileId": file_id
            },
            
        )
    except AppwriteException as e:
        return f"Database error: {e.message}", 500

    return render_template('index.html', text=text, category=category, advice=advice)



if __name__ == '__main__':
    app.run(debug=True)
