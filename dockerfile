FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .

# Install the required packages including gunicorn and openpyxl
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the necessary files and directories
COPY . . 

EXPOSE 8080

# Start the Flask app using gunicorn with the correct module path
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]