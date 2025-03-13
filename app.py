import os
import csv
import logging
import sys
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, abort

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from openai import OpenAI

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Check that required directories exist
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
if not os.path.exists(template_dir):
    logger.error(f"Templates directory not found: {template_dir}")
    os.makedirs(template_dir, exist_ok=True)
    logger.info(f"Created templates directory: {template_dir}")

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
if not os.path.exists(static_dir):
    logger.error(f"Static directory not found: {static_dir}")
    os.makedirs(static_dir, exist_ok=True)
    logger.info(f"Created static directory: {static_dir}")

css_dir = os.path.join(static_dir, 'css')
if not os.path.exists(css_dir):
    logger.error(f"CSS directory not found: {css_dir}")
    os.makedirs(css_dir, exist_ok=True)
    logger.info(f"Created CSS directory: {css_dir}")

@app.route('/')
def index():
    """Render the home page with the CSV upload and configuration form."""
    try:
        template_path = os.path.join(template_dir, 'index.html')
        if not os.path.exists(template_path):
            logger.error(f"Template not found: {template_path}")
            return "Error: index.html template not found. Please make sure your repository includes the templates directory with index.html", 500
        
        logger.info("Rendering index template")
        return render_template('index.html')
    except Exception as e:
        logger.exception(f"Error rendering index template: {str(e)}")
        return f"An error occurred: {str(e)}", 500

@app.route('/generate', methods=['POST'])
def generate():
    """Process the uploaded CSV and generate email drafts."""
    try:
        # Get form data
        if 'csv_file' not in request.files:
            flash('No file part in the request')
            return redirect(url_for('index'))
            
        csv_file = request.files['csv_file']
        if csv_file.filename == '':
            flash('No file selected')
            return redirect(url_for('index'))
            
        # Get form fields with validation
        try:
            email_column = request.form.get('email_column', '')
            first_name_column = request.form.get('first_name_column', '')
            company_column = request.form.get('company_column', '')
            
            if not email_column or not first_name_column or not company_column:
                flash('Please provide all required column letters')
                return redirect(url_for('index'))
                
            use_template = 'use_template' in request.form
            subject_template = request.form.get('subject_template', '') if use_template else ''
            body_template = request.form.get('body_template', '') if use_template else ''
            use_ai = 'use_ai' in request.form
            api_key = request.form.get('api_key', '') if use_ai else ''
            custom_prompt = request.form.get('custom_prompt', '') if use_ai else ''
        
            if use_ai and not api_key:
                flash('Please provide a Perplexity API key when using AI')
                return redirect(url_for('index'))
        except Exception as e:
            logger.exception(f"Error processing form data: {str(e)}")
            flash(f'Error processing form: {str(e)}')
            return redirect(url_for('index'))

        # Process CSV directly without saving to disk
        try:
            # Read CSV data from memory
            csv_data = csv_file.read().decode('utf-8')
            if not csv_data.strip():
                flash('The uploaded CSV file is empty')
                return redirect(url_for('index'))
                
            csv_reader = csv.reader(StringIO(csv_data))
            headers = next(csv_reader, None)  # Assume first row is headers
            
            if not headers:
                flash('The CSV file has no headers')
                return redirect(url_for('index'))
            
            # Convert column letters to indices (e.g., A=0, B=1)
            try:
                email_col_idx = ord(email_column.upper()) - ord('A')
                first_name_col_idx = ord(first_name_column.upper()) - ord('A')
                company_col_idx = ord(company_column.upper()) - ord('A')
                
                if email_col_idx < 0 or first_name_col_idx < 0 or company_col_idx < 0:
                    flash('Column letters must be between A and Z')
                    return redirect(url_for('index'))
            except Exception as e:
                logger.exception(f"Error converting column letters: {str(e)}")
                flash('Invalid column letters. Please use letters A-Z')
                return redirect(url_for('index'))
            
            max_col = max(email_col_idx, first_name_col_idx, company_col_idx)
            if max_col >= len(headers):
                flash(f'Column index out of range. CSV has only {len(headers)} columns.')
                return redirect(url_for('index'))
                
            # Collect data from rows
            data = []
            for row in csv_reader:
                if len(row) > max_col:
                    email = row[email_col_idx].strip()
                    first_name = row[first_name_col_idx].strip()
                    company = row[company_col_idx].strip()
                    if email:
                        data.append({'email': email, 'first_name': first_name, 'company': company})
        except Exception as e:
            logger.exception(f"Error reading CSV file: {str(e)}")
            flash(f'Error reading CSV file: {str(e)}')
            return redirect(url_for('index'))

        if not data:
            flash('No valid email addresses found in the CSV')
            return redirect(url_for('index'))

        # Generate email content
        emails = []
        for item in data:
            email = item['email']
            first_name = item['first_name']
            company = item['company']

            # Subject generation
            subject = (subject_template.replace('{first_name}', first_name)
                      .replace('{company}', company)) if use_template else ''

            # Body generation
            if use_ai:
                prompt = custom_prompt or "Write a friendly outreach email to {first_name} at {company}."
                prompt = prompt.replace('{first_name}', first_name).replace('{company}', company)
                try:
                    body = generate_ai_email(api_key, prompt)
                except Exception as e:
                    logger.exception(f"Error generating AI email: {str(e)}")
                    body = f"Error generating email: {str(e)}"
            elif use_template:
                body = body_template.replace('{first_name}', first_name).replace('{company}', company)
            else:
                body = ''

            emails.append({'email': email, 'subject': subject, 'body': body})

        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Email', 'Subject', 'Body'])
        for email in emails:
            writer.writerow([email['email'], email['subject'], email['body']])

        # Send CSV as a downloadable response
        csv_content = output.getvalue()
        response = make_response(csv_content)
        response.headers["Content-Disposition"] = "attachment; filename=generated_emails.csv"
        response.headers["Content-type"] = "text/csv"
        return response
        
    except Exception as e:
        logger.exception(f"Unexpected error in generate: {str(e)}")
        flash(f'An unexpected error occurred: {str(e)}')
        return redirect(url_for('index'))

def generate_ai_email(api_key, prompt):
    """Generate email content using the Perplexity API via OpenAI client."""
    if not api_key:
        return "Error: API key is required."
        
    client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
    try:
        response = client.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "system", "content": "You are a personal assistant who writes highly personalized, authentic-sounding emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800,
            top_p=0.9,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception(f"Error in Perplexity API call: {str(e)}")
        return f"Error generating email: {str(e)}"

@app.errorhandler(404)
def page_not_found(e):
    return "Page not found. Please check the URL and try again.", 404

@app.errorhandler(500)
def server_error(e):
    return "An internal server error occurred. Please try again later.", 500

if __name__ == '__main__':
    # Use PORT environment variable if available (for Render)
    port = int(os.environ.get('PORT', 5000))
    # Only run in debug mode during development
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
