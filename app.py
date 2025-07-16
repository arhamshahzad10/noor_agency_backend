from flask import Flask, render_template, request, jsonify, send_file
from flask import render_template
from flask import session, redirect, url_for
from collections import OrderedDict
import pandas as pd
import json
import os
import datetime
import requests
import qrcode
import tempfile
from weasyprint import HTML
import math
import base64
import psycopg2



    

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.secret_key = os.getenv("SECRET_KEY", "myfallbacksecret")
app.config['SESSION_COOKIE_SECURE'] = True

CONFIG = {
    "sandbox": {
        "RECORDS_FILE": "records_sandbox.json",
        "API_TOKEN": "2663ec4e-6ccc-35ff-969b-507ab139cd6e",
        "API_URL": "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb"
    },
    "production": {
        "RECORDS_FILE": "records_production.json",
        "API_TOKEN": "",
        "API_URL": "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata"
    }
}



def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )

def get_env():
    env = request.args.get('env') or request.headers.get('X-ERP-ENV') or 'sandbox'
    return env if env in CONFIG else 'sandbox'

def get_records_file(env):
    return CONFIG[env]['RECORDS_FILE']

def get_api_token(env):
    return CONFIG[env]['API_TOKEN']

def get_api_url(env):
    return CONFIG[env]['API_URL']

def load_records(env):
    file = get_records_file(env)
    if os.path.exists(file):
        with open(file, 'r') as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_records(env, records):
    file = get_records_file(env)
    with open(file, 'w') as f:
        json.dump(records, f, indent=2)

# Store last uploaded file and last JSON per environment
last_uploaded_file = {}
last_json_data = {}



@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    env = request.form.get('environment')

    print("Trying to log in with:", username, password)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = %s AND password_hash = %s", (username, password))
    user = cur.fetchone()

    if not user:
        print("No user found.")
        cur.close()
        conn.close()
        return render_template('index.html', error="Invalid username or password")

    user_id = user[0]
    print("User ID found:", user_id)

    cur.execute("SELECT id FROM clients WHERE user_id = %s", (user_id,))
    client = cur.fetchone()
    cur.close()
    conn.close()

    if not client:
        print("No client linked to this user.")
        return render_template('index.html', error="Client info missing")

    session['user_id'] = user_id
    session['client_id'] = client[0]
    session['env'] = env

    return redirect(url_for('dashboard_html'))









# Get all past records
@app.route('/records', methods=['GET'])
def get_records():
    env = get_env()
    records = load_records(env)
    return jsonify(records)



#  Upload Excel File
@app.route('/upload-excel', methods=['POST'])
def upload_excel():
    env = get_env()
    file = request.files.get('file')
    if not file or not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file format'}), 400
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{env}_{file.filename}")
    file.save(filepath)
    last_uploaded_file[env] = filepath
    return jsonify({'message': 'File uploaded successfully'})



