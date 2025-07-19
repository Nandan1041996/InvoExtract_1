
from pdf2image import convert_from_path
import os
from pypdf import PdfReader
import os
from PIL import Image
import base64
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI,GoogleGenerativeAIEmbeddings
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv
import json
import shutil
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import uuid
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import base64
import uuid
import traceback


load_dotenv()

app = Flask(__name__)
google_api = os.getenv('GOOGLE_API_KEY')


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET'])
def index():
    return render_template('New_index.html')


# define model
gemini_model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", #'gemini-2.5-pro'
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=1,
        google_api_key =google_api)

# define prompt for control model
prompt_template = """You are the helpful assistgant you have to give me answer in dictionary format in dictionary
            there will be key value pair which you will get from content provided to you.if you do not get any information from 
            document donot need to give your own.
            
            Important things that you have to check before do the process:
            1 -->   Thing you have to extract keys with values, Given Below keys are common key names  
                    "Bill To" (Note:comapany name), its "Pan No", "Gstin No","Invoice No", "Invoice date", "buyers Order No",
                    "Bill from" (Note:comapany name), its "Pan No", "Gstin No" 
                    material with serial No(in invoice possible that some invoice has "SI\nNo.","Sr No.", "Item", "Sr", "S No" etc.)
                    "HSN code" or "HSN", "Qty" or "Quantity", "Unit" or "per", "Unit Price", "Discount" or "Dis" rate, "Taxable Amt" or "Taxable Amount", "CGST rate" or "CGST %","CGST Amount",
                    "SGST rate" or"SGST %", "SGST Amount" , "Total Amount" or "Amount" or "Line Total" or "Net Amount"
                    Note: These are the common keys name you will get in invoice possible that few keys available ans possible that some keys name different. No need to extract description of material from material table 
            2 --> Length of that Customer order No number must 10 this you have to check.(Note: Name can be different ex given in common key name).
            3 --> Images formate will not be same you have to handle that  
            4 --> In some Image, "bill from" key is not given but company name is available you have to take care of it.
            5 --> Extract key-value pairs and for material use unique field or key name "material" return each material item as a dictionary inside a list — no separate field lists. 
                  For every image you process, use the following standardized key names:
                  In Image, any where TAX INVOICE or Text Invoice or tex invoice available then use key name for that 'Tax Invoice'
                  buyer → for "Bill To", buyers pan no → for PAN under "Bill To", buyers gstin no → for GSTIN under "Bill To", buyers order number → for keys like "Customer Order Number", "Order Number", etc., 
                  vendor → for "Bill From", vendors pan no → for PAN under "Bill From", vendor gstin no → for GSTIN under "Bill From"
                  For material key names(Each material item must include all of the following mandatory fields using these exact key names):
                    'sr no'-> for Sr No, SI\nNo., Sr No, Item, Sr, S No.
                    'hsn'-> for HSN code, HSN
                    'qty'-> Qty, Quantity
                    'unit'-> for Unit, per, UoM(Note if this column not available then look any unit available in qty column if available then take that value else keep value as nan
                    'unit price'-> Unit Price
                    'taxable amt'-> for Taxable Amt,Taxable Amount,Taxable Value Currency INR
                    'discount'-> for Discount, Dis
                    'cgst %'-> for CGST rate, CGST % OUTPUT CGST %
                    'cgst amount'-> for CGST Amount, Central
                    'sgst %'-> for SGST rate, SGST %, OUTPUT SGST %
                    'sgst amount'-> for SGST Amount, SGST
                    'amount'-> for Amount, Line Total, Net Amount
                  keys need to extract onetime only given below:
                    buyer, buyers pan no, buyers gstin no, buyers order number, vendor, vendors pan no, vendor gstin no
                  Note: No need to add extra key beyond given key
            6 --> Sometime table does not have header then :
                  if vendor name is Mogli Labs (India ) Pvt Ltd then if header is not available in material table then use headers: 
                    sr no, hsn, qty, unit, unit price, taxable amt, cgst %, cgst amount, sgst %, sgst amount, amount
                  if vendor is GHCL LTD and if found any image that does not contain header then use headers:
                    sr no, hsn, qty, unit, unit price, discount, taxable amt, cgst %, cgst amount, sgst %, sgst amount, amount
            """ 

