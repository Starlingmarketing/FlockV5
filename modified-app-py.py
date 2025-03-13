import os
import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from openai import OpenAI

app = Flask(__name__)
# Use environment variable for secret key or fallback to a default
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

@app.route('/')
def index():
    """Render the home page with the CSV upload and configuration form."""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """Process the uploaded CSV and generate email drafts."""
    # Get form data
    csv_file = request.files['csv_file']
    email_column = request.form['email_column']
    first_name_column = request.form['first_name_column']
    company_column = request.form['company_column']
    use_template = 'use_template' in request.form
    subject_template = request.form['subject_template'] if use_template else ''
    body_template = request.form['body_template'] if use_template else ''
    use_ai = 'use_ai' in request.form
    api_key = request.form['api_key'] if use_ai else ''
    custom_prompt = request.form['custom_prompt'] if use_ai else ''

    # Validate inputs
    if not csv_file:
        flash('Please upload a CSV file')
        return redirect(url_for('index'))
    
    if use_ai and not api_key:
        flash('Please provide a Perplexity API key when using AI')
        return redirect(url_for('index'))

    # Process CSV directly without saving to disk
    try:
        # Read CSV data from memory
        csv_data = csv_file.read().decode('utf-8')
        csv_reader = csv.reader(StringIO(csv_data))
        headers = next(csv_reader)  # Assume first row is headers
        
        # Convert column letters to indices (e.g., A=0, B=1)
        email_col_idx = ord(email_column.upper()) - ord('A')
        first_name_col_idx = ord(first_name_column.upper()) - ord('A')
        company_col_idx = ord(company_column.upper()) - ord('A')
        
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
            body = generate_ai_email(api_key, prompt)
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

def generate_ai_email(api_key, prompt):
    """Generate email content using the Perplexity API via OpenAI client."""
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
        return f"Error generating email: {str(e)}"

if __name__ == '__main__':
    # Use PORT environment variable if available (for Render)
    port = int(os.environ.get('PORT', 5000))
    # Only run in debug mode during development
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)