# Get JSON Data
@app.route('/get-json', methods=['GET'])
def get_json():
    env = get_env()
    if env not in last_uploaded_file or not os.path.exists(last_uploaded_file[env]):
        print("ERROR: File not found or not uploaded. Env =", env)
        print("last_uploaded_file =", last_uploaded_file)
        return jsonify({'error': 'No file uploaded'}), 400

    def safe(val, default=""):
        return default if pd.isna(val) or val in [None, ""] else val

    df = pd.read_excel(last_uploaded_file[env], header=None)

    # Parse sectioned key-value pairs
    section_data = {}
    product_start_index = None

    for i, row in df.iterrows():
        key = str(row[0]).strip() if pd.notna(row[0]) else ''
        val = row[1] if len(row) > 1 else None

        if key.lower() == "hscode":
            product_start_index = i
            break

        if key and not any(key.startswith(s) for s in ["1)", "2)", "3)", "4)"]):
            section_data[key] = safe(val, "")

    if product_start_index is None:
        print("ERROR: No product section found. Section data:", section_data)
        print("File path:", last_uploaded_file[env])
        return jsonify({'error': 'No product section found'}), 400

    product_df = pd.read_excel(last_uploaded_file[env], skiprows=product_start_index)

    items = []
    for _, row in product_df.iterrows():
        try:
            rate_raw = safe(row.get("rate", ""), "")
            rate = str(rate_raw).strip() if isinstance(rate_raw, str) else f"{int(float(rate_raw) * 100)}%"

            hs_code_raw = safe(row.get("hsCode", ""))
            hs_code = (
                "{:.4f}".format(float(hs_code_raw))
                if isinstance(hs_code_raw, (int, float)) and not pd.isna(hs_code_raw)
                else str(hs_code_raw).strip()
            )

            item = OrderedDict([
                ("hsCode", hs_code),
                ("productDescription", safe(row.get("productDescription"))),
                ("rate", rate),
                ("uoM", safe(row.get("uoM"))),
                ("quantity", int(safe(row.get("quantity"), 0))),
                ("totalValues", float(safe(row.get("totalValues"), 0))),
                ("valueSalesExcludingST", float(safe(row.get("valueSalesExcludingST"), 0))),
                ("fixedNotifiedValueOrRetailPrice", float(safe(row.get("fixedNotifiedValueOrRetailPrice"), 0))),
                ("salesTaxApplicable", float(safe(row.get("salesTaxApplicable"), 0))),
                ("salesTaxWithheldAtSource", float(safe(row.get("salesTaxWithheldAtSource"), 0))),
                ("extraTax", str(safe(row.get("extraTax")))),
                ("furtherTax", float(safe(row.get("furtherTax"), 0))),
                ("sroScheduleNo", str(safe(row.get("sroScheduleNo")))),
                ("fedPayable", float(safe(row.get("fedPayable"), 0))),
                ("discount", float(safe(row.get("discount"), 0))),
                ("saleType", str(safe(row.get("saleType")))),
                ("sroItemSerialNo", str(safe(row.get("sroItemSerialNo"))))
            ])
            items.append(item)
        except Exception as e:
            return jsonify({"error": f"Error parsing row: {row.to_dict()} — {str(e)}"}), 400

    raw_date = section_data.get("invoiceDate", "")
    if isinstance(raw_date, datetime.datetime):
        invoice_date = raw_date.strftime("%Y-%m-%d")
    else:
        invoice_date = str(raw_date).strip()

    invoice_json = OrderedDict([
        ("invoiceType", safe(section_data.get("invoiceType"))),
        ("invoiceDate", invoice_date),
        ("sellerNTNCNIC", str(safe(section_data.get("sellerNTNCNIC")))),
        ("sellerBusinessName", safe(section_data.get("sellerBusinessName"))),
        ("sellerProvince", safe(section_data.get("sellerProvince"))),
        ("sellerAddress", safe(section_data.get("sellerAddress"))),
        ("buyerNTNCNIC", str(safe(section_data.get("buyerNTNCNIC")))),
        ("buyerBusinessName", safe(section_data.get("buyerBusinessName"))),
        ("buyerProvince", safe(section_data.get("buyerProvince"))),
        ("buyerAddress", safe(section_data.get("buyerAddress"))),
        ("buyerRegistrationType", safe(section_data.get("buyerRegistrationType"))),
        ("invoiceRefNo", str(safe(section_data.get("invoiceRefNo", "")))),  # critical fix
        ("scenarioId", safe(section_data.get("scenarioId"))),
    ])
    
    # Only include scenarioId if sandbox
    if env == 'sandbox':
        invoice_json["scenarioId"] = safe(section_data.get("scenarioId"))

    invoice_json["items"] = items

    last_json_data[env] = invoice_json
    return app.response_class(
        response=json.dumps(invoice_json, indent=2, allow_nan=False),
        mimetype='application/json'
    )



