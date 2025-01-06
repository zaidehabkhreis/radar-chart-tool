FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .

# Install the required packages including gunicorn
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Start the Flask app using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]