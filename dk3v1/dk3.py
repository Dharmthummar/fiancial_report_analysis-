import os
import json
import re
import fitz  # PyMuPDF for PDF handling
import pytesseract
import pdfplumber
from groq import Groq
from PIL import Image, ImageEnhance, ImageFilter

# Set Tesseract path if needed (Uncomment for Windows)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Financial terms to filter relevant tables
FINANCIAL_RESULTS_TERMS = [
    "Consolidated Financial Results", "Standalone Financial Results",
    "Revenue", "Revenue from operations", "Sales", "Net Profit", "Operating Profit", "EBITDA",
    "Total Income", "Expenses", "Earnings Per Share", "Profit Before Tax", "Profit After Tax",
    "Balance Sheet", "Quarterly Results", "Unaudited Financial Results",
    "Depreciation", "Amortization", "Interest", "Tax Expense"
]

# Your Groq API Key
GROQ_API_KEY = "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"

# Function to detect the page number containing the financial result table
def detect_financial_table_page(pdf_path):
    """Detect the page number containing the financial result table."""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and ("Revenue from Operations" in text or "Profit Before Tax" in text or "Net Profit" in text):
                return page_num + 1  # Return 1-based page number
    return None

# Function to extract the financial table page as an image
def extract_table_image(pdf_path, page_num, output_folder):
    """Extract the financial table page as an image."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num - 1)  # Convert to 0-based index
    pix = page.get_pixmap(dpi=300)  # High resolution (300 DPI)
    image_path = os.path.join(output_folder, f"page_{page_num}.png")
    pix.save(image_path)
    return image_path

# Function to preprocess the image
def preprocess_image(image_path):
    """Apply preprocessing to the image for better OCR accuracy."""
    img = Image.open(image_path)

    # Convert to grayscale
    img = img.convert("L")

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Apply sharpening
    img = img.filter(ImageFilter.SHARPEN)

    # Save the preprocessed image
    preprocessed_image_path = image_path.replace(".png", "_preprocessed.png")
    img.save(preprocessed_image_path)
    return preprocessed_image_path

# Function to extract text from an image using OCR
def extract_text_from_image(image_path):
    """Extract text from an image using OCR."""
    try:
        text = pytesseract.image_to_string(image_path, config='--psm 6')  # PSM 6 ensures structured table reading
        return text
    except Exception as e:
        print(f"Error extracting text from image: {e}")
        return ""

# Function to check if text contains financial terms
def contains_financial_terms(text):
    """Check if extracted text contains strictly financial terms."""
    if not text:
        return False
    found_terms = [term for term in FINANCIAL_RESULTS_TERMS if term.lower() in text.lower()]
    return len(found_terms) >= 3  # At least 3 financial terms must be present

# Function to extract financial details using Groq API
def extract_financial_data(text):
    """Extract financial details using Groq API."""
    try:
        # Initialize Groq client with your API key
        client = Groq(api_key=GROQ_API_KEY)

        # Prepare the prompt for financial extraction
        prompt = f"""
        Extract the following details from the financial report details as I provided and return them in JSON format:
        - Revenue/Sales
        - expenses/operating profit
        - Net Profit
        
        Do not give any other notes, just the above details only.
        Financial Report:
        {text}
        """

        # Create a chat completion request
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_completion_tokens=500,
            top_p=1,
            stream=True,
            stop=None,
        )

        # Collect the response chunks
        result = ""
        for chunk in completion:
            result += chunk.choices[0].delta.content or ""
        
        return result.strip()
    except Exception as e:
        print(f"Error extracting financial data using Groq API: {e}")
        return "{}"

# Function to manually parse financial data from text
def manual_parse_financial_data(text):
    """Manually parse financial data from text."""
    financial_data = {
        "Revenue/Sales": None,
        "Operating Profit": None,
        "Net Profit": None
    }

    # Use regex to find financial data in the text
    revenue_match = re.search(r"Revenue from Operations\s*[:=]?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if revenue_match:
        financial_data["Revenue/Sales"] = float(revenue_match.group(1).replace(",", ""))

    operating_profit_match = re.search(r"expenses Profit Before Exceptional Items and Tax\s*[:=]?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if operating_profit_match:
        financial_data["Operating Profit"] = float(operating_profit_match.group(1).replace(",", ""))

    net_profit_match = re.search(r"Profit for the (?:year|period)\s*[:=]?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if net_profit_match:
        financial_data["Net Profit"] = float(net_profit_match.group(1).replace(",", ""))

    return financial_data

# Function to process a single PDF file
def process_pdf(pdf_path, output_folder):
    """Process a single PDF file and save the output."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Step 1: Detect the page containing the financial table
    page_num = detect_financial_table_page(pdf_path)
    if page_num is None:
        print(f"No financial table found in {pdf_path}. Skipping.")
        return

    # Step 2: Extract the financial table page as an image
    image_path = extract_table_image(pdf_path, page_num, output_folder)

    # Step 3: Preprocess the image
    preprocessed_image_path = preprocess_image(image_path)

    # Step 4: Extract text from the preprocessed image
    extracted_text = extract_text_from_image(preprocessed_image_path)

    # Step 5: Extract financial data using Groq API
    financial_data = extract_financial_data(extracted_text)
    try:
        financial_data = json.loads(financial_data)  # Convert JSON string to dictionary
    except json.JSONDecodeError:
        print("Error: Received response is not valid JSON. Falling back to manual parsing.")
        financial_data = manual_parse_financial_data(extracted_text)

    # Save financial data to a JSON file
    financial_data_path = os.path.join(output_folder, "financial_data.json")
    with open(financial_data_path, "w") as f:
        json.dump(financial_data, f, indent=4)

    print(f"Processed {pdf_path}. Results saved in {output_folder}.")

# Main Function to Process All PDFs in the Input Folder
def main(input_folder, output_folder):
    """Main function to process all PDFs in the input folder."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    pdf_files = [f for f in os.listdir(input_folder) if f.endswith('.pdf')]

    # Process each PDF file
    for pdf in pdf_files:
        pdf_path = os.path.join(input_folder, pdf)
        output_subfolder = os.path.join(output_folder, pdf.replace('.pdf', ''))
        print(f"Processing {pdf_path}...")
        process_pdf(pdf_path, output_subfolder)

if __name__ == "__main__":
    input_folder = "input"
    output_folder = "output"
    main(input_folder, output_folder)