# Submit JSON to FBR
@app.route('/submit-fbr', methods=['POST'])
def submit_fbr():
    env = get_env()
    records = load_records(env)
    if env not in last_json_data:
        return jsonify({'error': 'No JSON to submit'}), 400

    api_token = get_api_token(env)
    api_url = get_api_url(env)
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_url, headers=headers, json=last_json_data[env])
        
        # Try parsing response
        try:
            res_json = response.json()
        except Exception:
            res_json = {}

        # Extract invoice number if available
        invoice_no = res_json.get("invoiceNumber", "N/A")
        last_json_data[env]["fbrInvoiceNumber"] = invoice_no
        is_success = bool(invoice_no and invoice_no != "N/A")
        
        if not is_success:
            return jsonify({
                "status": "Failed",
                "status_code": response.status_code,
                "response_text": response.text
            }), 400

 
        status = "Success" if is_success else "Failed"
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        invoice_date = last_json_data[env].get("invoiceDate", "")
        item = last_json_data[env]["items"][0]
        value_sales_ex_st = float(item.get("valueSalesExcludingST", 0))
        sales_tax_applicable = float(item.get("salesTaxApplicable", 0))
        total_value = value_sales_ex_st + sales_tax_applicable

        record = {
            "sr": len(records) + 1,
            "invoiceReference": invoice_no,
            "invoiceType": last_json_data[env]["invoiceType"],
            "invoiceDate": invoice_date,
            "buyerName": last_json_data[env]["buyerBusinessName"],
            "sellerName": last_json_data[env]["sellerBusinessName"],
            "totalValue": total_value,
            "valueSalesExcludingST": value_sales_ex_st,
            "salesTaxApplicable": sales_tax_applicable,
            "status": status,
            "date": date,
            "items": last_json_data[env]["items"]
        }
        records.append(record)
        save_records(env, records)

        return jsonify({
            "status": status,
            "invoiceNumber": invoice_no,
            "date": date
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Generate Invoice PDF
@app.route('/generate-invoice-excel', methods=['GET'])
def generate_invoice_excel():
    env = get_env()
    if env not in last_json_data:
        return jsonify({'error': 'No JSON data to generate invoice'}), 400

    data = last_json_data[env]
    items = data['items']

    # Calculate totals (in case not done earlier)
    total_excl = 0
    total_tax = 0

    for item in items:
        try:
            excl = float(str(item.get('valueSalesExcludingST', 0)).replace(",", ""))
        except:
            excl = 0
        try:
            tax = float(str(item.get('salesTaxApplicable', 0)).replace(",", ""))
        except:
            tax = 0

        total_excl += excl
        total_tax += tax

    # Add totals to data so template can use them
    data["totalTax"] = total_tax
    data["totalInclusive"] = total_excl + total_tax

    # Get FBR invoice number
    fbr_invoice = data.get("fbrInvoiceNumber", "")

    # --- Generate QR Code as base64 ---
    qr_base64 = ""
    if fbr_invoice:
        qr = qrcode.make(fbr_invoice)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            qr_path = tmp.name
            qr.save(qr_path)

        with open(qr_path, "rb") as qr_file:
            qr_base64 = base64.b64encode(qr_file.read()).decode("utf-8")

        os.remove(qr_path)

    # --- Load FBR logo as base64 ---
    logo_path = "fbr_logo.png"
    logo_base64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as logo_file:
            logo_base64 = base64.b64encode(logo_file.read()).decode("utf-8")

    # --- Render HTML invoice ---
    rendered_html = render_template(
        'invoice_template.html',
        data=data,
        qr_base64=qr_base64,
        logo_base64=logo_base64
    )

    # --- Generate PDF ---
    pdf_file_path = 'invoice.pdf'
    HTML(string=rendered_html).write_pdf(pdf_file_path)

    return send_file(pdf_file_path, as_attachment=True)




@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard.html')
def dashboard_html():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html')

    
if __name__ == '__main__':
    app.run(debug=True)
