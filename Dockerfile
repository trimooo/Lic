# Use a base image with Python
FROM python:3.12-slim

# Install required packages for OpenCV
RUN apt-get update && apt-get install -y libgl1

# Copy your application files
WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install -r requirements.txt

# Set the command to run your application
CMD ["python", "app.py"]