def image_to_text(output_dir,image_path,prompt_template):
    ext = image_path.split('.')[-1]

    with open(f'{output_dir}/{image_path}', "rb") as img_file:
        b64_string = base64.b64encode(img_file.read()).decode('utf-8')

    messages = [
            (
                "user",
                [
                    {"type": "text", "text": prompt_template},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{ext};base64,{b64_string}"},
                    },
                ],
            )
        ]

    try:
        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | gemini_model | JsonOutputParser()
        result = chain.invoke({"b64_img": b64_string, "ext": ext})
        return result

    except Exception as e:
        return e

def pdf_to_text(pdf_path,file_name):
    upload_path = os.path.join('uploads',file_name)
    if pdf_path.endswith('pdf'):
        # Output directory for images
        os.path.basename(pdf_path)
        output_dir = os.path.basename(pdf_path).split('.')[0]
        os.makedirs(output_dir, exist_ok=True)

        # Convert PDF to list of images (one per page)
        images = convert_from_path(pdf_path, dpi=300)
        
        # Save each page as a JPEG file
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f"{output_dir}_{i + 1}.jpg")
            image.save(image_path, 'JPEG')

        img_file_lst = os.listdir(output_dir)
        if len(img_file_lst)!=0:
            page_wise_res = []
            for image_file in img_file_lst:
                result = image_to_text(output_dir,image_file,prompt_template)
                page_wise_res.append(result)

            if len(page_wise_res)>0:
                final_dict = page_wise_res[0]
                if not 'Tax Invoice' in final_dict:
                    os.remove(upload_path) 
                    # return 'Tax Invoice Not Found In Invoice'
                    # return jsonify({"error": "TAX INVOICE Not Found"}), 400
                    return {"success": False, "error": "TAX INVOICE Not Found."}

                elif not final_dict['buyers order number'].startswith('45'):
                    os.remove(upload_path) 
                    # return 'Buyers number is not start with 45'
                    return {"success": False, "error": "Buyers number is not start with 45."}
                elif  len(final_dict['buyers order number']) != 10:
                    os.remove(upload_path) 
                    # return 'Buyers number starts with 45 but length is not equal to 10'
                    return {"success": False, "error": "Buyers number starts with 45 but length is not equal to 10."}
                
                if 'material' in final_dict:
                    material_lst = final_dict['material']
                else:
                    material_lst=[]
                
                for item in range(1,len(page_wise_res)):
                    if 'material' in page_wise_res[item] and len(page_wise_res[item]['material'])>0 :
                        material_lst.extend(page_wise_res[item]['material'])
                final_dict['material'] = material_lst

                df = pd.DataFrame(final_dict['material'])
                df.drop_duplicates(inplace=True)
                df = df[~df['sr no'].isna()]
                final_dict['material'] = df.to_dict(orient='records')

                # Send email with extracted data and PDF
                email_sent = send_mail(final_dict, upload_path)

                return final_dict
            
    elif pdf_path.endswith('jpg') or  pdf_path.endswith('png') :
        print('in')
        os.makedirs('Image_folder', exist_ok=True)
        
        # Step 2: Get the image file name from full path
        image_name = os.path.basename(pdf_path)  # e.g., 'photo1.jpg'

        # Step 3: Open the original image from its full path
        img = Image.open(pdf_path)
        print('img::',img)

        # Step 4: Prepare the path to save it in 'Image_folder'
        save_path = os.path.join('Image_folder', image_name)

        # Step 5: Get the file extension for saving format
        ext = image_name.split('.')[-1].upper()
        if ext == 'JPG':
            ext = 'JPEG'  # Pillow uses 'JPEG'

        # Step 6: Save the image into the folder
        img.save(save_path, format=ext)

        img_file_lst = os.listdir('Image_folder')
        result = image_to_text('Image_folder',img_file_lst[0],prompt_template)
        os.remove(save_path)
        if not 'Tax Invoice' in result:
            os.remove(upload_path)
            # return 'Tax Invoice Not Found In Image'
            return {"success": False, "error": "Tax Invoice Not Found In Image."}
        
        elif not result['buyers order number'].startswith('45'):
            os.remove(upload_path)
            # return 'Buyers number is not start with 45'
            return {"success": False, "error": "Buyers number is not start with 45."}
        
        elif  len(result['buyers order number']) != 10:
            os.remove(upload_path)
            # return 'Buyers number starts with 45 but length is not equal to 10'
            return {"success": False, "error": "Buyers number starts with 45 but length is not equal to 10."}
        else:
            return result
       
    else:
        return "Please provide valid format: pdf, png and jpg"
        # return {"success": False, "error": "Please provide valid format: pdf, png and jpg."}


@app.route('/upload', methods=['POST'])
def upload_file():
    print('file::::::::::::::::::::',request.files)

    if 'pdfFile' not in request.files:
        return jsonify({"success": False, "error": "No file part in request."})

    file = request.files['pdfFile']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected."})

    file_path = os.path.join('uploads',file.filename)
    filename = secure_filename(file.filename)
    file.save(file_path)

    # Encode PDF to base64 for preview
    with open(file_path, "rb") as f:
        encoded_pdf = base64.b64encode(f.read()).decode('utf-8')

    return jsonify({
        "success": True,
        "message": "File uploaded successfully.",
        "filename": filename,  # Needed later in /extract
        "original_filename": file.filename,
        "pdf_data": encoded_pdf  # For PDF viewer
    })


@app.route('/extract', methods=['POST'])
def extract_data():
    try:
        data = request.get_json()
        filename = data.get('filename')
        original_filename = data.get('original_filename')

        if not filename:
            return jsonify({"success": False, "error": "Filename is missing."}), 400

        upload_path = os.path.join(UPLOAD_FOLDER, original_filename)
        if not os.path.exists(upload_path):
            return jsonify({"success": False, "error": "Uploaded file not found."}), 400

        # Extract text from PDF
        result = pdf_to_text(upload_path, original_filename)

        # 🧠 If the result is an error dict (i.e., has success=False), return it
        if isinstance(result, dict) and not result.get("success", True):
            return jsonify(result), 400

        # ✅ Successful extraction
        for f in os.listdir(UPLOAD_FOLDER):
            os.remove(os.path.join(UPLOAD_FOLDER, f))

        return jsonify({
            "success": True,
            "message": "Text extracted successfully.",
            "data": result
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": "Internal server error: " + str(e)}), 500


def send_mail(data, file_path):
    try:
        message = MIMEMultipart()
        sender_email = 'mayurnandanwar@ghcl.co.in'
        message["From"] = sender_email
        receiver_email = 'mayurnandanwar@ghcl.co.in' 
        message["To"] = receiver_email
        message["Subject"] = "Extracted Information"
        
        json_string = json.dumps(data, indent=4)
        body = "Extracted_Information: \n"+str(json_string)
        message.attach(MIMEText(body, "plain"))
        
        with open(file_path, "rb") as file:
            attachment = MIMEApplication(file.read(), Name=os.path.split(file_path)[1])
            message.attach(attachment)
        
        password = os.getenv('email_password')
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(sender_email, password)
        s.sendmail(sender_email, receiver_email, message.as_string())
        s.quit()
        return True
    except Exception as e:
        return False


if __name__ == '__main__':
    app.run(debug=True)


